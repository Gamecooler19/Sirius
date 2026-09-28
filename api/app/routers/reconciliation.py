"""Finance reconciliation: totals by intake cycle, for finance/audit
roles to see where the money stands without summing raw `payment_claim`
rows by hand.

**RBAC.** `SUPER_ADMIN`/`FINANCE_STAFF`/`FINANCE_MANAGER`/`AUDITOR`,
enforced as an explicit `require_role_session` allowlist -- the same
`_LIST_ROLES` shape Module 04's `payment_claim`/`import_batch` list
endpoints already established, and for the identical reason stated in
both of those modules' own reports: for a *list/aggregate* endpoint, an
out-of-scope role getting a clean 403 is the honest response, not a
misleadingly well-formed `200` with every number at zero (which is
exactly what this endpoint would silently return for, say,
`ADMISSIONS_MANAGER` if this role check were absent -- `ADMISSIONS_MANAGER`
is not in `finance_record`'s own RLS allowlist, so an unscoped-by-role
call would see zero `finance_record` rows and report a confusing "no
data" rather than "you cannot see this"). This allowlist happens to be
identical to `finance_record`/`payment_claim`'s own RLS policies (Module
01/03), so for every role actually admitted here, RLS narrows nothing
further -- the two layers agree, they are not doing different jobs for
this particular endpoint the way `applicants_read.py`'s RLS-only design
does for `/applicants`.

**Why two GROUP BY queries, not one.** A single query joining
`applicant -> finance_record -> payment_claim` and then `SUM`-ing
`finance_record.total_fee_due`/`total_paid` in the same `GROUP BY
intake_cycle` would double- (or N-times-) count every `finance_record`
that has more than one `payment_claim` -- the join fans a `finance_record`
row out once per matching `payment_claim`, and `SUM(total_fee_due)` over
that fanned-out result counts each `finance_record`'s own `total_fee_due`
once per claim, not once per record. Module 03's own applicant (one
`finance_record`, two `payment_claim`s) is the live proof case: a naive
single-join aggregate would report `total_fee_due` as `1,000,000.00`
(500000 x 2 claims) instead of the correct `500000.00`. Query A
aggregates `finance_record` totals grouped by cycle with no join to
`payment_claim` at all, so it cannot fan out. Query B aggregates
`payment_claim` counts/amounts by cycle *and* status, joined only as far
as `finance_record` (needed to reach `applicant.intake_cycle` at all,
since `finance_record` itself carries no cycle column) -- this join can
fan `finance_record` out across its claims, but Query B never sums
anything at the `finance_record` level, only at the `payment_claim`
level, so the fan-out is exactly the grouping this query wants, not a bug.
Both queries do their own summing entirely in SQL (`GROUP BY`,
`func.sum`, `func.count`) -- no row-level Python summation for either --
consistent with this module's own instruction and the precedent
`app.routers.applicants_read`'s `COUNT(*)` already set in Module 04.
Combining the two already-aggregated result sets by `intake_cycle` key in
Python below is assembly of pre-summed rows, not a second layer of
summation.

**Why `totals` is computed from `cycles`, not a third independent SQL
aggregate.** A third query re-aggregating across all cycles combined
would compute the same numbers by a different code path than the
per-cycle array, and the two could silently drift apart under a future
edit to one query but not the other -- caught by neither type checker nor
test unless someone thinks to compare them. Summing the already-built
`cycles` list in Python instead makes `totals == sum(cycles)` a structural
guarantee of this function's own control flow, not a fact that merely
happens to hold today and could stop holding tomorrow.

**Module 22 Part 2: `fee_not_set_count` per cycle/totals.** `total_fee_due`'s
own `SUM` already correctly ignores `NULL` (unset) records without any
special-casing here -- Postgres's `SUM`/`COALESCE` already do the right
thing for that. `fee_not_set_count` is a second aggregate, computed in
the same Query A via `func.count` filtered to `total_fee_due IS NULL`,
so a caller can tell "this cycle's total is the complete picture" apart
from "N records in this cycle have no decided fee yet, so this total
understates the true figure" -- see `app.schemas.reads.ReconciliationCycle`'s
own docstring for the full account of why this is a real, required
distinction, not a redundant convenience field.
"""

from collections import defaultdict
from decimal import Decimal

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import require_role_session
from app.models.applicant import Applicant
from app.models.enums import PaymentClaimStatus, RoleCode
from app.models.finance_record import FinanceRecord
from app.models.payment_claim import PaymentClaim
from app.models.user import User
from app.schemas.reads import (
    PaymentClaimStatusBreakdown,
    ReconciliationCycle,
    ReconciliationResponse,
    ReconciliationTotals,
)

router = APIRouter(prefix="/finance/reconciliation", tags=["finance"])

