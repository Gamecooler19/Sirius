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
    ApplicantSummary,
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
