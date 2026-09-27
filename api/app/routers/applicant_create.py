"""Manual single-applicant creation (Module 19): `POST /applicants` --
the one applicant-creation path that is not the Excel-import endpoint.

**Why this exists.** Before this module, `Applicant` rows could only be
created by `app.routers.import_.import_applicants` -- a real gap for
the ordinary, ongoing case of a counselor taking a walk-in visitor or a
phone inquiry and needing to record that person as an applicant right
now, not batched into tomorrow's spreadsheet. This endpoint is the
single-row analogue of that same creation path, sharing its
normalization/matching logic (`app.services.excel_import`) rather than
re-implementing it.

**RBAC: `SUPER_ADMIN`/`ADMISSIONS_MANAGER`/`ADMISSIONS_COUNSELOR` --
deliberately the same three roles `app.routers.status.
transition_applicant_status` already owns, not import's narrower
`SUPER_ADMIN`/`ADMISSIONS_MANAGER`-only set.** A counselor handling a
walk-in or a phone call is a real, ordinary case this workflow should
support directly -- the counselor is the one actually taking the
inquiry, and the whole point of `assigned_counselor_id`'s per-row RLS
scoping (ADR-03) is that a counselor can already fully own applicants
assigned to them; creating one they are about to own is not a
different, more privileged action than transitioning its status
afterward. Import's own narrower set is about a *different* risk
(bulk-loading a whole spreadsheet of someone else's applicants), not
one that applies to a single applicant a counselor is entering about a
person standing in front of them.

**Design decision: `assigned_counselor_id` role-dependent default,
documented deliberately rather than picked silently.**

- `ADMISSIONS_COUNSELOR`: the applicant this role's own RLS policy
  (`applicant.role_visibility`) will ever let them see again after
  creation is exactly one where `assigned_counselor_id` is their own
  id -- creating a row with any other value, or leaving it `NULL`,
  would produce an applicant this same counselor could never see or
  act on again the moment this request's own transaction commits (RLS
  is fail-closed, not merely a display filter). So: omitted
  ->auto-assigned to the caller themselves; explicitly sent equal to
  the caller's own id -> same result, accepted; explicitly sent as any
  *other* counselor's id -> rejected with a real 422 before any write,
  since a counselor assigning a walk-in to a colleague is not this
  role's own call to make (that is squarely a manager/admin decision,
  the next bullet).
- `SUPER_ADMIN`/`ADMISSIONS_MANAGER`: neither role's own RLS visibility
  depends on `assigned_counselor_id` at all (both are in
  `_ALL_APPLICANT_VISIBLE_ROLES`), so there is no structural reason to
  force an assignment. Optional: omitted -> created unassigned
  (`NULL`, "a normal, expected state before a counselor picks up a new
  inquiry," per `Applicant`'s own model docstring -- exactly as true
  for a manually-created applicant as an imported one); explicitly sent
  -> assigned to that counselor immediately, validated to be a real,
  active `ADMISSIONS_COUNSELOR` account (422 otherwise) so a manager
  routing a walk-in straight to the counselor who will actually handle
  it does not have to make a second call.

**Design decision: initial status is `APPLIED`, not `IMPORTED` --
documented deliberately, not picked silently.**
`app.models.enums.ApplicationStatus`'s own docstring and
`ALLOWED_TRANSITIONS`'s own module docstring both describe `IMPORTED`
as specifically "a raw row, unreviewed" -- the status a spreadsheet row
starts at *before* anyone has looked at it, matched it, or spoken to
the applicant. That description does not fit a row a staff member is
entering by hand, right now, in the same motion as (or immediately
after) having an actual conversation with the applicant -- by
construction, a manually-created applicant has already been reviewed
by the person creating it; there is no unreviewed-raw-data state to
represent. Starting instead at `APPLIED` -- the status
`ALLOWED_TRANSITIONS` already treats as the first "real pipeline
position" reachable from `IMPORTED` -- correctly skips a state that
only ever meant "came from an unreviewed Excel row," without inventing
a new status value or changing the transition table itself: `APPLIED`
already exists, and its only current source (`IMPORTED -> APPLIED`) is
not lost or bypassed for anyone -- this endpoint simply gives a
manually-entered applicant the pipeline position it always actually
starts at, one step past where a raw import row does.

**`import_batch_id` is always `NULL` here, never client-supplied.**
Confirmed directly against this module's own live schema before
writing a single line of this router (`\d applicant` against the real
running Postgres instance): the column has always been nullable, with
no `NOT NULL` constraint and no migration needed for this module --
`Applicant`'s own original model docstring already anticipated this
exact case ("nullable: a future manually-created applicant, if that
path is ever added, would have no batch"). This endpoint is that
anticipated case, arriving; it needed zero schema change, exactly as
that docstring predicted, not merely assumed to be true without
checking.

**Duplicate detection reuses `app.services.excel_import.normalize_phone`/
`normalize_email` verbatim** -- the identical normalization the import
endpoint's own matching already uses, so "this phone/email is already
in the system" means the exact same thing whether the existing
duplicate arrived by spreadsheet or by this endpoint. Unlike import
(which treats a phone/email match as "this is the same person, update
their record"), a manual creation that collides is rejected outright
with a real `409`, naming the conflicting applicant's real id -- the
counselor or manager entering this row is not trying to *update* an
existing applicant (they would use the existing applicant's own detail
view / status-transition flow for that), so silently treating a
duplicate submission as an update, or worse, silently creating a second,
unrelated-looking row for the same real person, would both be wrong in
a way import's own "matched row -> update" behavior specifically is not
here. Phone is checked before email, mirroring import's own
"phone first, then email" precedence (`app.routers.import_`'s own
docstring) -- for the identical reason: phone is the more specific,
less commonly reused-across-people identifier of the two in this
domain.

**Duplicate detection deliberately reads through a full-visibility
scope, not the caller's own RLS-scoped session -- a real gap caught
while implementing this, not an incidental choice.** `import_.py`'s own
matching loop never has to think about this, because its own RBAC
(`SUPER_ADMIN`/`ADMISSIONS_MANAGER` only) is already a strict subset of
`applicant`'s full-visibility role list (`_ALL_APPLICANT_VISIBLE_ROLES`,
`0003_rls.py`) -- both of import's own callers already see every
applicant row. This endpoint's own RBAC is deliberately *wider*
(`ADMISSIONS_COUNSELOR` included, see above), and that role's own RLS
policy on `applicant` is the *narrow*, own-rows-only one: reusing
`require_role_session`'s own yielded `db` for the duplicate-detection
`SELECT` would silently scope that check to only the applicants this
one counselor can already see, and a duplicate phone/email belonging to
a different counselor's applicant (or an unassigned one) would sail
straight through undetected -- producing exactly the "two unrelated
people" outcome this endpoint exists to prevent, silently, for the one
role this module newly grants creation access to. The duplicate check
therefore opens its own short-lived, read-only
`open_scoped_session(actor_role=RoleCode.SUPER_ADMIN.value)` (a fresh
transaction, distinct from the caller's own -- see `app.core.db`'s own
docstring on why a second `open_scoped_session` is the correct pattern
here, not reusing one session past a role boundary) purely to read
every applicant row regardless of who is asking, matching normalized
phone/email against the *entire* table -- the actual write (the new
`Applicant` insert) still happens on the caller's own, correctly
role-scoped session and transaction afterward, so the RLS `WITH CHECK`
guarantee on the insert itself (a counselor cannot insert a row
assigned to someone else, enforced above) is completely unaffected.
The `409` this can produce therefore does reveal one specific fact a
counselor could not otherwise learn through `GET /applicants` -- that
*some* applicant with this phone/email already exists, and its id --
to a counselor who might not otherwise be able to see that row at all.
Accepted deliberately: the alternative (silently creating a genuine
duplicate person the rest of the system now treats as two unrelated
applicants) is a strictly worse outcome than a counselor learning one
UUID belongs to an already-known contact, and this is the exact
system-wide integrity guarantee ("rather than silently creating a
duplicate the rest of the system would then treat as two unrelated
people") this module was asked to build.

**Module 20: push-notifies the applicant's own assigned counselor, or
`ADMISSIONS_MANAGER`/`SUPER_ADMIN` if left unassigned -- the exact same
visibility split `applicant`'s own RLS policy already enforces, never
a role invented for this notification alone.** An `ADMISSIONS_COUNSELOR`
assigned to a new applicant is, by that same RLS policy, the *only*
counselor who can ever `GET` that applicant again -- notifying exactly
that one counselor and no one else mirrors read visibility exactly, not
a broader "notify every counselor" convenience that would tell a
counselor about an applicant they can't even open. An unassigned
applicant is visible to every `SUPER_ADMIN`/`ADMISSIONS_MANAGER`/
`FINANCE_STAFF`/`FINANCE_MANAGER`/`AUDITOR` per that same policy, but
only `SUPER_ADMIN`/`ADMISSIONS_MANAGER` are notified -- the two roles
with an actual role in the admissions pipeline (the same reasoning this
router's own `_CREATE_ROLES` already applies: finance/audit roles can
*see* applicant data for reconciliation, per ADR-03, but have no
legitimate reason to act on a fresh, unassigned inquiry the way a
manager deciding who should pick it up does). Delivery runs via
`BackgroundTasks` (`app.core.push.notify_in_background`), scheduled
*after* the real `201` response and its own database write have
already succeeded -- a push-delivery failure (a dead subscription, a
transient push-service outage) must never turn a successful applicant
creation into a failed request; see `app.core.push`'s own docstring for
why `BackgroundTasks`, not a task queue, is this project's correct
choice for this.
"""

