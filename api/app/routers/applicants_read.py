"""Read-only endpoints over `applicant` and its related tables: list,
detail, status-history, and finance summary.

**RBAC design for this whole file: intentionally none beyond "any
authenticated session."** Every route below depends on
`require_role_session` with **all six** `RoleCode` values -- functionally
a no-op role gate, present only so every route follows this project's
established `require_role_session`-yields-`(user, db)` pattern rather than
reopening a second scoped session. The actual visibility narrowing for
every one of these routes is entirely RLS's job, already governed by
policies these tables have carried since Modules 01-03:

- `applicant`'s own `role_visibility` policy: `SUPER_ADMIN`,
  `ADMISSIONS_MANAGER`, `FINANCE_STAFF`, `FINANCE_MANAGER`, `AUDITOR` see
  every row; `ADMISSIONS_COUNSELOR` sees only rows where
  `assigned_counselor_id` is their own id.
- `application_status_event`'s policy is defined as an `EXISTS` against
  `applicant` using the exact same predicate -- a counselor's status
  history for another counselor's applicant is exactly as invisible as
  the applicant record itself.
- `finance_record`'s policy is a **different, narrower** allowlist:
  `SUPER_ADMIN`, `FINANCE_STAFF`, `FINANCE_MANAGER`, `AUDITOR` only --
  `ADMISSIONS_MANAGER` and `ADMISSIONS_COUNSELOR` are *not* in it, even
  though both can see the applicant itself. This is why
  `GET /applicants/{id}/finance` genuinely needs its own RLS-visibility
  check distinct from the applicant read above it: a counselor or manager
  requesting their own/any applicant's finance summary gets a real 404 --
  not because the applicant is invisible to them, but because the
  `finance_record` row is, per this table's own narrower policy. No route
  in this file re-implements or second-guesses any of the above in
  application code; every one is a plain `SELECT` through the RLS-scoped
  session `require_role_session` yields, letting the database decide what
  comes back.

Every response goes through a hand-declared Pydantic model
(`app.schemas.reads`), never a raw ORM object returned or dumped
directly -- see that module's own docstring for why.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import require_role_session
from app.models.applicant import Applicant
from app.models.application_status_event import ApplicationStatusEvent
from app.models.enums import ApplicationStatus, RoleCode
from app.models.finance_record import FinanceRecord
from app.models.payment_claim import PaymentClaim
from app.models.user import User
from app.schemas.reads import (
    ApplicantDetail,
    ApplicantFinanceResponse,
    ApplicantListResponse,
    ApplicantStatusBreakdown,
    ApplicantSummary,
    ApplicantSummaryTotals,
    PaymentClaimDetail,
    StatusHistoryEvent,
    StatusHistoryResponse,
)

router = APIRouter(prefix="/applicants", tags=["reads"])

_ALL_ROLES = tuple(RoleCode)


def _to_summary(applicant: Applicant) -> ApplicantSummary:
    return ApplicantSummary(
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
    )


@router.get("", response_model=ApplicantListResponse)
async def list_applicants(
    limit: int = Query(25, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_status: ApplicationStatus | None = None,
    program: str | None = None,
    intake_cycle: str | None = None,
    user_and_db: tuple[User, AsyncSession] = Depends(require_role_session(*_ALL_ROLES)),
) -> ApplicantListResponse:
    _, db = user_and_db

    filters = []
    if current_status is not None:
        filters.append(Applicant.current_status == current_status)
    if program is not None:
        filters.append(Applicant.program == program)
    if intake_cycle is not None:
        filters.append(Applicant.intake_cycle == intake_cycle)

    count_query = select(func.count()).select_from(Applicant)
    for f in filters:
        count_query = count_query.where(f)
    total = (await db.execute(count_query)).scalar_one()

    list_query = (
        select(Applicant).order_by(Applicant.created_at.asc(), Applicant.id.asc()).limit(limit).offset(offset)
    )
    for f in filters:
        list_query = list_query.where(f)
    rows = (await db.execute(list_query)).scalars().all()

    return ApplicantListResponse(
        items=[_to_summary(a) for a in rows], total=total, limit=limit, offset=offset
    )


# `_ALL_STATUSES` in declaration order (matches `ApplicationStatus`'s own
# pipeline order, the same order `frontend/src/applicants/statusTransitions.ts`
# already lists them in) -- iterated unconditionally below so every status
# bucket is always present in the response (`count: 0` for a status with no
# rows in this caller's own RLS-scoped view), matching the
# `PaymentClaimStatusBreakdown`/`ReconciliationCycle` "always-present
# bucket" convention `app.routers.reconciliation` already established.
_ALL_STATUSES: tuple[ApplicationStatus, ...] = tuple(ApplicationStatus)


@router.get("/summary", response_model=ApplicantSummaryTotals)
async def get_applicant_summary(
    user_and_db: tuple[User, AsyncSession] = Depends(require_role_session(*_ALL_ROLES)),
) -> ApplicantSummaryTotals:
    """Per-status applicant counts for the Home dashboard (Module 14).

    **Route ordering.** Declared here, immediately after `list_applicants`
    and before `get_applicant`'s `/{applicant_id}` route -- FastAPI matches
    routes in declaration order, and a literal `/applicants/summary` path
    registered *after* the `/{applicant_id}` UUID-typed route would either
    404 (Starlette's own UUID converter rejecting the literal string
    `"summary"`) or, worse, silently succeed with a confusing validation
    error, instead of ever reaching this handler. Declaring it before the
    dynamic route removes the ambiguity entirely rather than relying on a
    web framework's specific route-matching-order guarantee.

    **RBAC/RLS: reuses `applicant`'s own existing policy, adds nothing new.**
    Same `require_role_session(*_ALL_ROLES)` no-op-role-gate as every other
    route in this file (see the module docstring) -- the actual visibility
    narrowing is entirely `applicant`'s own `role_visibility` RLS policy,
    unchanged since Module 01/03: `SUPER_ADMIN`/`ADMISSIONS_MANAGER`/
    `FINANCE_STAFF`/`FINANCE_MANAGER`/`AUDITOR` see every row,
    `ADMISSIONS_COUNSELOR` sees only rows where `assigned_counselor_id` is
    their own id. This endpoint does not add a single line of new RLS or
    RBAC code -- the exact reuse the module prompt asked for. A counselor
    calling this endpoint gets counts scoped to only their own assigned
    applicants automatically, for the same reason `GET /applicants` already
    does; a manager or admin sees the real total across everyone.

    **SQL-level aggregation only, matching `app.routers.reconciliation`'s
    own discipline exactly.** One query,
    `GROUP BY current_status` with `func.count()`, no join at all (unlike
    reconciliation's two-query join-avoidance dance, there is nothing to
    fan out here -- this is a single-table aggregate over `applicant`
    itself), and no Python-side summation of `applicant` rows anywhere in
    this function. `total` is computed by summing the already-grouped
    `by_status` counts in Python (`sum(count for _, count in rows)`), the
    same "sum the already-aggregated array, don't re-query" pattern
    `ReconciliationTotals` uses for the identical drift-proofing reason:
    `total == sum(by_status)` is a structural guarantee of this function's
    own control flow, not a second SQL round-trip that could disagree with
    the first under a future edit.
    """
    _, db = user_and_db

    query = (
        select(Applicant.current_status, func.count(Applicant.id))
        .group_by(Applicant.current_status)
    )
    rows = (await db.execute(query)).all()
    counts_by_status: dict[ApplicationStatus, int] = {status: count for status, count in rows}

    by_status = [
        ApplicantStatusBreakdown(status=s, count=counts_by_status.get(s, 0))
        for s in _ALL_STATUSES
    ]
    total = sum(bucket.count for bucket in by_status)

    return ApplicantSummaryTotals(total=total, by_status=by_status)


@router.get("/{applicant_id}", response_model=ApplicantDetail)
async def get_applicant(
    applicant_id: uuid.UUID,
    user_and_db: tuple[User, AsyncSession] = Depends(require_role_session(*_ALL_ROLES)),
) -> ApplicantDetail:
    _, db = user_and_db

    result = await db.execute(select(Applicant).where(Applicant.id == applicant_id))
    applicant = result.scalar_one_or_none()
    if applicant is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "applicant not found")

    return ApplicantDetail(
        **_to_summary(applicant).model_dump(),
        import_batch_id=applicant.import_batch_id,
    )


@router.get("/{applicant_id}/status-history", response_model=StatusHistoryResponse)
async def get_applicant_status_history(
    applicant_id: uuid.UUID,
    user_and_db: tuple[User, AsyncSession] = Depends(require_role_session(*_ALL_ROLES)),
) -> StatusHistoryResponse:
    _, db = user_and_db

    # The applicant is fetched first, RLS-scoped exactly like the detail
    # route above -- an applicant invisible to this caller must 404 here
    # too, not merely return an empty history list (which would otherwise
    # be indistinguishable from "this applicant genuinely has no status
    # events yet," a real and valid state for a just-imported applicant).
    applicant_result = await db.execute(select(Applicant.id).where(Applicant.id == applicant_id))
    if applicant_result.scalar_one_or_none() is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "applicant not found")

    events_result = await db.execute(
        select(ApplicationStatusEvent)
        .where(ApplicationStatusEvent.applicant_id == applicant_id)
        .order_by(ApplicationStatusEvent.created_at.asc())
    )
    events = events_result.scalars().all()

    return StatusHistoryResponse(
        items=[
            StatusHistoryEvent(
                id=e.id,
                applicant_id=e.applicant_id,
                from_status=e.from_status,
                to_status=e.to_status,
                changed_by=e.changed_by,
                note=e.note,
                created_at=e.created_at,
            )
            for e in events
        ]
    )


@router.get("/{applicant_id}/finance", response_model=ApplicantFinanceResponse)
async def get_applicant_finance(
    applicant_id: uuid.UUID,
    user_and_db: tuple[User, AsyncSession] = Depends(require_role_session(*_ALL_ROLES)),
) -> ApplicantFinanceResponse:
    _, db = user_and_db

    # Deliberately does NOT first check applicant visibility the way
    # status-history does above. finance_record's own RLS policy is a
    # narrower, different allowlist than applicant's (see module
    # docstring) -- a manager or counselor who can plainly see the
    # applicant itself still gets 404 here once the finance_record read
    # below comes back empty, and that 404 is correct: to this caller,
    # under this table's own policy, no finance record exists to view.
    # Checking applicant visibility separately first would only produce
    # a misleading 404 message ("applicant not found") for a case where
    # the applicant is very much visible -- the finance_record is what
    # is actually missing/invisible.
    finance_result = await db.execute(
        select(FinanceRecord).where(FinanceRecord.applicant_id == applicant_id)
    )
    finance_record = finance_result.scalar_one_or_none()
    if finance_record is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "finance record not found")

    claims_result = await db.execute(
        select(PaymentClaim)
        .where(PaymentClaim.finance_record_id == finance_record.id)
        .order_by(PaymentClaim.created_at.asc())
    )
    claims = claims_result.scalars().all()

    return ApplicantFinanceResponse(
        finance_record_id=finance_record.id,
        applicant_id=finance_record.applicant_id,
        total_fee_due=finance_record.total_fee_due,
        total_paid=finance_record.total_paid,
        payment_claims=[
            PaymentClaimDetail(
                id=c.id,
                finance_record_id=c.finance_record_id,
                amount=c.amount,
                status=c.status,
                payment_mode=c.payment_mode,
                reference_number=c.reference_number,
                submitted_by=c.submitted_by,
                confirmed_by=c.confirmed_by,
                confirmed_at=c.confirmed_at,
                note=c.note,
                created_at=c.created_at,
            )
            for c in claims
        ],
    )
