# Module 04: Read endpoints — completion report

## Scope

Add read/list access for the four objects this API could already create
but never let anyone list or view: applicants (list, detail,
status-history, finance summary), a standalone payment-claims list, and
an import-batches list. No new RLS policy, no new RBAC role, no schema
change of any kind — every endpoint is a plain `SELECT` through the
existing RLS-scoped session, wired via `require_role_session`, exactly as
Modules 01-03 already established.

## What was built

### `app/schemas/reads.py`

Hand-declared Pydantic response models for every endpoint below —
`ApplicantSummary`/`ApplicantListResponse`/`ApplicantDetail`,
`StatusHistoryEvent`/`StatusHistoryResponse`,
`PaymentClaimDetail`/`ApplicantFinanceResponse`/`PaymentClaimListResponse`,
`ImportBatchSummary`/`ImportBatchListResponse`. None use
`ConfigDict(from_attributes=True)` over the raw ORM `__dict__` — every
field is picked by name, the same pattern `app.schemas.payment_claim`/
`app.schemas.status` already established, so an internal-only column
added to a model later (a password hash, a TOTP secret, anything not
meant for the wire) cannot leak through one of these routes by accident.

### `app/routers/applicants_read.py`

**`GET /applicants`** — paginated (`limit`, default 25, `ge=1, le=100`;
`offset`, default 0, `ge=0` — both enforced by FastAPI's own `Query`
validation, not hand-rolled bounds checking) and filterable
(`current_status`, `program`, `intake_cycle`, all optional, combined with
plain `AND`). A separate `COUNT(*)` query (same filters applied) backs
the response's own `total` field, independent of `limit`/`offset`, so a
client can compute total pages without a second unfiltered request.
Ordered by `created_at ASC, id ASC` — a stable tie-break, not `created_at`
alone, since several of this module's own seeded rows share an identical
`created_at` timestamp (same-transaction bulk insert) and an unstable sort
would risk a row appearing on two different pages or neither, across two
separate paginated requests.

**`GET /applicants/{id}`** — single-record detail, 404 if the id does not
exist or is RLS-invisible to the caller (indistinguishable from each
other by design, matching the established convention from
`app.routers.status`).

**`GET /applicants/{id}/status-history`** — the full
`application_status_event` log for that applicant, chronological
(`created_at ASC`). The applicant is checked for visibility *first*, as
its own explicit 404, before querying the event log — an applicant that
is RLS-invisible to the caller must 404, not silently return `{"items":
[]}`, which would otherwise be indistinguishable from "this applicant is
visible to you and genuinely has no status events yet" (a real, valid
state for a just-imported applicant that has never been transitioned).
`application_status_event`'s own RLS policy (an `EXISTS` against
`applicant` using the identical role/counselor predicate, confirmed live
via `\d+`) makes this two-query shape belt-and-suspenders rather than
strictly load-bearing on its own — the event query would come back empty
regardless — but the explicit applicant check is what actually produces
the *correct status code* for the invisible case.

**`GET /applicants/{id}/finance`** — the `finance_record` and its full
list of `payment_claim`s for that applicant, if one exists; 404 if it
does not (most applicants, anyone who never reached `ADMISSION_TAKEN`,
have none — expected, not an error) or if RLS hides it. **Deliberately
does not** check applicant visibility first the way status-history does:
`finance_record`'s own RLS policy (`SUPER_ADMIN`/`FINANCE_STAFF`/
`FINANCE_MANAGER`/`AUDITOR`) is a genuinely different, narrower allowlist
than `applicant`'s own (`SUPER_ADMIN`/`ADMISSIONS_MANAGER`/
`FINANCE_STAFF`/`FINANCE_MANAGER`/`AUDITOR`, plus a counselor's own
assigned rows) — `ADMISSIONS_MANAGER` and `ADMISSIONS_COUNSELOR` can see
the applicant but not the finance record. A pre-check against `applicant`
first would produce a misleading `"applicant not found"` for a caller who
can plainly see the applicant; the 404 this endpoint actually returns
(`"finance record not found"`) correctly names what is actually missing.

