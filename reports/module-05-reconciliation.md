# Module 05: Reconciliation — completion report

## Scope

Build `GET /finance/reconciliation`: finance totals grouped by
`intake_cycle` — summed `total_fee_due`/`total_paid` across every
`finance_record` in each cycle (joining through `applicant.intake_cycle`,
since `finance_record` itself carries no cycle column), the derived
`outstanding` (fee_due minus paid), a `finance_record` count, a
`payment_claim` count/amount breakdown by status
(`PENDING`/`CONFIRMED`/`REJECTED`) for claims against `finance_record`s in
that cycle, and a top-level `totals` object summing all of the above
across every cycle combined. SQL-level aggregation throughout, no
row-level Python summation of raw query results. Explicit
application-layer role-gate (`SUPER_ADMIN`/`FINANCE_STAFF`/
`FINANCE_MANAGER`/`AUDITOR`), matching the shape Module 04's two list
endpoints already established.

## What was built

### `app/schemas/reads.py` additions

`PaymentClaimStatusBreakdown` (`status`, `count`, `amount`),
`ReconciliationCycle` (`intake_cycle` plus the same
count/fee_due/paid/outstanding/breakdown shape), `ReconciliationTotals`
(identical shape minus `intake_cycle`), `ReconciliationResponse`
(`cycles: list[ReconciliationCycle]`, `totals: ReconciliationTotals`).
`claims_by_status` always carries all three `PaymentClaimStatus` values
for every cycle and for `totals`, even when a status has zero claims in
that scope (`count: 0, amount: 0` rather than omitting the status
entirely) — verified live below.

### `app/routers/reconciliation.py`

**Two `GROUP BY` queries, not one, and why.** A single query joining
`applicant -> finance_record -> payment_claim` and summing
`finance_record.total_fee_due`/`total_paid` in the same `GROUP BY
intake_cycle` would double-count any `finance_record` with more than one
`payment_claim` — the join fans a `finance_record` row out once per
matching claim, and `SUM` over the fanned-out result counts that
`finance_record`'s own totals once per claim, not once per record.
Module 03's own applicant (one `finance_record`, two `payment_claim`s) is
the concrete case this would break on: a naive single-join aggregate
would report `total_fee_due` as `1,000,000.00` (500000 × 2) instead of
`500000.00`. **Query A** aggregates `finance_record` totals grouped by
cycle with no join to `payment_claim` at all — `SELECT
applicant.intake_cycle, COUNT(finance_record.id),
SUM(finance_record.total_fee_due), SUM(finance_record.total_paid) ...
GROUP BY applicant.intake_cycle` — so it cannot fan out. **Query B**
aggregates `payment_claim` counts/amounts grouped by cycle *and* status,
joined through `finance_record` only as far as needed to reach
`applicant.intake_cycle` — this join does fan `finance_record` out
across its claims, but Query B never sums anything at the
`finance_record` level, only at the `payment_claim` level, so the
fan-out is exactly the grouping this query wants. Both queries do all
summing in SQL (`func.sum`, `func.count`, `GROUP BY`) — consistent with
this module's own instruction and the `COUNT(*)` precedent
`app.routers.applicants_read` already set in Module 04. The two
already-aggregated result sets are combined by `intake_cycle` key in
Python — assembly of pre-summed rows, not a second layer of summation.

**`totals` computed from `cycles`, not a third SQL query.** A third,
independently-aggregated "across all cycles" query would compute the same
numbers through a different code path than the per-cycle array, with no
structural guarantee the two stay in agreement under a future edit to
one but not the other. `totals` is instead built by summing the
already-constructed `cycles` list in Python, making `totals ==
sum(cycles)` a property of this function's own control flow rather than
a fact that merely happens to hold today.

