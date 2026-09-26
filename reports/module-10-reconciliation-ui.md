# Module 10: Reconciliation dashboard — completion report

## Scope

Build the reconciliation dashboard in `frontend/`, wired to the real
`GET /finance/reconciliation` (Module 05) — no mocked data. A new page at
`/finance/reconciliation` (no placeholder existed at this route before
this module — `router.tsx` had no reconciliation entry at all) shows the
top-level `totals` object prominently as summary cards (finance-record
count, fee due, paid, outstanding, plus a card per claim status), then a
per-`intake_cycle` breakdown table below it with the same fields, sorted
alphabetically by cycle. Gated on `RECONCILIATION_ROLES`
(`SUPER_ADMIN`/`FINANCE_STAFF`/`FINANCE_MANAGER`/`AUDITOR`), copied
verbatim from `app.routers.reconciliation._ROLES`. This endpoint has no
pagination and no filters — no page controls or filter inputs were built
for it. A zero-count status (e.g., a cycle with no `REJECTED` claims yet)
renders as a real `0`/`0` in its own column, never omitted, matching what
the backend always includes per status per Module 05's own design.

## What was built

### Types (`src/api/types.ts` additions)

`PaymentClaimStatusBreakdown`, `ReconciliationCycle`,
`ReconciliationTotals`, `ReconciliationResponse` — all mirror
`api/app/schemas/reads.py`'s identically-named schemas field-for-field,
each with a docstring citing the exact backend schema it mirrors. Money
fields are typed `string` (the raw decimal string FastAPI/Pydantic
serializes a `Decimal` as, e.g. `"800000.00"`), matching how every other
money field already sitting in `types.ts` from Module 09
(`total_fee_due`, `total_paid`, `amount`) is typed — not narrowed to
`number`, which would silently lose precision or reformat a value the
backend never asked to have reformatted.

### Roles (`src/auth/roles.ts` addition)