**RBAC for this whole file**: every route depends on
`require_role_session` passed all six `RoleCode` values — functionally a
no-op gate, present only for the established `(user, db)`-from-one-
transaction pattern. All narrowing is RLS's job, per the module prompt's
own instruction ("no new RLS or RBAC, just wire the existing
`require_role_session`-scoped session through").

### `app/routers/payment_claim.py` — `GET /finance/payment-claims`

Standalone list, independent of any applicant/finance_record id,
filterable by `status` (`PENDING`/`CONFIRMED`/`REJECTED`, query param
name `status`, Python attribute `claim_status` to avoid shadowing the
`fastapi.status` module already imported in this file). **Unlike the
applicant-read routes above, this endpoint enforces its own explicit
role allowlist** (`SUPER_ADMIN`/`FINANCE_STAFF`/`FINANCE_MANAGER`/
`AUDITOR` — the same four roles `payment_claim`'s own RLS policy already
scopes to) rather than relying on RLS alone to narrow an otherwise
unrestricted list route. This is a deliberate difference from
`applicants_read.py`, not an inconsistency: for a *list* endpoint
specifically, a role outside the intended audience getting a clean 403 is
more honest than getting a 200 with an empty `items` list that looks
identical to "you're allowed here, there's just nothing yet" — verified
live which of the two actually happens (see below).

### `app/routers/import_batches_read.py` — `GET /import-batches`

Paginated list (same `limit`/`offset` shape as `/applicants`) returning
each batch's `created_count`/`updated_count`/`flagged_count`/
`rejected_count` breakdown already on the table since Module 02's
migration `0008_import_batch_counts`. Same explicit-role-gate reasoning
as the payment-claims list: `SUPER_ADMIN`/`ADMISSIONS_MANAGER`/`AUDITOR`,
the exact allowlist `import_batch`'s own RLS policy already carries.

`app/main.py` registers both new routers.

## Verification against the live stack

All verification below is real HTTP calls (`curl`) against the running
`api` container on `127.0.0.1:38210`, with real session cookies from
actual logins, real seeded data (not a single fixture row), and direct
`psql`/audit-log checks — not code review alone.

**Seed data used**: two `ADMISSIONS_COUNSELOR` accounts, one with 30
applicants (`counselor A`, split across `CS`/`ECE` programs and
`IMPORTED`/`APPLIED` statuses in a known pattern — specifically to cross
the default `limit=25` page boundary with one counselor's own real data,
not a synthetic single row), one with 3 (`counselor B`, `MBA`/
`Spring2027`, entirely disjoint from counselor A's programs/intake cycle
so a filter false-positive would be caught). One `ADMISSIONS_MANAGER`,
one `AUDITOR`. Module 03's leftover `FINANCE_STAFF`, applicant, and its
`finance_record`/two `payment_claim`s (one `CONFIRMED`, one `REJECTED`)
were reused rather than re-seeded, giving `/applicants/{id}/finance` and
`/finance/payment-claims` real historical data with a genuine mix of
outcomes instead of a fresh, uniform fixture. One real Excel import was
run through the actual `POST /import/applicants` endpoint (not inserted
directly) to give `/import-batches` a real `COMPLETED` batch with real
counts rather than an SQL-inserted stand-in.

### Applicant list — pagination

- Counselor A, `limit=25&offset=0`: 25 items returned, `total: 30`, every
  item's `assigned_counselor_id` counselor A's own id.
- Counselor A, `limit=25&offset=25` (the actual page boundary): exactly
  5 items returned (the remaining applicants past the first page),
  `total: 30` unchanged, `offset: 25` echoed correctly — confirmed no
  overlap with page 1's ids by inspecting both pages' full item sets.
- `limit=101`: 422, FastAPI's own `Query(le=100)` validation, `"Input
  should be less than or equal to 100"` — never reaches the route body.
- `limit=0`: 422, `"Input should be greater than or equal to 1"`.
- `offset=-1`: 422, `"Input should be greater than or equal to 0"`.
- `limit=100` (the accepted max): all 36 applicants (30 + 3 + Module 03's
  1 + 2 from the live import below) returned in one page as manager.
- No query params at all: `limit: 25, offset: 0` in the response,
  confirming the documented defaults.

### Applicant list — RLS scoping and filters

- Counselor A's own list: `total: 30`, zero of counselor B's applicants
  present anywhere across both pages.
- Counselor B's own list: `total: 3`, exactly their own 3 applicants,
  zero of counselor A's 30.
- Manager's list: `total: 34` before the live import, `36` after —
  confirming the manager genuinely sees every applicant across both
  counselors, not merely their own.
- Auditor's list: `total: 36`, matching the manager's count exactly.
- `program=CS` (counselor A): `total: 15`, matching the seeded
  even/odd program split exactly.
- `current_status=APPLIED` (counselor A): `total: 10`, matching the
  seeded `i % 3 == 0` pattern exactly.
- `intake_cycle=Spring2027` (counselor A): `total: 0`, `items: []` —
  counselor A genuinely has zero applicants in counselor B's intake
  cycle, confirming the filter and the RLS scope compose correctly
  together rather than one silently overriding the other.

### Applicant detail — 404-vs-visible

- Counselor A requesting counselor A's own applicant: 200, full detail
  including `import_batch_id`.
- Counselor A requesting counselor B's applicant (exists, RLS-invisible):
  404, `"applicant not found"`.
- Counselor A requesting an all-zero UUID (genuinely does not exist):
  404, `"applicant not found"` — identical response to the RLS-invisible
  case above, by design.

### Status-history — 404-vs-empty-list distinction

- A real transition was driven through the actual `POST
  /applicants/{id}/status` endpoint (not inserted directly) against one
  of counselor A's applicants: `IMPORTED -> APPLIED`, 200.
- That applicant's status-history, requested by counselor A (owns it):
  `{"items": [{...one event, from_status: IMPORTED, to_status: APPLIED,
  changed_by: counselor A's own id, note: "m4 test transition"...}]}` —
  the real transition, correctly attributed.
- The **same** applicant's status-history, requested by counselor B (does
  not own it): 404, `"applicant not found"` — confirmed this is a 404,
  not `{"items": []}`, which would have been silently wrong (indistinguishable
  from "you can see this applicant and it just has no history").