import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import open_scoped_session
from app.core.deps import require_role_session
from app.core.push import get_active_user_ids_for_roles, notify_in_background
from app.models.applicant import Applicant
from app.models.application_status_event import ApplicationStatusEvent
from app.models.enums import ApplicationStatus, RoleCode
from app.models.role import Role
from app.models.user import User
from app.schemas.applicant_create import ApplicantCreateRequest
from app.schemas.reads import ApplicantDetail
from app.services.excel_import import normalize_email, normalize_phone

router = APIRouter(prefix="/applicants", tags=["applicants"])

# The same three roles app.routers.status already owns -- see this
# module's own docstring for why counselors are included here, unlike
# import's narrower SUPER_ADMIN/ADMISSIONS_MANAGER-only set.
_CREATE_ROLES = (
    RoleCode.SUPER_ADMIN,
    RoleCode.ADMISSIONS_MANAGER,
    RoleCode.ADMISSIONS_COUNSELOR,
)


def _to_detail(applicant: Applicant) -> ApplicantDetail:
    return ApplicantDetail(
        id=applicant.id,
        full_name=applicant.full_name,
        email=applicant.email,
        phone=applicant.phone,
        program=applicant.program,
        intake_cycle=applicant.intake_cycle,
        current_status=applicant.current_status,
        assigned_counselor_id=applicant.assigned_counselor_id,
        created_at=applicant.created_at,
        updated_at=applicant.updated_at,
        import_batch_id=applicant.import_batch_id,
    )