**RBAC.** `require_role_session(SUPER_ADMIN, FINANCE_STAFF,
FINANCE_MANAGER, AUDITOR)` — the identical `_LIST_ROLES` shape and
reasoning Module 04's `payment_claim`/`import_batch` list endpoints
already established: an out-of-scope role gets a clean 403, not a
misleadingly well-formed `200` with every figure at zero (which is what
this endpoint would return for e.g. `ADMISSIONS_MANAGER` if this check
were absent, since that role is outside `finance_record`'s own RLS
allowlist and would see zero rows without any application-layer signal
that the emptiness means "you cannot see this" rather than "there is
nothing here").

`app/main.py` registers the new router.

## Verification against the live stack

All verification is real HTTP calls (`curl`) against the running `api`
container, cross-checked against direct `psql` queries run *before* each
HTTP call as independent ground truth — not derived from the endpoint's
own output. No new seed data or fixtures: all applicants/finance_records/
payment_claims used were either already sitting in the stack from
Modules 03/04, or created by driving *already-seeded* Module 04
applicants through the *already-verified* real `POST
/applicants/{id}/status` and `POST /finance/payment-claims`(`/confirm`)
endpoints — not by inserting rows directly.

### Exact match against Module 03's own recorded numbers

Before any HTTP call, `psql` independently confirmed the ground truth for
`Fall2026` (the cycle Module 03's applicant/finance_record/claims belong
to): `finance_record` count `1`, `SUM(total_fee_due) = 500000.00`,
`SUM(total_paid) = 100000.00`; `payment_claim` breakdown `CONFIRMED: 1
claim, 100000.00` and `REJECTED: 1 claim, 50000.00` — all four numbers
matching Module 03's own report (`reports/module-03-payment-workflow.md`)
exactly, byte-for-byte on the decimal values. `GET
/finance/reconciliation` as `FINANCE_STAFF`, before any additional data
was added, returned the identical row: `{"intake_cycle": "Fall2026",
"finance_record_count": 1, "total_fee_due": "500000.00", "total_paid":
"100000.00", "outstanding": "400000.00", "claims_by_status": [{"status":
"PENDING", "count": 0, "amount": "0"}, {"status": "CONFIRMED", "count":
1, "amount": "100000.00"}, {"status": "REJECTED", "count": 1, "amount":
"50000.00"}]}`. `outstanding = 400000.00 = 500000.00 - 100000.00`,
confirming the derived field's own arithmetic. `PENDING` correctly
present with `count: 0, amount: "0"` rather than being omitted, since
neither of Module 03's two claims is `PENDING`.

### Multi-cycle totals: sum of the array, not independent drift risk

The single-cycle case above cannot distinguish "totals correctly equals
the sum of cycles" from "totals happens to equal the one cycle because
there's only one" — a second cycle was needed to make this a real check,
using only already-seeded data and already-verified endpoints, not a
fresh fixture. One of Module 04's own seeded `Spring2027` applicants
(counselor B's `M4 Applicant B00`, still at `IMPORTED`) was walked
through the real `POST /applicants/{id}/status` endpoint,
`IMPORTED -> APPLIED -> IN_PROCESS -> ADMISSION_OFFERED ->
ADMISSION_TAKEN`, four genuine HTTP calls, firing the same
`applicant_create_finance_record()` trigger Module 02/03 already
verified. The resulting `finance_record`'s `total_fee_due` was set to
`200000.00` via direct `psql` (the only way to set this field today,
same as Module 03's own setup — no endpoint writes `total_fee_due`).
`FINANCE_STAFF` submitted a real `75000.00` `UPI` claim against it via
`POST /finance/payment-claims`; `FINANCE_MANAGER` confirmed it via `POST
/finance/payment-claims/{id}/confirm` — both real endpoint calls, not
direct inserts.

`psql` ground truth after this setup: `Fall2026` unchanged (1,
500000.00, 100000.00); `Spring2027` (1, 200000.00, 75000.00). Combined
claim breakdown: `CONFIRMED` 2 claims / `175000.00`, `REJECTED` 1 claim /
`50000.00`, `PENDING` 0.

`GET /finance/reconciliation` returned both cycle rows matching this
ground truth exactly, and a `totals` object of `{"finance_record_count":
2, "total_fee_due": "700000.00", "total_paid": "175000.00", "outstanding":
"525000.00", "claims_by_status": [{"status": "PENDING", "count": 0,
"amount": "0"}, {"status": "CONFIRMED", "count": 2, "amount":
"175000.00"}, {"status": "REJECTED", "count": 1, "amount": "50000.00"}]}`.
Checked field-by-field against the two cycle rows themselves, not merely
against `psql`: `2 = 1 + 1`; `700000.00 = 500000.00 + 200000.00`;
`175000.00 = 100000.00 + 75000.00`; `525000.00 = 400000.00 + 125000.00`
(each cycle's own `outstanding`); `CONFIRMED` `2 = 1 + 1` and `175000.00
= 100000.00 + 75000.00`; `REJECTED` `1 = 1 + 0` and `50000.00 = 50000.00
+ 0`. Every totals field is exactly the sum of the corresponding
per-cycle field — confirming the route's `totals`-from-`cycles`
computation the docstring documents actually holds, not merely that it
was written with that intent.

### Role-gate, tested against the adjacent-but-excluded role

Per this module's own instruction, tested against `ADMISSIONS_MANAGER`
specifically — a role with broad applicant visibility elsewhere in this
system (confirmed extensively in Module 04's own report, `total: 34`/`36`
across both counselors) but no actual claim to `finance_record`/
`payment_claim` data — rather than a role already known to be excluded.
`GET /finance/reconciliation` as `ADMISSIONS_MANAGER`: **403**,
`"insufficient role for this action"` — exactly the failure mode this
module's own design intentionally produces instead of the
misleadingly-well-formed `200`-with-every-figure-at-zero that an
RLS-only design would have returned for this role (`ADMISSIONS_MANAGER`
is outside `finance_record`'s own RLS allowlist).

Paired checks, all against the live stack:
- `FINANCE_MANAGER`: 200, identical correct two-cycle data.
- `AUDITOR`: 200, identical correct two-cycle data.
- `ADMISSIONS_COUNSELOR` (the role already known to be excluded, checked
  as a baseline sanity check, not the primary test per the module's own
  instruction): 403, same message.
- No session cookie at all: 401, `"not authenticated"` — confirmed this
  endpoint requires authentication before RBAC is even evaluated, same as
  every other protected route in this project.

### No sensitive-field leakage

`GET /openapi.json` searched for `password_hash`/`totp_secret_encrypted`
across the full schema including this module's new response models:
zero matches, consistent with Modules 01-04's own established pattern of
hand-declared Pydantic response models that never reference those
fields.

## Real defects found and fixed during this module

None. The endpoint's numbers matched Module 03's independently-recorded
report values exactly on the first live call, the multi-cycle totals
summed correctly on the first live call, and the role-gate behaved
exactly as designed against both the adjacent-claim role
(`ADMISSIONS_MANAGER`) and the baseline-excluded role
(`ADMISSIONS_COUNSELOR`). The two-query, no-fan-out design was reasoned
through *before* writing the query (documented in the router's own
docstring) specifically to avoid the double-counting failure mode Module
03's own two-claims-per-record data would have made trivially visible had
a naive single-join aggregate been written instead — the design choice
was made correctly up front rather than discovered as a defect during
verification.

## Cleanup

All curl cookie jars used for this module's live verification
(`m5_*_cookies.txt`) were deleted after verification completed; none
were staged or committed. The one additional `finance_record`/
`payment_claim` created during this module's verification (the
`Spring2027` applicant walked to `ADMISSION_TAKEN`, its `total_fee_due`
set via `psql`, its one claim submitted and confirmed via the real
endpoints) remains in the running dev stack's database, same as every
prior module's own test data — disposable Docker Compose dev state, not
committed to git, and itself a byproduct of exercising only real,
already-verified endpoints rather than a synthetic fixture.

## Definition of done

- [x] `GET /finance/reconciliation` — per-`intake_cycle` totals: finance
      record count, summed `total_fee_due`/`total_paid`, derived
      `outstanding`, `payment_claim` count/amount breakdown by status.
- [x] Top-level `totals` object summing across every cycle, computed from
      the per-cycle array itself (verified field-by-field to equal the
      sum, not merely asserted).
- [x] SQL-level `GROUP BY`/`SUM`/`COUNT` aggregation throughout, no
      row-level Python summation of raw rows — verified by design (two
      queries, each aggregated entirely in SQL) and live output matching
      independently-obtained `psql` ground truth.
- [x] Explicit application-layer role-gate
      (`SUPER_ADMIN`/`FINANCE_STAFF`/`FINANCE_MANAGER`/`AUDITOR`),
      matching Module 04's list-endpoint shape.
- [x] Live-verified against Module 03's own recorded numbers exactly
      (500000.00/100000.00, 1 CONFIRMED, 1 REJECTED) with zero
      discrepancy.
- [x] Live-verified multi-cycle totals-equals-sum-of-cycles using only
      already-seeded data driven through already-verified endpoints, not
      fresh fixtures.
- [x] Role-gate tested against `ADMISSIONS_MANAGER` (adjacent-claim role)
      specifically, confirmed 403 — not only against the
      already-known-excluded role.
- [x] No sensitive-field leakage, verified via the full OpenAPI schema.
- [x] Report committed as `reports/module-05-reconciliation.md`.
