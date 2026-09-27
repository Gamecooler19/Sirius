# Module 14: Home dashboard analytics (real, role-based)

## Scope

Replace Module 13's static "Welcome to Sirius" intro card on the Home page
with real, role-scoped analytics:

- One new backend endpoint, `GET /applicants/summary` -- a per-status
  applicant count breakdown, aggregated entirely in SQL
  (`GROUP BY current_status`), reusing `applicant`'s own existing RLS
  policy with **zero** new RLS or RBAC code.
- A finance-totals section on the same page, reusing the exact
  `useReconciliation` query hook `ReconciliationPage` already uses
  (Modules 05/09/10) -- no new backend endpoint, no duplicated query
  logic.
- Role gating: any role with applicant visibility sees the applicant
  section; any role with finance visibility sees the finance section;
  `SUPER_ADMIN`/`AUDITOR` (the only two roles in both groups) see both;
  a role in neither sees neither (falls back to the Module 13 intro
  card).
- Every visual reuses Module 13's design system (`Card`, `SimpleGrid`,
  the exact tonal/spacing tokens, the `EmptyState` component) -- no new
  ad hoc styling.

## Part 1 -- the backend endpoint

### `GET /applicants/summary` (`api/app/routers/applicants_read.py`)

Added immediately after `list_applicants` and before the `/{applicant_id}`
dynamic route, not appended at the end of the file -- a literal
`/applicants/summary` path registered *after* the UUID-typed
`/{applicant_id}` route would collide with Starlette's own route matching
(the literal string `"summary"` failing UUID parsing). Verified this
ordering is correct by hitting the live endpoint successfully (below),
not just by inspecting the source.