`RECONCILIATION_ROLES` (`SUPER_ADMIN`, `FINANCE_STAFF`, `FINANCE_MANAGER`,
`AUDITOR`), copied verbatim from `app.routers.reconciliation._ROLES`. Its
docstring explicitly notes this membership is identical to the existing
`FINANCE_ROLES` constant today (both mirror the same backend RLS
allowlist per that router's own docstring) but is kept as its own named
constant rather than reused, matching this file's own established
convention of one constant per distinct backend `require_role_session`
call site (the same reasoning already applied to
`PAYMENT_SUBMIT_ROLES`/`PAYMENT_RESOLVE_ROLES` in Module 09, which also
happen to overlap in membership without being merged into one constant).

### Query hook (`src/finance/useReconciliation.ts`)

`useReconciliation()` — a single `GET /finance/reconciliation` call with
no parameters at all, since the endpoint takes none. The module's own
docstring calls this out explicitly as the reason this hook has no
`params` argument and no per-parameter query key, unlike every other list
hook in this codebase.

### Dashboard page (`src/finance/ReconciliationPage.tsx`)

A `TotalsCards` sub-component renders four top-row cards
(finance-record count, fee due, paid, outstanding) and three
per-status cards (`PENDING`/`CONFIRMED`/`REJECTED`, each showing its
count and amount) built from `totals.claims_by_status` via a helper that
falls back to `{count: 0, amount: "0"}` if a status were ever absent —
defensive against a future backend change, though live verification
below confirms the backend already always includes every status. Below
the cards, a `Table` with one row per cycle: `intake_cycle`,
`finance_record_count`, `total_fee_due`, `total_paid`, `outstanding`, and
one column per status showing `count`/`amount` stacked. Cycles are
explicitly `.sort((a, b) => a.intake_cycle.localeCompare(b.intake_cycle))`
on the frontend rather than trusting the backend's own sort order, even
though the backend does already sort this way — a stable, self-documented
order regardless of what the backend happens to return, per the module's
own instruction. Money fields render as the raw decimal string the
backend returns with no reformatting — the same convention Module 09's
`ApplicantFinanceSection`/`FinancePage` already established for
`total_fee_due`/`total_paid`/`amount`, reused here rather than a second,
inconsistent convention (e.g. `Intl.NumberFormat`) for the same kind of
field in the same app. No pagination controls, no filter inputs — the
endpoint has neither.

### Nav and routing (`router.tsx`, `AppShellLayout.tsx`)

`{ path: "finance/reconciliation", element: <ReconciliationPage /> }`
added to `router.tsx`'s route table. A "Reconciliation" nav entry added
to `AppShellLayout.tsx`, gated on `RECONCILIATION_ROLES` via `hasRole`,
positioned directly below the existing "Finance" nav entry.

## Verification against the live stack

Verified against the real running Docker Compose stack
(`sirius-api-1` on `127.0.0.1:38210`) and a real Firefox browser
session driving the real Vite dev server at `http://127.0.0.1:5173`,
using real accumulated data across Modules 03/05/09's own prior live
verification — no new fixtures created, no new applicants/claims seeded
for this module.

- **Totals card matches an independent `psql` sum across every
  `finance_record`/`payment_claim` currently in the stack.** Before
  touching the UI: `psql SELECT count(*), sum(total_fee_due),
  sum(total_paid) FROM finance_record` returned **4, 1000000.00,
  260000.00** — a genuine multi-row sum across `Fall2026` (3 records) and
  `Spring2027` (1 record) combined, not a single-cycle coincidence.
  `psql SELECT status, count(*), sum(amount) FROM payment_claim GROUP BY
  status` returned **CONFIRMED: 3/260000.00, REJECTED: 3/200000.00**
  (`PENDING` absent from the group-by since its count is genuinely 0).
  Logged in as `m3-financemanager@...` (`FINANCE_MANAGER`), the
  Reconciliation page's totals cards showed: Finance records **4**, Fee
  due **1000000.00**, Paid **260000.00**, Outstanding **740000.00**
  (`1000000.00 - 260000.00`, confirmed by hand), Pending **0
  claims / 0**, Confirmed **3 claims / 260000.00**, Rejected **3 claims /
  200000.00** — every figure matching the independent `psql` ground
  truth exactly.
- **Totals equal the sum of the per-cycle rows, the same way Module 05's
  own backend report proved arithmetically.** The per-cycle table showed
  `Fall2026`: 3 records, 800000.00 fee due, 185000.00 paid, 615000.00
  outstanding, Pending 0/0, Confirmed 2/185000.00, Rejected 3/200000.00;
  `Spring2027`: 1 record, 200000.00 fee due, 75000.00 paid, 125000.00
  outstanding, Pending 0/0, Confirmed 1/75000.00, Rejected 0/0. Checked
  by hand against the totals card: `4 = 3 + 1`;
  `1000000.00 = 800000.00 + 200000.00`;
  `260000.00 = 185000.00 + 75000.00`;
  `740000.00 = 615000.00 + 125000.00`; Confirmed `3 = 2 + 1` and
  `260000.00 = 185000.00 + 75000.00`; Rejected `3 = 3 + 0` and
  `200000.00 = 200000.00 + 0`. Every totals field is exactly the sum of
  the corresponding per-cycle field — the frontend is faithfully
  rendering the backend's own `totals`-from-`cycles` structural
  guarantee (Module 05's report), not independently recomputing anything
  that could drift from it.
- **A cycle with a zero-count status renders that zero, not an omitted
  row or column.** `Spring2027` genuinely has zero `REJECTED` claims
  (confirmed by the `psql` per-cycle breakdown above, which has no
  `Spring2027`/`REJECTED` row at all in the raw `GROUP BY` result — the
  backend itself fills this gap per its own schema docstring). The
  `Spring2027` row in the rendered table still shows a `Rejected` column
  with **`0`** count and **`0`** amount, in the identical column
  position every other row's non-zero statuses occupy — not a blank
  cell, not a missing column, not the row skipped from the table
  entirely. Extracted the row's own DOM text content directly to confirm
  this was a real rendered `0`/`0` rather than an empty string that
  merely looked like a zero at a glance.
- **`ADMISSIONS_MANAGER` — the adjacent-but-excluded role, per Module
  05's own reasoning — gets a real 403 and no nav link.** Logged in as
  `m4-manager@...`. The nav showed Home/Applicants/Import
  applicants/Import history — no Finance, no Reconciliation link
  anywhere (this role is outside both `FINANCE_ROLES` and
  `RECONCILIATION_ROLES`). Direct URL navigation to
  `/finance/reconciliation` showed the real backend's
  `"insufficient role for this action"` text in a red `Alert`
  immediately — confirming the frontend gate is UX convenience only and
  the actual boundary is the backend's own `require_role_session`
  rejection, exactly the scenario Module 05's own report specifically
  chose this role to prove (broad applicant visibility elsewhere in the
  system, but genuinely no reconciliation access).
- **`ADMISSIONS_COUNSELOR` also gets a real 403 and no nav link.**
  Logged in as `m4-counselor-a@...`. Nav showed only Home/Applicants — no
  Finance, no Reconciliation link. Direct URL navigation to
  `/finance/reconciliation` showed the identical
  `"insufficient role for this action"` text immediately, with no
  loader hang (benefiting from Module 08's global 4xx-retry-policy fix,
  same as every other out-of-role finance route in this app).
- **Build and typecheck.** `npx tsc -b` and `npm run build` both pass
  with zero errors against the final source tree.

## Real defects found during this module

None. The dashboard's totals and per-cycle numbers matched independent
`psql` ground truth exactly on every field checked, the totals-equal-
sum-of-cycles arithmetic held exactly as Module 05's backend already
guaranteed structurally, the zero-count status rendered as a genuine
zero rather than being silently dropped, and both tested out-of-role
roles were correctly denied with the real backend's own 403 text and no
nav link. No frontend or backend code change was required.

## Explicitly out of scope (per module boundary)

No pagination or filter UI was built for `/finance/reconciliation`,
since the real backend endpoint accepts neither — building such
affordances would imply a capability that does not exist. No RBAC logic
was duplicated beyond `RECONCILIATION_ROLES`, copied verbatim from
`app.routers.reconciliation._ROLES`; that router's own
`require_role_session` dependency remains the actual enforcement point.
This closes the last module against the original project scope — no
further backend endpoints from Modules 01-05 remain without a
corresponding frontend surface.
