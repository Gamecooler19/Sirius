# Module 09: Payment-Claim UI — completion report

## Scope

Build the payment-claim UI in `frontend/`: a Finance review queue wired to
the real `GET /finance/payment-claims` and `POST
/finance/payment-claims/{id}/confirm|reject` (Module 03), and a
per-applicant finance section (embedded in Module 07's own
`ApplicantDetailDrawer`) wired to the real `GET /applicants/{id}/finance`
(Module 04) and `POST /finance/payment-claims` (Module 03) — no mocked
responses. The real backend enforces a genuine maker-checker asymmetry
sharper than Module 08's import split: `submit_payment_claim` allows
`SUPER_ADMIN`/`FINANCE_STAFF`/`FINANCE_MANAGER`, but
`confirm_payment_claim`/`reject_payment_claim` allow only
`SUPER_ADMIN`/`FINANCE_MANAGER` — `FINANCE_STAFF` may originate a claim
but can never resolve *any* claim, including one submitted by a different
staff member — plus an application-layer same-user check on top (a
`FINANCE_MANAGER` cannot resolve their own submission). The frontend's
role gates and control visibility had to reflect that split exactly, not
a milder version of it, and the review queue had to render *no* Actions
column at all for a role outside `PAYMENT_RESOLVE_ROLES`, not a column of
disabled buttons implying near-access.

## What was built

### Roles (`src/auth/roles.ts` additions)

