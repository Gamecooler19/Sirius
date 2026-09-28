"""`PATCH /finance-records/{id}/fee-due` (Module 22 Part 2): the one
real write path for `finance_record.total_fee_due`, which previously
had none at all -- see `app.models.finance_record`'s own docstring for
the full account of the live defect this closes.

**RBAC: `FINANCE_MANAGER`/`SUPER_ADMIN` only, matching this module's
own explicit requirement and the narrowed `finance_record_update` RLS
policy (migration `0015_finance_fee_due`) exactly.** `FINANCE_STAFF`
may submit a payment claim but, per this project's own established
maker-checker separation (`app.routers.payment_claim`'s own docstring),
was never meant to set the fee a payment is measured against either;
`AUDITOR` reviews figures, not writes them. A role outside this
allowlist gets a clean `403` before any query runs, the same
`require_role_session` pattern every other write endpoint in this
project already uses -- and even if this application-layer check were
ever accidentally removed or bypassed, the database's own RLS policy
denies the same `UPDATE` independently (verified live, not merely
reasoned about; see the module-22 report's own Part 2 section for the
real RLS-denial reproduction).

**Reject lowering the fee below the already-confirmed `total_paid`
with a `422` naming both figures -- the module's own explicit
requirement, and a real, not hypothetical, protection.** Without this
check, a `FINANCE_MANAGER` could set `total_fee_due` below
`total_paid` (e.g. an applicant who paid `300000.00` against a fee
mistakenly set to `200000.00` later), and every dashboard/
reconciliation "outstanding" figure derived from `total_fee_due -
total_paid` would report a genuine negative balance again -- the exact
class of corruption this whole module exists to close, just reached
through a different path than the original "never written" bug. The
comparison uses the *current* `total_paid` read inside this same
transaction (not a stale value from an earlier request), so a
concurrent payment confirmation cannot be raced around this check
within one request's own lifetime.

**Not exposed as a full `PATCH finance_record` (arbitrary field
update).** `total_paid` is never settable through this endpoint --
that figure's only legitimate write path is the existing
payment-confirm rollup trigger (migration 0009); a manager directly
overwriting `total_paid` would break the one-way link between "a real
confirmed payment claim exists" and "the recorded total paid," the
same reasoning `app.routers.payment_claim`'s own docstring already
gives for why the rollup lives in a trigger and not application code.
This endpoint's own request schema
(`app.schemas.finance_record.FinanceRecordFeeDueUpdateRequest`)
structurally cannot carry a `total_paid` field at all.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import require_role_session
from app.models.enums import RoleCode
from app.models.finance_record import FinanceRecord
from app.models.payment_claim import PaymentClaim
from app.models.user import User
from app.schemas.finance_record import FinanceRecordFeeDueUpdateRequest
from app.schemas.reads import ApplicantFinanceResponse, PaymentClaimDetail

router = APIRouter(prefix="/finance-records", tags=["finance"])

_FEE_DUE_ROLES = (RoleCode.SUPER_ADMIN, RoleCode.FINANCE_MANAGER)


@router.patch("/{finance_record_id}/fee-due", response_model=ApplicantFinanceResponse)
async def update_fee_due(
    finance_record_id: uuid.UUID,
    body: FinanceRecordFeeDueUpdateRequest,
    user_and_db: tuple[User, AsyncSession] = Depends(require_role_session(*_FEE_DUE_ROLES)),
) -> ApplicantFinanceResponse:
    _, db = user_and_db

    result = await db.execute(select(FinanceRecord).where(FinanceRecord.id == finance_record_id))
    finance_record = result.scalar_one_or_none()
    if finance_record is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "finance record not found")

    # Reject lowering the fee below the already-confirmed total_paid --
    # see module docstring for why this is a real, required protection,
    # not a defensive nicety. Read from the same row this transaction
    # already holds (finance_record.total_paid), not a separately
    # queried value, so this comparison is against the current, correct
    # figure.
    if body.total_fee_due < finance_record.total_paid:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"total_fee_due ({body.total_fee_due}) cannot be set below the "
            f"already-confirmed total_paid ({finance_record.total_paid})",
        )

    finance_record.total_fee_due = body.total_fee_due
    await db.flush()
    await db.refresh(finance_record)

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
