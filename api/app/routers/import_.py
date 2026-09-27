"""Excel-import endpoint: uploads a .xlsx of applicant rows, reconciles
them against existing `applicant` rows, and writes one `import_batch` row
per import summarizing the outcome.

**RBAC.** `SUPER_ADMIN` and `ADMISSIONS_MANAGER` only -- the two roles
ADR-03 already scopes `import_batch` visibility to, and the only two
roles with a legitimate reason to bulk-load applicant data into the
system.

**Checksum dedup.** The uploaded file's raw bytes are sha256'd
(`app.services.excel_import.compute_checksum`) before anything else. If a
prior `import_batch` row exists with the same checksum and
`status = COMPLETED`, this endpoint short-circuits: it returns that prior
batch's own summary (`deduplicated=True` on the response) and touches
nothing else -- no new `import_batch` row, no applicant reads or writes.
A `FAILED` prior batch for the same checksum does not short-circuit
(scoped to `COMPLETED` only, per the migration's own docstring), so a
genuinely failed import can be retried with the identical file once
whatever caused the failure is fixed.

**Column mapping.** Headers are resolved through
`app.services.import_config.COLUMN_MAP`, not hardcoded literal strings at
each field access -- a renamed/missing header raises `MissingColumnsError`
before any row is processed, surfaced here as a 422 naming the missing
header(s), never a partial silent import.

**Matching.** Each parsed row is matched against existing `applicant` rows
by normalized phone first, then normalized email if no phone match is
found (module prompt: "matched incoming rows against existing applicants
by normalized phone first and email second"). An unmatched row creates a
new `Applicant` at `IMPORTED` status. A matched row updates only reference
fields (`full_name`, `program`, `intake_cycle`, and email/phone
themselves) -- `current_status` is never touched on a matched row, since a
re-import must not silently reset or advance an applicant's pipeline
position.

**Flag-for-review, not auto-resolve, on a changed identifier.** If a
matched row's incoming email or phone differs from what is already stored
for that applicant, this endpoint does *not* silently overwrite the
identifier and call it resolved -- it still updates the applicant's other
reference fields, but records the row in `import_batch.flagged_rows`
(with the applicant id, old/new email, old/new phone, and a reason) and
counts it under `flagged_count` rather than `updated_count`, so a human
reviews whether the incoming file's email/phone is a correction or a
data-entry error before it becomes the applicant's system-of-record
contact detail. This module does not build a review-resolution workflow
(deferred, per `app.models.import_batch`'s own migration docstring) --
only the flag itself and its visibility in the batch summary.

**Module 20: one summary push notification per completed batch, never
one per imported row -- a deliberate decision, not the default choice
left unexamined.** An import can create dozens of `Applicant` rows in a
single call (this endpoint's whole reason to exist over one-at-a-time
entry); notifying once per created row would turn a routine, expected
bulk operation into a genuine notification flood for whoever is
watching -- the exact failure mode a "one push per event" design must
avoid when the "event" is actually a batch. The other extreme, no
notification at all, was also rejected: a completed import is real,
actionable information (dozens of new, unassigned applicants now exist
and need a counselor) that the recipient roles below have no other way
to learn about promptly -- silence would just move the flood problem to
"discover it eventually by refreshing the applicants list," which is
not actually better, only less honest about being a gap. One summary
per batch is the shape that survives both failure modes: exactly one
push, named with the real counts (`created_count`/`flagged_count`), no
matter whether the batch created 1 row or 500.

**Recipients mirror the same unassigned-applicant visibility split
Module 19's own `POST /applicants` trigger already established, not a
separately invented rule.** Every row this endpoint creates is
unassigned by construction -- `import_applicants`'s own `new_applicant =
Applicant(...)` call below never sets `assigned_counselor_id` at all,
so a fresh import row starts exactly where a manually-created,
left-unassigned applicant does. `SUPER_ADMIN`/`ADMISSIONS_MANAGER` are
therefore the correct, and only, recipients -- the same two roles
Module 19's own unassigned case notifies, for the identical reason (the
two roles with an actual role in deciding who picks up a fresh,
unassigned inquiry). A `FAILED` batch (`MissingColumnsError`) sends no
notification at all -- nothing was actually created, so there is
nothing new for `SUPER_ADMIN`/`ADMISSIONS_MANAGER` to act on; the
caller's own real `422` response already tells them the file was
rejected. The `deduplicated=True` short-circuit path (an exact repeat
upload of an already-`COMPLETED` file's own checksum) also sends no
notification -- it creates zero new rows by construction, the same "no
notification for no new information" reasoning as the failed-file case.
"""

from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import require_role_session
from app.core.push import get_active_user_ids_for_roles, notify_in_background
from app.models.applicant import Applicant
from app.models.enums import ApplicationStatus, ImportBatchStatus, RoleCode
from app.models.import_batch import ImportBatch
from app.models.user import User
from app.schemas.import_batch import ImportBatchResponse
from app.services.excel_import import (
    MissingColumnsError,
    compute_checksum,
    normalize_email,
    normalize_phone,
    parse_workbook,
)

router = APIRouter(prefix="/import", tags=["import"])


def _batch_response(batch: ImportBatch, deduplicated: bool = False) -> ImportBatchResponse:
    return ImportBatchResponse(
        id=batch.id,
        status=batch.status,
        row_count=batch.row_count or 0,
        created_count=batch.created_count,
        updated_count=batch.updated_count,
        flagged_count=batch.flagged_count,
        rejected_count=batch.rejected_count,
        flagged_rows=batch.flagged_rows,
        error_detail=batch.error_detail,
        completed_at=batch.completed_at,
        deduplicated=deduplicated,
    )