class _CounselorOption(BaseModel):
    """Minimal, non-sensitive shape for the "assign to" picker
    `ApplicantsPage`'s own new-applicant form needs -- id and display
    name only, deliberately not `app.schemas.users.UserSummary` (which
    exists for `SUPER_ADMIN`-only `GET /users` and carries fields, e.g.
    `is_active`/`last_login_at`, that this narrower, wider-audience
    lookup has no reason to expose to an `ADMISSIONS_MANAGER` caller).
    """

    id: uuid.UUID
    full_name: str


@router.get("/counselors", response_model=list[_CounselorOption])
async def list_assignable_counselors(
    user_and_db: tuple[User, AsyncSession] = Depends(
        require_role_session(RoleCode.SUPER_ADMIN, RoleCode.ADMISSIONS_MANAGER)
    ),
) -> list[_CounselorOption]:
    """Every active `ADMISSIONS_COUNSELOR` account, for the "assign to"
    picker on the manual-applicant-creation form -- `SUPER_ADMIN`/
    `ADMISSIONS_MANAGER` only, the same two roles this router's own
    `create_applicant` lets *optionally* assign a new applicant to any
    counselor (an `ADMISSIONS_COUNSELOR` caller is always auto-assigned
    to themselves and never needs to pick from a list at all, so this
    route excludes that role rather than returning it a list it has no
    use for). Declared here rather than in `app.routers.users` (which
    is `SUPER_ADMIN`-only end to end) since this lookup's own, wider
    audience does not fit that router's access model.
    """
    _, db = user_and_db
    rows = (
        await db.execute(
            select(User.id, User.full_name)
            .join(Role, User.role_id == Role.id)
            .where(Role.code == RoleCode.ADMISSIONS_COUNSELOR.value, User.is_active.is_(True))
            .order_by(User.full_name.asc())
        )
    ).all()
    return [_CounselorOption(id=row.id, full_name=row.full_name) for row in rows]


