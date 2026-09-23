"""Payment-claim submit/confirm/reject endpoints, on top of the
`finance_record`/`payment_claim` tables and triggers that already exist
from Modules 01/02/03's own migration (`0009_payment_claim_workflow`).

**Single transaction, no mid-request commit, in either endpoint's normal
path.** `require_role_session` (`app.core.deps`) yields `(user, db)` from
the one RLS-scoped transaction `get_scoped_session` opened for the
request; every read and write below happens in that transaction, and
neither endpoint calls `db.commit()` before returning -- unlike Module
02's Defect 3 fix (which had a real reason to persist a `FAILED` batch
row before raising), neither of these endpoints has a partial state worth
persisting ahead of a failure: a rejected submit or a rejected
confirm/reject attempt has written nothing yet, so there is nothing to
save before the 4xx response. `get_scoped_session`'s own docstring (and
`app/core/db.py`'s `open_scoped_session`) documents, with live
verification, exactly what a mid-request commit would do here if one were
ever added carelessly -- worth re-reading before changing this file.

**Submit (`POST /finance/payment-claims`).** `SUPER_ADMIN`, `FINANCE_STAFF`,
`FINANCE_MANAGER` may submit. `submitted_by` is taken from the
authenticated session's own user id, never from the request body -- see
`app.schemas.payment_claim`'s own docstring for why. A finance_record id
that RLS hides from the caller (should not happen in practice, since every
role permitted to submit already has `finance_record_select` access, but
checked explicitly rather than assumed) or that genuinely does not exist
is reported as 404, matching this project's established RLS-invisible-is-
404 convention (`app.routers.status`).

**Confirm/reject (`POST /finance/payment-claims/{id}/confirm` and
`/reject`).** `FINANCE_MANAGER`/`SUPER_ADMIN` only -- `FINANCE_STAFF` may
submit but never resolve any claim, including one submitted by a
different staff member, matching the maker-checker separation the RLS
design (and the database's own `CHECK` constraint) already encode. Before
touching the database, the maker-checker conflict
(`claim.submitted_by == user.id`) is checked at the application layer and
rejected with 422 naming the conflict -- **not** left to surface as the
database's own `ck_payment_claim_distinct_submitter_confirmer` `CHECK`
constraint violation, which would otherwise reach the client as an
unhandled `IntegrityError` (a 500), violating this project's standing
rule that a business-logic rejection is always a 422, never a 500. The
`CHECK` constraint itself is left in place, unchanged, as the
database-level backstop this project's general preference for
defense-in-depth already established (ADR-07's reasoning: a guarantee
enforced only by an application-layer check is one omitted call path away
from being wrong) -- this endpoint's own check is the first line, not the
only one.

Confirming a claim (`status -> CONFIRMED`) is the only write either
endpoint performs against `payment_claim` beyond the status/`confirmed_by`/
`confirmed_at` update itself; the parent `finance_record.total_paid`
rollup happens entirely inside
`payment_claim_confirmed_increments_total_paid()` (migration 0009), fired
by the database on the same `UPDATE`, without this router importing or
touching `finance_record` at all -- the same pattern
`app.routers.status` already established for the `finance_record`
auto-create trigger.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import require_role_session
from app.models.enums import PaymentClaimStatus, RoleCode
from app.models.finance_record import FinanceRecord
from app.models.payment_claim import PaymentClaim
from app.models.user import User
from app.schemas.payment_claim import (
    PaymentClaimResolveRequest,
    PaymentClaimResponse,
    PaymentClaimSubmitRequest,
)
from app.schemas.reads import PaymentClaimDetail, PaymentClaimListResponse

router = APIRouter(prefix="/finance/payment-claims", tags=["finance"])

# Same four roles as payment_claim's own role_visibility RLS policy
# (migration 0003/0009). The list endpoint (module 04) enforces this
# explicitly at the application layer, ahead of RLS, so a role outside
# this allowlist gets a clean 403 -- not a 200 with an empty `items` list
# that would otherwise be indistinguishable from "you're allowed to look,
# there's just nothing to see." The table's own RLS policy would produce
# exactly that empty-list result if this role check were absent (RLS
# fails closed, never raises), but for a *list* endpoint specifically
# (unlike the single-applicant reads in `applicants_read.py`, where "no
# role restriction, let RLS narrow the rows" is the deliberate design),
# an explicit 403 is the more honest response for a role that was never
# meant to reach this endpoint at all -- verified live which of the two
# actually fires; see the module-04 report.
_LIST_ROLES = (
    RoleCode.SUPER_ADMIN,
    RoleCode.FINANCE_STAFF,
    RoleCode.FINANCE_MANAGER,
    RoleCode.AUDITOR,
)


def _to_response(claim: PaymentClaim) -> PaymentClaimResponse:
    return PaymentClaimResponse(
        id=claim.id,
        finance_record_id=claim.finance_record_id,
        amount=claim.amount,
        status=claim.status,
        payment_mode=claim.payment_mode,
        reference_number=claim.reference_number,
        submitted_by=claim.submitted_by,
        confirmed_by=claim.confirmed_by,
        confirmed_at=claim.confirmed_at,
        note=claim.note,
    )


@router.get("", response_model=PaymentClaimListResponse)
async def list_payment_claims(
    limit: int = Query(25, ge=1, le=100),
    offset: int = Query(0, ge=0),
    claim_status: PaymentClaimStatus | None = Query(None, alias="status"),
    user_and_db: tuple[User, AsyncSession] = Depends(require_role_session(*_LIST_ROLES)),
) -> PaymentClaimListResponse:
    """Standalone list, independent of any single applicant/finance_record
    -- for finance/audit roles to triage without needing an applicant id
    first. Filterable by `status` (`PENDING`/`CONFIRMED`/`REJECTED`).

    RLS still applies underneath this endpoint's own `_LIST_ROLES` role
    gate (the two are not redundant: the role gate rejects an
    out-of-scope caller with a 403 before any query runs; RLS is what
    would otherwise silently narrow the *rows* for an in-scope caller if
    a future policy ever became row-level rather than role-level for this
    table -- today `payment_claim`'s policy is a flat role allowlist with
    no per-row narrowing, so every role in `_LIST_ROLES` sees every claim,
    but the RLS layer is not bypassed to get that result).
    """
    _, db = user_and_db

    filters = []
    if claim_status is not None:
        filters.append(PaymentClaim.status == claim_status)

    count_query = select(func.count()).select_from(PaymentClaim)
    for f in filters:
        count_query = count_query.where(f)
    total = (await db.execute(count_query)).scalar_one()

    list_query = (
        select(PaymentClaim)
        .order_by(PaymentClaim.created_at.asc(), PaymentClaim.id.asc())
        .limit(limit)
        .offset(offset)
    )
    for f in filters:
        list_query = list_query.where(f)
    rows = (await db.execute(list_query)).scalars().all()

    return PaymentClaimListResponse(
        items=[
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
            for c in rows
        ],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post("", response_model=PaymentClaimResponse)
async def submit_payment_claim(
    body: PaymentClaimSubmitRequest,
    user_and_db: tuple[User, AsyncSession] = Depends(
        require_role_session(RoleCode.SUPER_ADMIN, RoleCode.FINANCE_STAFF, RoleCode.FINANCE_MANAGER)
    ),
) -> PaymentClaimResponse:
    user, db = user_and_db

    result = await db.execute(
        select(FinanceRecord).where(FinanceRecord.id == body.finance_record_id)
    )
    finance_record = result.scalar_one_or_none()
    if finance_record is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "finance record not found")

    claim = PaymentClaim(
        finance_record_id=finance_record.id,
        amount=body.amount,
        status=PaymentClaimStatus.PENDING,
        payment_mode=body.payment_mode,
        reference_number=body.reference_number,
        submitted_by=user.id,
    )
    db.add(claim)
    await db.flush()
    await db.refresh(claim)

    return _to_response(claim)


async def _resolve_claim(
    claim_id: uuid.UUID,
    body: PaymentClaimResolveRequest,
    new_status: PaymentClaimStatus,
    user: User,
    db: AsyncSession,
) -> PaymentClaimResponse:
    result = await db.execute(select(PaymentClaim).where(PaymentClaim.id == claim_id))
    claim = result.scalar_one_or_none()
    if claim is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "payment claim not found")

    if claim.status != PaymentClaimStatus.PENDING:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"payment claim is not PENDING (current status: {claim.status.value})",
        )

    # Maker-checker: rejected at the application layer, before this ever
    # reaches the database's own CHECK constraint -- see module docstring
    # for why a raw IntegrityError here would be the wrong failure shape.
    if claim.submitted_by == user.id:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "cannot confirm or reject a payment claim you submitted yourself "
            "(maker-checker separation)",
        )

    claim.status = new_status
    claim.confirmed_by = user.id
    claim.confirmed_at = func.now()
    if body.note is not None:
        claim.note = body.note

    await db.flush()
    await db.refresh(claim)

    return _to_response(claim)


@router.post("/{claim_id}/confirm", response_model=PaymentClaimResponse)
async def confirm_payment_claim(
    claim_id: uuid.UUID,
    body: PaymentClaimResolveRequest,
    user_and_db: tuple[User, AsyncSession] = Depends(
        require_role_session(RoleCode.SUPER_ADMIN, RoleCode.FINANCE_MANAGER)
    ),
) -> PaymentClaimResponse:
    user, db = user_and_db
    return await _resolve_claim(claim_id, body, PaymentClaimStatus.CONFIRMED, user, db)


@router.post("/{claim_id}/reject", response_model=PaymentClaimResponse)
async def reject_payment_claim(
    claim_id: uuid.UUID,
    body: PaymentClaimResolveRequest,
    user_and_db: tuple[User, AsyncSession] = Depends(
        require_role_session(RoleCode.SUPER_ADMIN, RoleCode.FINANCE_MANAGER)
    ),
) -> PaymentClaimResponse:
    user, db = user_and_db
    return await _resolve_claim(claim_id, body, PaymentClaimStatus.REJECTED, user, db)