- Module 03's leftover applicant (status set via a direct `psql UPDATE`
  during that module's setup, never through the real transition
  endpoint), requested by its manager owner: `{"items": []}` — genuinely
  correct, not a bug: this applicant really has zero
  `application_status_event` rows, because its status was never moved
  through the endpoint that creates them. This is the live-verified
  positive case for "an applicant visibly exists but genuinely has no
  history yet," distinct from the 404 case immediately above.

### Applicant finance — narrower RLS than the applicant itself

- `FINANCE_STAFF` requesting Module 03's applicant's finance summary:
  200, `finance_record_id`, `total_fee_due: 500000.00`, `total_paid:
  100000.00` (the real Module 03 rollup, unchanged), and both historical
  `payment_claim`s (one `CONFIRMED`, one `REJECTED`) in full detail.
- `ADMISSIONS_MANAGER` requesting the **same** applicant's finance
  summary (the manager can see the applicant itself — confirmed
  separately via the list endpoint above showing it in their `total: 34`)
  : 404, `"finance record not found"` — the applicant is visible to this
  role, the finance record is not, and the response correctly names the
  finance record as what's missing rather than misreporting the
  applicant as not found.
- `FINANCE_STAFF` requesting a genuinely finance-record-less applicant
  (one of counselor A's, never reached `ADMISSION_TAKEN`): 404,
  `"finance record not found"` — the expected, non-error case for "most
  applicants," confirmed against a real applicant, not merely asserted.

### Payment-claims list — standalone, role-gated ahead of RLS

- `FINANCE_STAFF`, no filter: `total: 2`, both of Module 03's historical
  claims present in full detail.
- `status=CONFIRMED`: `total: 1`, only the `CONFIRMED` claim.
- `status=PENDING`: `total: 0`, `items: []` — correctly empty (both
  historical claims are already resolved), not an error.
- `ADMISSIONS_COUNSELOR` requesting this endpoint at all: 403,
  `"insufficient role for this action"` — confirming this is the
  **role-gate** that fires, not RLS producing a silently-empty `200`.
  This was the specific distinction the module prompt called out to
  verify ("a counselor gets an empty list or 403 depending on which
  RLS/RBAC layer is actually doing the blocking") — live-confirmed as
  403, the application-layer role check, fired first.
- `AUDITOR`: `total: 2`, matching finance staff's own count exactly.

### Import-batches list

- Manager, before any import in this fresh volume: `{"items": [], "total":
  0}` — correct empty state, not an error, for "no imports have run yet."
- A real `.xlsx` uploaded through the actual `POST /import/applicants`
  endpoint (2 new rows, both created): batch returned `created_count: 2,
  updated_count: 0, flagged_count: 0, rejected_count: 0`.
- The same batch, read back through `GET /import-batches`: identical
  counts, correct `imported_by` (the manager's own id), correct
  `checksum`, confirming the list endpoint surfaces exactly what the
  import endpoint itself wrote, not a stale or recomputed value.
- `ADMISSIONS_COUNSELOR` requesting this endpoint: 403 — same role-gate
  pattern as the payment-claims list, confirmed live.
- `AUDITOR`: `total: 1`, sees the batch despite never having run an
  import themselves — confirming this is genuine role-based visibility,
  not scoped to "batches you personally ran."

### No sensitive-field leakage

The full `GET /openapi.json` schema (covering every response model in
this module) was searched for `password_hash`/`totp_secret_encrypted` —
zero matches. A raw applicant-list response was independently checked
the same way. Both checks are consistent with the response models never
having declared those fields in the first place (they are not on
`Applicant`/`User` fields these schemas even reference), rather than
merely "didn't happen to appear in this particular response."

### No writes from read endpoints

`audit_log` was queried for any `applicant`/`application_status_event`/
`finance_record`/`payment_claim`/`import_batch` row with an action other
than `INSERT`/`UPDATE` in the verification window: zero rows — and more
directly, zero *new* audit rows at all were produced by any `GET` call
in this module (the only new `audit_log` activity during this session
came from the one real `POST /applicants/{id}/status` transition and the
one real `POST /import/applicants` upload, both deliberately exercised
above to generate real read data, not from any of the six new read
routes themselves).

## Real defects found and fixed during this module

None. Every endpoint worked as designed on first live test — no RLS
policy needed correction, no 404-vs-empty-list case came back wrong, and
no pagination boundary produced an off-by-one. This is consistent with
the module's own scope: no new RLS, no new RBAC, no new schema — every
endpoint is a thin read over policies and tables Modules 01-03 already
built and already live-verified in their own reports, so there was
substantially less new surface for a defect to hide in than in a module
introducing new triggers or RLS policies.

## Cleanup

All ad hoc seed/xlsx-generation scripts and curl cookie jars used for
this module's live verification (`api/m4_seed.py`,
`api/m4_make_xlsx.py`, `m4_*_cookies.txt`, `m4_*.json`, `m4_import.xlsx`)
were deleted after verification completed; none were staged or
committed. The seeded test users/applicants/import batch created for
this module remain in the running dev stack's database, same as every
prior module's own test data — disposable Docker Compose dev state, not
committed to git.

## Definition of done

- [x] `GET /applicants` — paginated, filterable, RLS-scoped automatically.
- [x] `GET /applicants/{id}` — 404 on nonexistent/RLS-invisible.
- [x] `GET /applicants/{id}/status-history` — chronological, same
      visibility as the applicant, correct 404-vs-empty-list.
- [x] `GET /applicants/{id}/finance` — 404 when genuinely absent or
      RLS-invisible under `finance_record`'s own narrower policy.
- [x] `GET /finance/payment-claims` — standalone, filterable by status.
- [x] `GET /import-batches` — full outcome-count breakdown.
- [x] Every response through a hand-declared Pydantic model; verified no
      sensitive field leakage via the full OpenAPI schema.
- [x] No new RLS policy, no new RBAC role — every route reuses
      `require_role_session` and existing table policies exactly as-is.
- [x] Live-verified: counselor-scoped vs manager-sees-all, pagination at
      a real page boundary, 403-vs-empty-list on the role-gated list
      endpoints, 404-vs-empty-list on status-history and finance.
- [x] Report committed as `reports/module-04-read-endpoints.md`.

## Follow-up verification

Two gaps in this module's own original verification, closed against the
same live stack and the same seed data already sitting in it — no new
seeding. Both checks confirmed the existing design; neither surfaced a
real defect, so no code change was needed.

### 1. Applicant-list filters combine with AND, not one overriding the other

The original report verified `program=CS` (`total: 15`) and
`current_status=APPLIED` (`total: 10`) as counselor A **individually**,
but never in the same request — leaving open whether `list_applicants`'s
`filters` list (`app/routers/applicants_read.py`) genuinely `AND`s every
active filter together, or whether a bug (e.g. only the last-applied
`.where()` call taking effect, or one filter silently short-circuiting
the query builder) would let one filter quietly win over the other while
still returning a plausible-looking response.

Requested `GET /applicants?program=CS&current_status=APPLIED&limit=100`
as counselor A against the live stack. Result: `total: 6`, six items,
applicants A00/A06/A12/A18/A22/A24. Cross-checked against the seed
pattern used to build this data (`program = CS if i % 2 == 0 else ECE`,
`current_status = APPLIED if i % 3 == 0 else IMPORTED`, for `i` in
`0..29`, documented in the original report and since cleaned up per this
module's own artifact-cleanup discipline): five of the six returned
indices (`0, 6, 12, 18, 24`) are exactly the values divisible by both 2
and 3 from the original seed pattern; the sixth, `A22`, is `CS` (even)
and was separately transitioned to `APPLIED` via the real `POST
/applicants/{id}/status` call already made earlier in this module's own
original verification (see "Status-history — 404-vs-empty-list
distinction" above) rather than by the seed pattern itself. Both sources
of `APPLIED`-status CS applicants are correctly reflected in the
combined-filter result.

This is the mathematically exact intersection of "CS" (15 applicants)
and "APPLIED" (10 applicants) — `6 < 15` and `6 < 10`, satisfying the
review's own sanity check that the combined total be strictly smaller
than either individual filter's total, not equal to either (which would
indicate one filter being ignored) and not their sum or union (which
would indicate `OR` instead of `AND`). Every one of the six returned
items was independently confirmed to carry both `"program":"CS"` and
`"current_status":"APPLIED"` by searching the raw response for any
`"program":"ECE"` or `"current_status":"IMPORTED"` occurrence — zero
matches for either, confirming no mismatched row leaked through under
either field. No code change needed; `list_applicants`'s `for f in
filters: ... query.where(f)` loop genuinely composes every active filter
with `AND`, exactly as written.

### 2. The two new role-gates, tested against the role most likely to reveal over-inclusion

The original report verified each role-gated list endpoint's exclusion
against `ADMISSIONS_COUNSELOR` — a role with no plausible reason to be
included in either allowlist, and the least interesting negative case
for catching an accidentally-too-broad `_LIST_ROLES` tuple, since nobody
would expect a counselor to slip through by coincidence. The two roles
genuinely worth testing are the ones with *some* adjacent legitimate
claim to the data: `ADMISSIONS_MANAGER` (broad applicant visibility
everywhere else in this system) against `/finance/payment-claims`, and
`FINANCE_STAFF` (a real, active finance role) against `/import-batches`.

- `GET /finance/payment-claims` as `ADMISSIONS_MANAGER`: 403,
  `"insufficient role for this action"` — confirmed the manager's broad
  applicant-list visibility (verified extensively in the original
  report, `total: 34`/`36` across both counselors) does **not** extend to
  this endpoint's own `_LIST_ROLES` tuple
  (`SUPER_ADMIN`/`FINANCE_STAFF`/`FINANCE_MANAGER`/`AUDITOR`), which
  correctly does not include `ADMISSIONS_MANAGER` at all.
- `GET /import-batches` as `FINANCE_STAFF`: 403, same message — confirmed
  a real, TOTP-enrolled, actively-used finance role in this system does
  **not** fall inside this endpoint's own `_LIST_ROLES` tuple
  (`SUPER_ADMIN`/`ADMISSIONS_MANAGER`/`AUDITOR`), which correctly does
  not include `FINANCE_STAFF`.
- Both negative cases were paired with a positive sanity check against
  the *same* two role/endpoint combinations from the other direction, to
  confirm the gates are precisely scoped rather than accidentally too
  narrow in the process of being correctly not-too-broad: `FINANCE_STAFF`
  against `/finance/payment-claims` still returns `200`/`total: 2` (its
  own legitimate endpoint), and `ADMISSIONS_MANAGER` against
  `/import-batches` still returns `200`/`total: 1` (its own legitimate
  endpoint, the real batch from the original report's live import).

Both role-gates are exactly as narrow as intended — no accidental
over-inclusion in either direction, and no accidental exclusion of a
role that does belong. No code change needed.