@router.post("", response_model=ApplicantDetail, status_code=status.HTTP_201_CREATED)
async def create_applicant(
    body: ApplicantCreateRequest,
    background_tasks: BackgroundTasks,
    user_and_db: tuple[User, AsyncSession] = Depends(require_role_session(*_CREATE_ROLES)),
) -> ApplicantDetail:
    user, db = user_and_db

    # Resolve the caller's own role_code -- require_role_session already
    # validated it is one of _CREATE_ROLES, but the specific value (not
    # merely "is allowed") decides the assignment default below.
    role_row = (await db.execute(select(Role.code).where(Role.id == user.role_id))).scalar_one()
    caller_role = RoleCode(role_row)

    # --- assigned_counselor_id resolution (see module docstring) ---
    assigned_counselor_id: uuid.UUID | None

    if caller_role is RoleCode.ADMISSIONS_COUNSELOR:
        if body.assigned_counselor_id is not None and body.assigned_counselor_id != user.id:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "an ADMISSIONS_COUNSELOR may only assign a new applicant to themselves",
            )
        assigned_counselor_id = user.id
    else:
        # SUPER_ADMIN / ADMISSIONS_MANAGER: optional, validated if sent.
        assigned_counselor_id = body.assigned_counselor_id
        if assigned_counselor_id is not None:
            counselor_row = (
                await db.execute(
                    select(User.is_active, Role.code)
                    .join(Role, User.role_id == Role.id)
                    .where(User.id == assigned_counselor_id)
                )
            ).first()
            if counselor_row is None or counselor_row[1] != RoleCode.ADMISSIONS_COUNSELOR.value:
                raise HTTPException(
                    status.HTTP_422_UNPROCESSABLE_ENTITY,
                    "assigned_counselor_id must be an existing ADMISSIONS_COUNSELOR account",
                )
            if not counselor_row[0]:
                raise HTTPException(
                    status.HTTP_422_UNPROCESSABLE_ENTITY,
                    "assigned_counselor_id refers to a deactivated account",
                )

    # --- duplicate detection, reusing excel_import's own normalization
    # verbatim -- see module docstring for why phone is checked first,
    # why a collision here is a hard 409 (not import's own matched-row
    # update behavior), and why this reads through a fresh, full-
    # visibility scope rather than the caller's own RLS-scoped `db`
    # (a counselor's own scope would silently miss a duplicate outside
    # their own assigned rows). ---
    normalized_phone = normalize_phone(body.phone)
    normalized_email = normalize_email(body.email)

    conflict: Applicant | None = None
    conflict_field: str | None = None
    async with open_scoped_session(actor_id=None, actor_role=RoleCode.SUPER_ADMIN.value) as dup_db:
        if normalized_phone is not None:
            for candidate in (await dup_db.execute(select(Applicant))).scalars():
                if normalize_phone(candidate.phone) == normalized_phone:
                    conflict, conflict_field = candidate, "phone"
                    break

        if conflict is None and normalized_email is not None:
            for candidate in (await dup_db.execute(select(Applicant))).scalars():
                if normalize_email(candidate.email) == normalized_email:
                    conflict, conflict_field = candidate, "email"
                    break

    if conflict is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"an applicant with this {conflict_field} already exists "
            f"(applicant_id={conflict.id})",
        )

    applicant = Applicant(
        import_batch_id=None,
        assigned_counselor_id=assigned_counselor_id,
        full_name=body.full_name,
        email=body.email,
        phone=body.phone,
        program=body.program,
        intake_cycle=body.intake_cycle,
        current_status=ApplicationStatus.APPLIED,
    )
    db.add(applicant)
    await db.flush()

    # A manually-created applicant starts life already at APPLIED (see
    # module docstring) -- the same "record the transition" discipline
    # app.routers.status.transition_applicant_status applies to every
    # later move applies here too, at creation time: from_status=None
    # (there was no prior status to move from -- this is the first
    # event for this applicant, mirroring StatusHistoryEvent.from_status's
    # own nullability, which exists specifically for this case), to_status
    # =APPLIED, changed_by=the creating user, so this applicant's status
    # history starts with a real, attributed event rather than an
    # unexplained row that simply appears already at APPLIED.
    event = ApplicationStatusEvent(
        applicant_id=applicant.id,
        from_status=None,
        to_status=ApplicationStatus.APPLIED,
        changed_by=user.id,
        note="Manually created applicant (walk-in/phone entry)",
    )
    db.add(event)
    await db.flush()
    await db.refresh(applicant)

    # --- Module 20: push-notify, scheduled after the real write above
    # has already succeeded -- see module docstring for the full
    # reasoning on why the recipient set mirrors applicant's own RLS
    # visibility split exactly, and why BackgroundTasks (not a task
    # queue) is the correct delivery mechanism here. ---
    if assigned_counselor_id is not None:
        notify_recipient_ids = [assigned_counselor_id]
    else:
        notify_recipient_ids = await get_active_user_ids_for_roles(
            db, [RoleCode.SUPER_ADMIN.value, RoleCode.ADMISSIONS_MANAGER.value]
        )

    background_tasks.add_task(
        notify_in_background,
        notify_recipient_ids,
        "New applicant",
        f"{applicant.full_name} was just added ({applicant.program}, {applicant.intake_cycle}).",
        f"/applicants?open={applicant.id}",
    )

    return _to_detail(applicant)