**RBAC/RLS -- reuses the existing policy exactly, as required.** Same
`require_role_session(*_ALL_ROLES)` no-op role gate every other route in
this file already uses (the file's own docstring: "intentionally none
beyond any authenticated session"). The real visibility narrowing is
`applicant`'s own `role_visibility` RLS policy from Modules 01/03,
completely unchanged:

- `SUPER_ADMIN`/`ADMISSIONS_MANAGER`/`FINANCE_STAFF`/`FINANCE_MANAGER`/
  `AUDITOR` see every row.
- `ADMISSIONS_COUNSELOR` sees only rows where `assigned_counselor_id` is
  their own id.

**Zero new RLS or RBAC code was written for this endpoint** -- the exact
constraint the module asked for. A counselor's summary is automatically
scoped to their own applicants; a manager's or admin's summary is the
real total across everyone, purely because they're both going through
the identical RLS-scoped session `require_role_session` already yields
for every other route in this file.

**SQL-level aggregation only, matching Module 05's own discipline exactly.**

```python
query = (
    select(Applicant.current_status, func.count(Applicant.id))
    .group_by(Applicant.current_status)
)
```

One query, one `GROUP BY`, `func.count()` -- no join at all (there is
nothing to fan out here, unlike reconciliation's two-query join-avoidance
dance over `finance_record`/`payment_claim`), and no Python-side counting
of `applicant` rows anywhere in the function. Every status is always
present in the response (`count: 0` for a status with zero rows in the
caller's own scope), the same always-present-bucket convention
`PaymentClaimStatusBreakdown`/`ReconciliationCycle` already established.
`total` is computed by summing the already-grouped `by_status` array in
Python, not a second SQL round-trip -- `total == sum(by_status)` is a
structural guarantee of the function's own control flow, the identical
drift-proofing reasoning `ReconciliationTotals` already documents for the
same pattern.

### New schemas (`api/app/schemas/reads.py`)

`ApplicantStatusBreakdown` (`status`, `count`) and `ApplicantSummaryTotals`
(`total`, `by_status: list[ApplicantStatusBreakdown]`) -- hand-declared
Pydantic models, matching this file's own established "never dump a raw
ORM object" pattern. Verified via the live OpenAPI schema that the
response carries only these fields, no leakage:

```json
{
  "properties": {
    "total": {"type": "integer"},
    "by_status": {"items": {"$ref": "#/components/schemas/ApplicantStatusBreakdown"}}
  },
  "required": ["total", "by_status"]
}
```

## Part 2 -- the frontend

### New types/hook

`ApplicantStatusBreakdown`/`ApplicantSummaryTotals` in `api/types.ts`,
mirroring the backend schemas field-for-field. `useApplicantSummary()` in
`applicants/useApplicants.ts`, added to the existing `applicantsKeys`
namespace (`summary: ["applicants", "summary"]`) so a status transition's
existing `invalidateQueries({ queryKey: applicantsKeys.all })` call
automatically invalidates the dashboard's cache too, via TanStack Query's
own prefix-key matching -- no new invalidation logic needed.

### Role gates (`auth/roles.ts`)

`DASHBOARD_APPLICANTS_ROLES` = `SUPER_ADMIN`/`ADMISSIONS_MANAGER`/
`ADMISSIONS_COUNSELOR`/`AUDITOR` -- deliberately **not** a reuse of the
existing `APPLICANTS_ROLES` constant, because that one is scoped to "roles
that own the transition workflow" (excludes `AUDITOR` by design, per its
own comment), while `GET /applicants/summary`'s real backend RBAC is open
to all six roles with RLS narrowing. `AUDITOR` genuinely has applicant
read visibility (the same reason they already have `IMPORT_HISTORY_ROLES`
nav access), so the dashboard section correctly includes them even though
the Applicants *nav link* itself does not.

`DASHBOARD_FINANCE_ROLES` = `FINANCE_ROLES` reused verbatim (no asymmetry
to preserve for a summary view the way the nav-gate constants sometimes
have).

### `HomePage.tsx`

Two independent sections (`ApplicantSummarySection`, `FinanceSummarySection`),
each with its own loading/error/empty state, gated by `hasRole` against
the two constants above. `FinanceSummarySection` imports and calls
`useReconciliation` -- the exact same hook `ReconciliationPage` uses,
not a re-implementation -- and renders only the `totals` half of that
response (per-cycle breakdown stays on the dedicated page). Every card
uses `Card withBorder padding="lg" radius="lg"` and `SimpleGrid` with the
exact same responsive `cols` pattern Module 13's `ReconciliationPage` fix
established; the applicant-summary empty case and finance-summary empty
case both use the Module 13 `EmptyState` component, not new markup.

## Part 3 -- live verification

Since Module 13's follow-up verification had already seeded real data
(12 applicants, real status transitions, real payment claims -- see
`reports/module-13-redesign-v2.md`'s own Follow-up section), this module
reused that same live data rather than reseeding, plus assigned 2 of the
12 applicants (`Ira Desai`, `Yash Kulkarni`, both `IMPORTED`) to
`admissionscounselor@sirius.app` via a direct SQL `UPDATE` (the one
legitimate use of direct SQL in this project's own established pattern:
setting up fixture state no endpoint yet supports -- no assignment
endpoint exists in this codebase) to create a genuinely RLS-narrowed
third view to check against.

### Endpoint correctness: cross-checked against independent psql, twice

**Full/unscoped total** (as `ADMISSIONS_MANAGER`, who sees every row):

```
$ curl -b cookies.txt http://127.0.0.1:38210/applicants/summary
{"total":12,"by_status":[
  {"status":"IMPORTED","count":2},{"status":"APPLIED","count":1},
  {"status":"IN_PROCESS","count":2},{"status":"ON_HOLD","count":1},
  {"status":"ADMISSION_OFFERED","count":2},{"status":"ADMISSION_TAKEN","count":2},
  {"status":"REJECTED","count":1},{"status":"WITHDRAWN","count":1}]}
```

Independent psql `GROUP BY`, run separately, as `postgres` superuser
(bypasses RLS entirely -- the true, unscoped ground truth):

```sql
SELECT current_status, count(*) FROM applicant GROUP BY current_status ORDER BY current_status;
  current_status   | count
-------------------+-------
 IMPORTED          |     2
 APPLIED           |     1
 IN_PROCESS        |     2
 ON_HOLD           |     1
 ADMISSION_OFFERED |     2
 ADMISSION_TAKEN   |     2
 REJECTED          |     1
 WITHDRAWN         |     1
```

**Exact match**, every status, every count, and the sum (12).

**RLS-narrowed total** (as `ADMISSIONS_COUNSELOR`, who should see only
their own 2 assigned applicants):

```
$ curl -b counselor_cookies.txt http://127.0.0.1:38210/applicants/summary
{"total":2,"by_status":[{"status":"IMPORTED","count":2}, ... rest 0]}
```

Independent psql cross-check, filtered to this counselor's own id:

```sql
SELECT current_status, count(*) FROM applicant
WHERE assigned_counselor_id='79cff0fe-74bc-4746-b3f8-8b18ae3b8c81'
GROUP BY current_status;
 current_status | count
----------------+-------
 IMPORTED       |     2
```

**Exact match.** This is the real, live proof the endpoint's RLS reuse
works: the same endpoint, same code path, returns a completely different
(and correct) scope depending purely on who's calling it -- zero role
parameter, zero scope filter passed by the client.

### Dashboard content: verified across 3 genuinely different roles

1. **`AUDITOR`** (`auditor@sirius.app`) -- in both dashboard role groups.
   Live screenshot shows **both** sections: "Applicants by status" (all 8
   status cards, matching the unscoped totals above exactly -- 2/1/2/1/
   2/2/1/1) and "Finance totals" (Finance records: 2, Fee due: 0.00, Paid:
   550000.00, Outstanding: -550000.00). Nav correctly shows Home/Finance/
   Reconciliation/Import history (no Applicants link, per `AUDITOR`'s
   existing nav-gate exclusion from `APPLICANTS_ROLES` -- the dashboard
   section and the nav link are deliberately different gates, as designed).

2. **`ADMISSIONS_COUNSELOR`** (`admissionscounselor@sirius.app`) --
   applicant-only dashboard group. Live screenshot shows **only**
   "Applicants by status," with `Imported: 2` and every other status at
   `0` -- the exact RLS-narrowed scope, cross-checked against psql above.
   **No "Finance totals" section renders at all** (correctly gated out --
   this role is not in `DASHBOARD_FINANCE_ROLES`). Nav correctly shows
   only Home/Applicants.

3. **`FINANCE_STAFF`** (`financestaff@sirius.app`, real TOTP login via a
   live-computed code) -- finance-only dashboard group. Live screenshot
   shows **only** "Finance totals" (Finance records: 2, Paid: 550000.00,
   Outstanding: -550000.00). **No "Applicants by status" section renders
   at all** (correctly gated out). Nav correctly shows Home/Finance/
   Reconciliation (no Applicants, no Import).

These three roles cover every branch of the gating logic: both-sections,
applicant-only (with real RLS narrowing on top), and finance-only.

### Regression checks

- `tsc --noEmit`: zero errors.
- `impeccable detect --json frontend/src`: `[]`, zero findings.
- `npm run build`: clean production build, 5480 modules transformed.
- OpenAPI schema for the new response models: only `total`/`by_status`/
  `status`/`count`, zero sensitive-field leakage.
- No existing role gate, RLS policy, or maker-checker control was
  touched -- the only backend change is one new `GET` route and two new
  read-only Pydantic schemas; the only frontend changes are one new hook,
  two new role constants, and `HomePage.tsx`'s own render logic.

## Files changed

**Modified:**
- `api/app/routers/applicants_read.py` -- new `GET /applicants/summary`
  route.
- `api/app/schemas/reads.py` -- `ApplicantStatusBreakdown`,
  `ApplicantSummaryTotals`.
- `frontend/src/api/types.ts` -- matching TS interfaces.
- `frontend/src/applicants/useApplicants.ts` -- `useApplicantSummary()`.
- `frontend/src/auth/roles.ts` -- `DASHBOARD_APPLICANTS_ROLES`,
  `DASHBOARD_FINANCE_ROLES`.
- `frontend/src/pages/HomePage.tsx` -- full rewrite: two role-gated
  dashboard sections replacing the Module 13 static intro card. The old
  card is retained as `WelcomeIntro`, rendered only when a session's role
  is in neither `DASHBOARD_APPLICANTS_ROLES` nor `DASHBOARD_FINANCE_ROLES`.
  No current role reaches this path: all six roles fall into at least one
  of the two dashboard groups today (see the Follow-up section below for
  the exhaustive per-role accounting). `WelcomeIntro` exists as
  forward-compatible scaffolding for a role added in a future module that
  genuinely belongs in neither group, not as a presently-reachable screen.

**Data used (already existed from Module 13's own follow-up seeding,
reused rather than reseeded):** 12 applicants, real status transitions,
real payment claims, plus 2 applicants freshly assigned to
`admissionscounselor@sirius.app` via a direct SQL `UPDATE` (the one
legitimate direct-SQL use in this project's established pattern -- no
assignment endpoint exists yet to do this through the API).

## Follow-up verification

One gap in this module's own original verification, closed against the
same live stack and the same seed data already sitting in it -- no new
fixtures. The check confirmed the existing design and caught a real
documentation inaccuracy in this report's own first version; no code
change was needed.

### 1. `ADMISSIONS_MANAGER`'s dashboard, checked at the UI level, not just via curl

Every role combination this module's original verification exercised
(`AUDITOR`, `ADMISSIONS_COUNSELOR`, `FINANCE_STAFF`) was checked live in
the browser. The fourth structurally distinct combination --
`ADMISSIONS_MANAGER`, who is in `DASHBOARD_APPLICANTS_ROLES` but not
RLS-narrowed the way `ADMISSIONS_COUNSELOR` is (no `assigned_counselor_id`
restriction applies to this role), and who is in neither
`DASHBOARD_FINANCE_ROLES` -- had only been checked via a raw `curl`
request against `GET /applicants/summary` directly, not through the real
rendered page. That is a real gap: a curl response proves the backend
endpoint works, not that the frontend's role-gating logic, query hook, and
render tree actually reach the same conclusion for this specific role in
the browser.

Logged in as `admissionsmanager@sirius.app` through the real login form
(fresh session, not a reused cookie), navigated to `/`, and took a live
screenshot:

```
Applicants by status
  Imported: 2       Applied: 1        In process: 2     On hold: 1
  Admission offered: 2   Admission taken: 2   Rejected: 1   Withdrawn: 1
```

This is an **exact match** to the same independent psql `GROUP BY` used
earlier in this report (2/1/2/1/2/2/1/1, total 12) -- the true unscoped
total, since `ADMISSIONS_MANAGER` is not narrowed by RLS the way
`ADMISSIONS_COUNSELOR` is. Confirmed the "Finance totals" heading and
every finance card are genuinely absent from the DOM, not merely
off-screen or visually hidden:

```js
document.body.textContent.includes('Finance totals') // => false
```

Nav also correctly showed only Home/Applicants/Import applicants/Import
history -- no Finance/Reconciliation, matching `ADMISSIONS_MANAGER`'s
existing nav-gate scope.

This completes the fourth and final structurally distinct role
combination at the UI level (the other three were already covered):
both-sections (`AUDITOR`), applicant-only-with-RLS-narrowing
(`ADMISSIONS_COUNSELOR`), finance-only (`FINANCE_STAFF`), and now
applicant-only-with-the-real-unscoped-total (`ADMISSIONS_MANAGER`).

### 2. `WelcomeIntro`'s framing corrected

This report's first version described `WelcomeIntro` as "the fallback for
a role in neither dashboard group" without stating plainly whether any
role currently reaches it. Checking `DASHBOARD_APPLICANTS_ROLES` (
`SUPER_ADMIN`/`ADMISSIONS_MANAGER`/`ADMISSIONS_COUNSELOR`/`AUDITOR`) and
`DASHBOARD_FINANCE_ROLES` (`SUPER_ADMIN`/`FINANCE_STAFF`/
`FINANCE_MANAGER`/`AUDITOR`) against the full six-role `RoleCode` enum
confirms every one of the six roles is a member of at least one set:

| Role | In `DASHBOARD_APPLICANTS_ROLES`? | In `DASHBOARD_FINANCE_ROLES`? |
|---|---|---|
| `SUPER_ADMIN` | yes | yes |
| `ADMISSIONS_MANAGER` | yes | no |
| `ADMISSIONS_COUNSELOR` | yes | no |
| `FINANCE_STAFF` | no | yes |
| `FINANCE_MANAGER` | no | yes |
| `AUDITOR` | yes | yes |

No row has "no" in both columns. **No current role can reach
`WelcomeIntro` today.** It exists as forward-compatible scaffolding --
correct and harmless to keep, since a future role that genuinely
belongs in neither group would otherwise hit a blank Home page -- but
this report's "Files changed" section (above) has been corrected to say
so plainly rather than leaving it implied.

### Regression checks (unchanged)

`tsc --noEmit` and `impeccable detect --json frontend/src` were re-run
after this follow-up; both remain clean (zero errors, `[]` findings). No
code changed as a result of this follow-up -- both findings confirmed the
existing implementation was already correct.