`PAYMENT_SUBMIT_ROLES` (`SUPER_ADMIN`, `FINANCE_STAFF`, `FINANCE_MANAGER`
— copied from `app.routers.payment_claim.submit_payment_claim`'s own
`require_role_session` call) and `PAYMENT_RESOLVE_ROLES` (`SUPER_ADMIN`,
`FINANCE_MANAGER` only — copied from `confirm_payment_claim`/
`reject_payment_claim`'s own allowlist). The module docstring states the
asymmetry explicitly and names the backend's own application-layer
same-user check as a second, independent boundary this frontend does not
attempt to pre-empt or duplicate — a self-resolve attempt is always sent
to the real backend and its real 422 is shown verbatim, never blocked
client-side with a guessed message.

### Types (`src/api/types.ts` additions)

`PaymentClaimStatus`, `PaymentMode` (mirror
`api/app/models/enums.PaymentClaimStatus`/`PaymentMode` exactly),
`PaymentClaimSubmitRequest` (deliberately has no `submitted_by` field,
matching the backend schema's own documented reasoning that trusting a
client-supplied identity for an audit-relevant field would defeat the
point of recording it), `PaymentClaimResolveRequest`,
`PaymentClaimResponse`, `PaymentClaimDetail` (mirrors
`api/app/schemas/reads.py::PaymentClaimDetail` — the shape both
`GET /finance/payment-claims` and `GET /applicants/{id}/finance` actually
return), `PaymentClaimListResponse`, `ApplicantFinanceResponse` (mirrors
`api/app/schemas/reads.py::ApplicantFinanceResponse` exactly).

### Query hooks (`src/finance/useFinance.ts`)

- `usePaymentClaimsList(params)` — `GET
  /finance/payment-claims?limit=&offset=&status=`, same
  `placeholderData` pattern as Modules 07/08 to avoid flashing empty
  during a page/filter change.
- `useApplicantFinance(applicantId)` — `GET /applicants/{id}/finance`
  with `retry: false` and a derived `notFound` flag
  (`error instanceof ApiError && error.status === 404`), since a 404 here
  is the documented, expected "no finance record yet" state for most
  applicants (anyone who never reached `ADMISSION_TAKEN`), not a genuine
  error — retrying it three times before rendering the empty state would
  only slow the drawer down for no benefit.
- `useSubmitPaymentClaim(applicantId)` — `POST
  /finance/payment-claims`; on success invalidates this applicant's own
  finance-detail query and the standalone claims-list query root, so a
  freshly submitted claim appears in `FinancePage`'s queue without a
  reload.
- `useResolvePaymentClaim()` — `POST
  /finance/payment-claims/{id}/confirm` or `/reject`; on success
  invalidates the claims-list root and the entire `["applicants",
  "finance"]` key *prefix* rather than one applicant id, because
  `PaymentClaimDetail` carries only `finance_record_id`, not
  `applicant_id` — `FinancePage` (where resolve actions actually live)
  has no single applicant id to target-invalidate. Invalidating the whole
  prefix is cheap since TanStack Query only refetches mounted queries,
  and correctly reaches an already-open `ApplicantDetailDrawer` showing
  the resolved claim's own applicant.

### Review queue (`src/finance/FinancePage.tsx`)

Same `Table` + `Pagination` + "Showing X-Y of Z" shape as Modules 07/08,
plus a status `Select` filter (`PENDING`/`CONFIRMED`/`REJECTED`,
clearable). Columns: submitted timestamp, amount, mode, reference,
status badge, submitted-by id, resolved-by id, and — **only rendered at
all when `hasRole(me.role_code, PAYMENT_RESOLVE_ROLES)`** — an Actions
column with Confirm/Reject buttons on `PENDING` rows only (an em dash for
non-pending rows). A per-row error `Alert` (spanning the full row) shows
the backend's real 422 text verbatim when a resolve attempt fails
(maker-checker self-resolve, or "not PENDING" if another user resolved it
first).

### Finance section (`src/finance/ApplicantFinanceSection.tsx`)

Embedded in `ApplicantDetailDrawer` below the status-history timeline.
Loading state, then three branches on `useApplicantFinance`: `notFound`
→ plain dimmed explanatory text ("No finance record yet -- created
automatically once this applicant reaches Admission Taken"), a genuine
non-404 error → red `Alert` with the backend's real text, otherwise the
real record: fee-due/paid/outstanding (outstanding computed client-side
as `due - paid`, both server-supplied decimal strings), a read-only
`Table` of every existing claim (no confirm/reject controls here at all
— that action lives only on `FinancePage`, matching the real review-queue
design), and — gated on `PAYMENT_SUBMIT_ROLES` — a submit-new-claim form
(amount, payment mode, optional reference) whose success/error alerts
show the backend's own text, never a synthesized one.

### Nav and routing (`router.tsx`, `ApplicantDetailDrawer.tsx`)

`finance/FinancePage.tsx` replaces the old `pages/FinancePage.tsx`
placeholder at `/finance` in `router.tsx`. `ApplicantDetailDrawer.tsx`
renders `<ApplicantFinanceSection applicantId={...} />` under a "Finance"
section divider, for every role that can open a drawer at all
(`APPLICANTS_ROLES`), independent of `PAYMENT_SUBMIT_ROLES`/
`PAYMENT_RESOLVE_ROLES` — the finance section itself does the further
gating of its own submit form, and the real `GET
/applicants/{id}/finance` RLS policy does the further gating of whether
any data comes back at all.

## Verification against the live stack

Verified against the real running Docker Compose stack
(`sirius-api-1` on `127.0.0.1:38210`) and a real Firefox browser
session driving the real Vite dev server at `http://127.0.0.1:5173`,
using Module 03's own real fixtures (`m3-financestaff`,
`m3-financemanager`, `m3-financemanager2`, all with mandatory TOTP) and
Module 04's `ADMISSIONS_COUNSELOR` fixture (`m4-counselor-a`). TOTP codes
were generated on demand via a temporary `get_totp.py` helper copied into
the `api` container (decrypts the real seeded TOTP secrets and computes
the live code) — both this helper and a throwaway `login_and_verify.py`
script were deleted from the container and the host repo before
committing (see Cleanup).

- **`FINANCE_STAFF` sees the queue but genuinely has no Actions column at
  all.** Logged in as `m3-financestaff@...`. Nav showed Home/Finance
  only — no Applicants, no Import links (matches `FINANCE_ROLES` /
  `FINANCE_STAFF` not being in any other nav gate). `/finance` listed all
  existing claims with **no Actions column header rendered at all**, not
  a column of disabled buttons — confirmed by inspecting the actual
  rendered `<table>` structure, column count matched the non-`canResolve`
  branch exactly.
- **`FINANCE_STAFF` can still reach `/applicants` directly and submit a
  real new claim.** Direct URL navigation to `/applicants` succeeded
  (matches the existing, already-verified Module 07 design: applicant
  reads are open to all six roles with RLS doing the narrowing). Opened
  an `ADMISSION_TAKEN` applicant's drawer, filled the submit-claim form
  (amount `85000`, mode `UPI`, no reference) and submitted. A `psql`
  check confirmed a new `payment_claim` row: `amount = 85000.00`,
  `payment_mode = UPI`, `status = PENDING`, `submitted_by` = this staff
  user's real id. Without reloading, navigating to `/finance` (still
  logged in as this staff user) showed the new claim in the queue
  immediately — the cache invalidation from `useSubmitPaymentClaim`
  genuinely reached `FinancePage`'s own query.