@router.post("/applicants", response_model=ImportBatchResponse)
async def import_applicants(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    user_and_db: tuple[User, AsyncSession] = Depends(
        require_role_session(RoleCode.SUPER_ADMIN, RoleCode.ADMISSIONS_MANAGER)
    ),
) -> ImportBatchResponse:
    user, db = user_and_db

    if not file.filename or not file.filename.lower().endswith(".xlsx"):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "only .xlsx files are accepted")

    file_bytes = await file.read()
    checksum = compute_checksum(file_bytes)

    existing = await db.execute(
        select(ImportBatch).where(
            ImportBatch.checksum == checksum,
            ImportBatch.status == ImportBatchStatus.COMPLETED,
        )
    )
    prior_batch = existing.scalar_one_or_none()
    if prior_batch is not None:
        return _batch_response(prior_batch, deduplicated=True)

    batch = ImportBatch(
        source_filename=file.filename,
        status=ImportBatchStatus.PROCESSING,
        checksum=checksum,
        imported_by=user.id,
    )
    db.add(batch)
    await db.flush()

    try:
        parsed_rows, rejected_errors = parse_workbook(file_bytes)
    except MissingColumnsError as exc:
        batch.status = ImportBatchStatus.FAILED
        batch.error_detail = str(exc)
        batch.completed_at = datetime.now(timezone.utc).replace(tzinfo=None)
        # Explicit commit, not just flush: get_scoped_session (app.core.deps)
        # wraps this whole request in one session.begin() block, which rolls
        # back the entire transaction -- including this FAILED batch row --
        # the instant the HTTPException below propagates out of the route.
        # A flush alone is visible only within the still-open transaction;
        # without this commit, the batch this endpoint promises to write
        # "one import_batch row per import" for a rejected file silently
        # never lands in the database at all, confirmed as a real gap by
        # this module's own live verification (see the module-02 report):
        # querying import_batch after a rejected upload showed no FAILED
        # row whatsoever, only the COMPLETED ones from unrelated successful
        # imports.
        await db.commit()
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"import rejected: {exc}",
        ) from exc

    created_count = 0
    updated_count = 0
    flagged_count = 0
    flagged_rows: list[dict] = []

    for row in parsed_rows:
        normalized_phone = normalize_phone(row.phone)
        normalized_email = normalize_email(row.email)

        matched: Applicant | None = None

        if normalized_phone is not None:
            all_applicants_result = await db.execute(select(Applicant))
            for candidate in all_applicants_result.scalars():
                if normalize_phone(candidate.phone) == normalized_phone:
                    matched = candidate
                    break

        if matched is None and normalized_email is not None:
            email_result = await db.execute(select(Applicant))
            for candidate in email_result.scalars():
                if normalize_email(candidate.email) == normalized_email:
                    matched = candidate
                    break

        if matched is None:
            new_applicant = Applicant(
                import_batch_id=batch.id,
                full_name=row.full_name,
                email=row.email,
                phone=row.phone,
                program=row.program,
                intake_cycle=row.intake_cycle,
                current_status=ApplicationStatus.IMPORTED,
            )
            db.add(new_applicant)
            created_count += 1
            continue

        identifier_changed = (
            normalize_email(matched.email) != normalized_email
            or normalize_phone(matched.phone) != normalized_phone
        )

        old_email, old_phone = matched.email, matched.phone
        matched.full_name = row.full_name
        matched.program = row.program
        matched.intake_cycle = row.intake_cycle
        matched.email = row.email
        matched.phone = row.phone
        # current_status is deliberately never touched here -- see module
        # docstring: a re-import must not reset or advance the pipeline.

        if identifier_changed:
            flagged_count += 1
            flagged_rows.append(
                {
                    "row_number": row.row_number,
                    "applicant_id": str(matched.id),
                    "old_email": old_email,
                    "new_email": row.email,
                    "old_phone": old_phone,
                    "new_phone": row.phone,
                    "reason": "matched applicant's email or phone changed",
                }
            )
        else:
            updated_count += 1

    batch.status = ImportBatchStatus.COMPLETED
    batch.row_count = created_count + updated_count + flagged_count + len(rejected_errors)
    batch.created_count = created_count
    batch.updated_count = updated_count
    batch.flagged_count = flagged_count
    batch.rejected_count = len(rejected_errors)
    batch.flagged_rows = flagged_rows or None
    batch.error_detail = "; ".join(rejected_errors) if rejected_errors else None
    batch.completed_at = datetime.now(timezone.utc).replace(tzinfo=None)

    await db.flush()
    await db.refresh(batch)

    # Module 20: one summary notification per completed batch, only
    # when it actually created at least one new (unassigned)
    # applicant -- see module docstring for the full reasoning,
    # including why an all-updates batch (created_count == 0) sends
    # nothing, the same "no notification for no new information" rule
    # the FAILED/deduplicated paths above already follow.
    if created_count > 0:
        recipient_ids = await get_active_user_ids_for_roles(
            db, [RoleCode.SUPER_ADMIN.value, RoleCode.ADMISSIONS_MANAGER.value]
        )
        background_tasks.add_task(
            notify_in_background,
            recipient_ids,
            "Import completed",
            f"{file.filename}: {created_count} new applicant(s) imported"
            + (f", {flagged_count} flagged for review" if flagged_count else "") + ".",
            "/import/history",
        )

    return _batch_response(batch)