_ROLES = (
    RoleCode.SUPER_ADMIN,
    RoleCode.FINANCE_STAFF,
    RoleCode.FINANCE_MANAGER,
    RoleCode.AUDITOR,
)

_ALL_CLAIM_STATUSES = (
    PaymentClaimStatus.PENDING,
    PaymentClaimStatus.CONFIRMED,
    PaymentClaimStatus.REJECTED,
)


@router.get("", response_model=ReconciliationResponse)
async def get_reconciliation(
    user_and_db: tuple[User, AsyncSession] = Depends(require_role_session(*_ROLES)),
) -> ReconciliationResponse:
    _, db = user_and_db

    # Query A: finance_record totals per cycle. No join to payment_claim
    # -- see module docstring for why joining it here would fan out and
    # over-count total_fee_due/total_paid. fee_not_set_count (Module 22
    # Part 2) is a plain conditional count in the same query, not a
    # separate round trip.
    finance_query = (
        select(
            Applicant.intake_cycle,
            func.count(FinanceRecord.id),
            func.count(FinanceRecord.id).filter(FinanceRecord.total_fee_due.is_(None)),
            func.coalesce(func.sum(FinanceRecord.total_fee_due), 0),
            func.coalesce(func.sum(FinanceRecord.total_paid), 0),
        )
        .select_from(FinanceRecord)
        .join(Applicant, FinanceRecord.applicant_id == Applicant.id)
        .group_by(Applicant.intake_cycle)
    )
    finance_rows = (await db.execute(finance_query)).all()

    # Query B: payment_claim counts/amounts per cycle, per status.
    claims_query = (
        select(
            Applicant.intake_cycle,
            PaymentClaim.status,
            func.count(PaymentClaim.id),
            func.coalesce(func.sum(PaymentClaim.amount), 0),
        )
        .select_from(PaymentClaim)
        .join(FinanceRecord, PaymentClaim.finance_record_id == FinanceRecord.id)
        .join(Applicant, FinanceRecord.applicant_id == Applicant.id)
        .group_by(Applicant.intake_cycle, PaymentClaim.status)
    )
    claims_rows = (await db.execute(claims_query)).all()

    # claims_by_cycle[cycle][status] = (count, amount)
    claims_by_cycle: dict[str, dict[PaymentClaimStatus, tuple[int, Decimal]]] = defaultdict(dict)
    for cycle, claim_status, count, amount in claims_rows:
        claims_by_cycle[cycle][claim_status] = (count, amount)

    cycles: list[ReconciliationCycle] = []
    for cycle, fr_count, fee_not_set_count, fee_due, paid in finance_rows:
        breakdown = [
            PaymentClaimStatusBreakdown(
                status=s,
                count=claims_by_cycle.get(cycle, {}).get(s, (0, Decimal(0)))[0],
                amount=claims_by_cycle.get(cycle, {}).get(s, (0, Decimal(0)))[1],
            )
            for s in _ALL_CLAIM_STATUSES
        ]
        cycles.append(
            ReconciliationCycle(
                intake_cycle=cycle,
                finance_record_count=fr_count,
                fee_not_set_count=fee_not_set_count,
                total_fee_due=fee_due,
                total_paid=paid,
                outstanding=fee_due - paid,
                claims_by_status=breakdown,
            )
        )

    cycles.sort(key=lambda c: c.intake_cycle)

    # totals: sum of the cycles array itself, not a separate SQL query --
    # see module docstring for why this is the drift-proof choice.
    totals_by_status: dict[PaymentClaimStatus, list[Decimal | int]] = {
        s: [0, Decimal(0)] for s in _ALL_CLAIM_STATUSES
    }
    total_fr_count = 0
    total_fee_not_set_count = 0
    total_fee_due = Decimal(0)
    total_paid = Decimal(0)
    for cycle in cycles:
        total_fr_count += cycle.finance_record_count
        total_fee_not_set_count += cycle.fee_not_set_count
        total_fee_due += cycle.total_fee_due
        total_paid += cycle.total_paid
        for bucket in cycle.claims_by_status:
            totals_by_status[bucket.status][0] += bucket.count
            totals_by_status[bucket.status][1] += bucket.amount

    totals = ReconciliationTotals(
        finance_record_count=total_fr_count,
        fee_not_set_count=total_fee_not_set_count,
        total_fee_due=total_fee_due,
        total_paid=total_paid,
        outstanding=total_fee_due - total_paid,
        claims_by_status=[
            PaymentClaimStatusBreakdown(status=s, count=totals_by_status[s][0], amount=totals_by_status[s][1])
            for s in _ALL_CLAIM_STATUSES
        ],
    )

    return ReconciliationResponse(cycles=cycles, totals=totals)