- **`FINANCE_MANAGER` #1 sees Confirm/Reject on every `PENDING` row and a
  genuine cross-user confirm updates `total_paid` via the DB trigger.**
  Logged in as `m3-financemanager@...`. `/finance` showed Confirm/Reject
  buttons on all `PENDING` rows including the staff-submitted 85000 UPI
  claim from a different, real user. Clicked Confirm: the row updated to
  `CONFIRMED` in place. A `psql` check confirmed
  `payment_claim.status = 'CONFIRMED'`, `confirmed_by` = this manager's
  real id, and — via the finance-record trigger — `finance_record.
  total_paid` updated from `0.00` to `85000.00`. Reopening that same
  applicant's drawer (a fresh mount, exercising the invalidated
  `["applicants","finance"]` prefix from `useResolvePaymentClaim`) showed
  `Paid: 85000.00` reflecting the update without any manual refresh.
- **The real maker-checker 422 surfaces verbatim on a genuine self-resolve
  attempt.** Still as manager #1: submitted their own new claim (`30000`
  CASH) via the same applicant's drawer, then went to `/finance` and
  clicked Confirm on that same row. The row's error `Alert` showed
  exactly: *"cannot confirm or reject a payment claim you submitted
  yourself (maker-checker separation)"* — the backend's own text, not a
  frontend-authored message. A `psql` check confirmed the claim stayed
  `PENDING`, `confirmed_by` still `NULL`, completely unchanged by the
  failed attempt.
- **`FINANCE_MANAGER` #2 genuinely resolves a different manager's own
  claim (cross-user reject).** Logged in as `m3-financemanager2@...`
  (TOTP verify needed the `get_totp.py` call and the browser's verify
  `eval` issued back-to-back with nothing in between, after a couple of
  transient 30-second-window misses). Clicked Reject on manager #1's own
  30000 CASH claim from the queue. A `psql` check confirmed
  `status = 'REJECTED'`, `confirmed_by` = manager #2's real id (not
  manager #1's), and `finance_record.total_paid` unaffected — still
  `85000.00`, matching the backend's real "a rejected claim never touches
  `total_paid`" design.
- **`ADMISSIONS_COUNSELOR` has no Finance nav link, a real 403 on direct
  navigation, and a correct empty-state finance section on their own
  applicant.** Logged in as `m4-counselor-a@...`. Nav showed no Finance
  link. Direct URL navigation to `/finance` showed the real backend's
  `"insufficient role for this action"` text in a red `Alert`
  **immediately** — benefiting from Module 08's retry-policy fix (any
  4xx, not only 401, is now excluded from TanStack Query's retry). Opened
  the drawer for `M4 Applicant A02` (`ADMISSION_TAKEN`, assigned to this
  counselor): the Finance section rendered *"No finance record yet --
  created automatically once this applicant reaches Admission Taken"* and
  **no submit form**. A direct `psql` check confirmed this applicant's
  `finance_record` genuinely exists (`total_fee_due = 300000.00,
  total_paid = 85000.00`, the very row manager #1 confirmed against
  earlier in this same verification pass) — the 404 this counselor's
  session receives is entirely a product of `finance_record`'s own RLS
  `SELECT` policy (`SUPER_ADMIN`/`FINANCE_STAFF`/`FINANCE_MANAGER`/
  `AUDITOR` only, `ADMISSIONS_COUNSELOR` excluded), not an actual absence
  of data. The frontend's empty-state text is therefore indistinguishable
  from true absence by design — matching the backend's own RLS boundary,
  not a frontend approximation of it. No submit form appeared either,
  correctly gated by this role being outside `PAYMENT_SUBMIT_ROLES`.
- **Build and typecheck.** `npx tsc -b` and `npm run build` both pass
  with zero errors against the final source tree.

## Real defects found and fixed during this module

None found in this module's own new code. Module 09's UI benefited
directly from Module 08's retry-policy fix (`App.tsx`'s `QueryClient`
now excludes all 4xx statuses from retry, not only 401) — without that
fix, the counselor's direct-URL `/finance` 403 would have hung with
neither a loader nor an error for several seconds, the same failure mode
Module 08 diagnosed and fixed. No new defect required a code change in
this module.

## Cleanup

`api/get_totp.py` and `api/login_and_verify.py` — temporary helper
scripts used only to generate/verify TOTP codes during this module's live
verification — were deleted from both the `api` container
(`sirius-api-1`) and the host repo before committing. The Vite
dev server background task used throughout this verification was
stopped. `git status` was checked to confirm no test `.xlsx` files, log
files, or other scratch artifacts were staged.

## Explicitly out of scope (per module boundary)

No RBAC logic was duplicated beyond `PAYMENT_SUBMIT_ROLES`/
`PAYMENT_RESOLVE_ROLES`, both copied verbatim from the backend's own
`require_role_session` declarations in `app.routers.payment_claim`. The
backend (`submit_payment_claim`, `confirm_payment_claim`,
`reject_payment_claim`, plus `finance_record`'s own RLS policies) remains
the actual enforcement point for every access decision this module's UI
merely reflects or hides controls for. Reconciliation reporting (Module
05's `GET /reconciliation` endpoints) has no frontend UI in this module —
out of scope until a future module, if any, covers it.

## Follow-up verification

Two gaps in this module's own original verification, closed against the
same live stack using the claims already sitting in it from this module
and Module 03 — no new fixtures created for either. Both confirmed the
existing design; neither surfaced a real defect, so no code change was
needed.

### 1. The status filter genuinely narrows the queue server-side, not silently ignored

The original report exercised `usePaymentClaimsList`'s `status` param
only implicitly, by observing which claims a given role could act on —
never by independently counting a status in the database first and
confirming the *filtered* UI result matches that count exactly, as
distinct from just "looking plausible."

Six real claims existed in the live database from this module and Module
03's combined activity: `psql GROUP BY status` gave
**PENDING: 1, CONFIRMED: 3, REJECTED: 2** — counted independently,
before touching the UI at all. Logged in as `m3-financemanager@...`
(`FINANCE_MANAGER`), the unfiltered `/finance` queue showed all 6 rows
("Showing 1-6 of 6"). Selecting the `PENDING` filter produced
**"Showing 1-1 of 1"**, the single row being the real `120000.00 CHEQUE`
claim (`M5F-TXN-001`) — matching the independent count of 1 exactly, not
merely "fewer than 6." Selecting `CONFIRMED` next produced
**"Showing 1-3 of 3"**, all three rows genuinely `CONFIRMED` by their
badge and none `PENDING`/`REJECTED` — matching the independent count of
3 exactly. Together these two checks prove the `status` query param
reaches the real backend and narrows the result set to the exact
database-side count in both directions (down to 1, and to a different
non-trivial value of 3), rather than the parameter being silently
dropped and the UI still rendering all 6 (or some accidentally-cached
stale set). No code change needed.

### 2. A stale review-queue row surfaces the real "not PENDING" 422, not a silent failure or a crash

The original report's maker-checker verification always resolved a claim
from the *only* browser session that had it loaded — it never left a
second, unrefreshed browser tab sitting on a `PENDING` row with a live
Confirm button after that same claim was resolved by someone else
through a completely different session, the exact "stale queue" race
Module 07's own follow-up used for a stale status transition.

Logged in as `m3-financemanager@...` in the browser and loaded `/finance`
filtered to `PENDING`: exactly the one row from check 1 above
(`120000.00 CHEQUE`, `M5F-TXN-001`, id `d8d3aa72-4a3a-486d-9fdc-36d06d3160da`),
with a live, enabled Confirm button rendered. Without that tab refetching
anything, authenticated a genuinely separate session as
`m3-financemanager2@...` via real `curl` calls against the live backend
(`POST /auth/login` then `POST /auth/totp/verify` with a freshly
generated real TOTP code) and called
**`POST /finance/payment-claims/d8d3aa72-4a3a-486d-9fdc-36d06d3160da/reject`**
directly against that session — 200, the backend's real response showing
`status: "REJECTED"`, `confirmed_by` = manager #2's real id. A `psql`
check immediately confirmed this genuinely landed in the database:
`status = REJECTED`, `confirmed_by = 1c08c67d-7f8e-4a18-91f1-bb1dfb5c804b`
(manager #2), a real `confirmed_at` timestamp.

The first browser tab (manager #1) was never touched during that second
session's call and still showed the row as `PENDING` with its Confirm
button live — screenshotted to record the stale state before proceeding.
Clicking that stale Confirm button produced a row-level red `Alert`
reading exactly:

> payment claim is not PENDING (current status: REJECTED)

— the real backend's own text, in the identical row-error `Alert` shape
`FinancePage.tsx` already uses for the maker-checker 422 (see the
original report's manager #1 self-confirm case), not a silent failure,
not a stuck loading spinner, and not a crash. A `psql` check immediately
afterward confirmed the stale click altered nothing further:
`status` still `REJECTED`, `confirmed_by` still manager #2's id, and
`confirmed_at` still the exact same timestamp as before the stale
click — the failed mutation genuinely touched zero rows, it did not,
for instance, silently overwrite `confirmed_by` back to manager #1 or
bump `confirmed_at` before the backend's own PENDING check rejected it.
Reloading the page afterward correctly showed the claim as `REJECTED`,
resolved by manager #2, confirming the earlier stale render was purely a
client-side cache artifact of not having refetched, not a genuine
data inconsistency. No code change needed — this is
`useResolvePaymentClaim`'s existing `ApiError`-surfacing path (the same
one the maker-checker case already exercised) correctly handling a
different backend rejection reason without any special-casing required.
