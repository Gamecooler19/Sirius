# Module 21 -- Bounded Edge-Case Audit

## Scope

A bounded audit against five named categories, each verified live
against the real running Docker stack (no mocked data, no inferring
correctness from reading code alone), following this project's own
established discipline from every prior module. Not an open-ended
"make it perfect" pass -- exactly the categories and depth the module
prompt specified, no more:

1. **Concurrency** -- beyond what was already individually proven
   (two managers racing a claim resolution, a stale-queue confirm):
   three new real races.
2. **Scale** -- pagination/filtering/aggregation against hundreds of
   real seeded rows, not a handful.
3. **Input boundaries** -- extremely long strings, zero/negative
   payment amounts, unicode/emoji, and injection-shaped filter values
   against real parameterized queries.
4. **Frontend resilience** -- a genuine unhandled render exception,
   observed in a real browser, not inferred from `react-error-boundary`
   usage in the source.
5. **Precision** -- fractional-paisa rounding drift across
   submit/confirm/reconciliation, and UTC-storage-vs-browser-render
   timestamp consistency across a real timezone offset.

Every finding below states concrete live evidence. Three genuine,
previously-undiscovered defects were found and fixed (payment-claim
non-positive amounts, the missing frontend error boundary, and the
UTC-timestamp-serialization bug). Two categories (concurrency, scale)
produced no defects -- documented with the same evidentiary rigor as
the ones that did, not skipped because nothing was wrong. Where
something was found but deliberately not fixed, the reasoning is
stated explicitly, the same standard Module 15's role-change gap and
Module 20's click-through limitation already set.

## 1. Concurrency

Three real races fired against the live stack, each genuinely
concurrent (both calls dispatched before either could complete, not
merely issued back-to-back).

### 1.1 Role change racing a self-service TOTP reset on the same account

`financemanager@sirius.app`'s role-code (`PATCH /users/{id}` as
`SUPER_ADMIN`) and its own `POST /auth/totp/self-reset` call (as
itself, from its own live session) were fired at the same instant
against the same account.

**Result: no defect.** Both writes landed correctly --
`role_code` changed to `ADMISSIONS_COUNSELOR`, the TOTP secret was
genuinely replaced (`totp_secret_encrypted` changed, `totp_enabled`
flipped to `false`), confirmed via a direct DB read immediately after.
SQLAlchemy's ORM issues column-level `UPDATE`s for only the attributes
each transaction actually touched, not a whole-row overwrite, so the
two transactions did not stomp each other despite touching the same
row concurrently. The account's session was correctly flipped back to
TOTP-pending (confirmed: a subsequent `GET /finance/payment-claims`
on the same session returned a real `401`, "two-factor verification
required," until it re-enrolled). Role reverted back to
`FINANCE_MANAGER` afterward.

### 1.2 Two devices mid-TOTP-enrollment for the same account at once

Two separate, genuinely distinct sessions for `auditor@sirius.app`
(a never-enrolled account) both called `POST /auth/totp/enroll/start`.
Per `totp_enroll_start`'s own documented behavior ("re-calling start...
overwrites the prior unconfirmed secret"), Device B's call genuinely
overwrote Device A's freshly-provisioned secret.

**Result: no defect -- the documented overwrite behavior holds
correctly under a real two-device race.** Device A's own subsequent
`POST /auth/totp/enroll/confirm`, using a live code generated from its
own (now-stale) secret, was correctly rejected with a real `400
invalid TOTP code`. Device B's confirm, using a live code from the
secret that actually won the race, succeeded with a real `204`. No
data corruption, no account left in an inconsistent state. A genuine,
minor UX gap is disclosed here rather than fixed: Device A receives no
signal that its QR code/backup codes are already worthless the instant
Device B overwrites them -- it only discovers this when its own
confirm fails. **Deliberately not fixed in this pass**: closing it
would need either a push notification to the other session (this
project's Module 20 push infrastructure could theoretically carry it,
but no route today fires one for this event) or a fundamentally
different enrollment-locking design, both larger changes than a
bounded input/concurrency audit warrants; flagging it precisely, with
live evidence, is the audit's job here, not redesigning enrollment.

### 1.3 Admin deactivation racing the instant redemption of that same account's own password-reset token

`newhire@sirius.app`'s real password-reset token (obtained via the
actual `forgot-password` -> Mailpit flow) was redeemed
(`POST /auth/reset-password`) at the same instant `SUPER_ADMIN`
deactivated the account (`PATCH /users/{id}` with `is_active: false`).

**Result: no defect.** Both writes landed correctly and independently
-- the password was genuinely changed (confirmed: the real, freshly-set
password subsequently fails login with the *same* generic
`"invalid email or password"` a genuinely wrong password gets, not a
different error), and the account's `is_active` flag was set to
`false`. Critically, `get_scoped_session`'s existing "check `is_active`
fresh, every request" design (established in an earlier module, not
new to this one) means the deactivation wins for all practical
purposes regardless of ordering: `POST /auth/login`'s own `is_active`
check runs before the password comparison, so a deactivated account
cannot log in even with a freshly-and-correctly reset password.
Restored `is_active: true` afterward.

**Category summary: zero defects found across all three concurrency
races.** Each result is a genuine, live-verified confirmation that the
existing design (column-level ORM updates, documented enrollment
overwrite semantics, fresh-per-request `is_active` checks) holds under
real concurrent load, not an assumption.

## 2. Scale

### 2.1 Applicants list -- pagination, filtering, aggregation, RLS

300 real applicant rows were seeded directly into Postgres (via a real
`INSERT ... SELECT FROM generate_series`, with the RLS session GUCs
set exactly as a real authenticated request would set them, so the
`write_audit()` trigger fired for every row exactly as it would for a
real request), distributed across 5 programs, 3 intake cycles, and all
8 `ApplicationStatus` values, bringing the real `applicant` table to
**312 rows** for the duration of this check (317 at peak, including 5
more from the input-boundary tests below).

**Pagination math -- exact at every tested offset, no off-by-one, no
crash beyond the end of the dataset:**
- `limit=25&offset=0`: `total=312`, `items.length=25` -- correct.
- `limit=25&offset=300` (the real last, partial page): `items.length=12`
  (`312 - 300 = 12`) -- exact.
- `limit=100&offset=250` (a page whose own end overlaps the total):
  `items.length=62` (`312 - 250 = 62`) -- exact.
- `limit=25&offset=1000` (an offset far beyond the real total):
  `total=312`, `items=[]` -- a clean empty page, no negative-index
  crash, no 500.

**Filtering -- exact against real ground truth, not merely "returns
something plausible."** A direct `GROUP BY current_status` query
against the real table gave `IN_PROCESS: 40`;
`GET /applicants?current_status=IN_PROCESS` returned `total: 40` --
an exact match, not an approximation.

**Aggregation (`GET /applicants/summary`, the Home dashboard's own
data source) -- every one of the 8 status buckets matched real
`GROUP BY` ground truth exactly**, `total: 312` correct.

**RLS scoping holds correctly at 312+ rows, not only at a handful.**
`admissionscounselor@sirius.app` (with exactly 2 real applicants
assigned to it out of the 312) still saw `total: 2` through
`GET /applicants` -- RLS's row-level narrowing does not degrade or
leak at volume.

**Speed -- fast, not merely "eventually returns."** Every list/summary
call measured well under 100ms warm (a cold first-call outlier around
370ms, consistent with connection-pool warm-up, not a per-request
cost).

All 300 seeded rows and their `application_status_event` rows were
deleted after this check, confirmed by a direct `SELECT count(*)`
returning `12` (the exact pre-audit baseline) afterward.

### 2.2 Reconciliation/dashboard aggregation -- real volume, not the applicant-only case

**Self-correction, stated explicitly rather than silently fixed.** The
first pass of this audit tested pagination/filtering/aggregation only
against the `applicant` table (section 2.1 above) and never actually
seeded `finance_record`/`payment_claim` volume -- `GET /finance/
reconciliation`'s own two-query join-avoidance design (Module 05) had
only ever run against the original 2 `finance_record`/3
`payment_claim` rows throughout the whole audit, the exact same
handful-of-rows case every module's own prior verification already
covered. The original version of this report claimed reconciliation
was checked "with the extra volume in play" -- that claim was false,
caught on a self-review re-read of the module prompt against the
actual evidence gathered, not caught by the user. Closed for real
here, not left overstated.

150 real applicants were moved through a genuine two-step status
transition (`ADMISSION_OFFERED` -> `ADMISSION_TAKEN`, `OLD != NEW`,
exactly matching what a real `POST /applicants/{id}/status` call
does) so the real `applicant_create_finance_record()` trigger fired
150 times, producing 150 real `finance_record` rows. Each was given a
real, varying `total_fee_due` (`200000`-`400000`, cycling). 300 real
`payment_claim` rows were created against them (100 `PENDING`, 100
`REJECTED`, and 100 moved through a genuine `PENDING -> CONFIRMED`
transition -- tracked by id in a temp table first, specifically so the
real `payment_claim_confirmed_increments_total_paid()` rollup trigger
fired for exactly the intended 100 rows and not the pre-existing
genuinely-`PENDING` ones), varying amounts and payment modes, spread
across all three real intake cycles. This brought the real
`finance_record`/`payment_claim` tables to **152 records / 303
claims** for the duration of this check -- a real multi-claim-per-
record case, not the original 1-2-claims-per-record toy shape.

**Result: exact at every aggregation level, no defect.** A direct
`GROUP BY intake_cycle` ground-truth query against `finance_record`
gave `Fall2026: 52 records, 15100000.00 fee due, 2340000.00 paid`
(and the matching real totals for `Fall2027`/`Spring2027`).
`GET /finance/reconciliation` returned the identical figures exactly,
per cycle and in the combined `totals` block
(`total_fee_due: 45000000.00`, `total_paid: 6300000.00`,
`finance_record_count: 152`) -- and the per-status claim breakdown
correctly reflected the real confirm-trigger's own effect
(`CONFIRMED: 102 claims, 6300000.00` -- exactly the 100 newly-
confirmed plus the 2 pre-existing ones, matching `total_paid` to the
cent). Confirmed identically in the real, live browser UI via
screenshot: every figure in both the top-level totals cards and the
per-cycle table matches. `GET /finance/reconciliation` measured
~35ms warm at this real volume -- the two-query, no-fan-out design
(Query A: `finance_record` totals with no join to `payment_claim`;
Query B: `payment_claim` counts/amounts joined only as far as
`finance_record`) holds its own documented correctness and speed
guarantee at real multi-claim volume, not only in the toy 1-2-claim
case every prior module's own verification happened to use.

All 150 seeded applicants, their `finance_record`/`payment_claim`
rows, and any `application_status_event` rows were deleted after this
check; confirmed via direct queries returning `applicants: 12`,
`finance_records: 2`, `claims: 3`, `total_paid_sum: 550000.00` --
the exact pre-audit baseline across every one of these tables.

**Category summary: zero defects found**, now genuinely covering both
the applicant-list case and the reconciliation/dashboard-aggregation
case the module prompt explicitly named, not only the former.

## 3. Input boundaries

### 3.1 Extremely long strings -- **real defect found and fixed**

Before this fix, no schema anywhere in this codebase (confirmed by a
full grep for `max_length` across `api/app/schemas/`: zero matches)
bounded a text field's length at all, and no `applicant` column
declared a length limit at the Postgres level either
(`character_maximum_length` was `NULL` for `full_name`/`program`/
`intake_cycle`/`email`/`phone`, confirmed via `information_schema.
columns`).

A genuine 10,000-character `full_name` submitted through
`POST /applicants` was accepted with a real `201`, stored in full
(confirmed: `SELECT length(full_name)` returned exactly `10000`), and
then visually broke `ApplicantsPage`'s own table: the row's text
overflowed its cell with no truncation, pushing the email/program/
intake-cycle/status columns off-screen -- confirmed via a real
screenshot of the live browser.

**Fixed, bounded scope, not a full-stack pass:**
- `api/app/schemas/applicant_create.py`: `full_name`/`program`/
  `intake_cycle` now `Field(min_length=1, max_length=255)`,
  `phone` `Field(max_length=255)` -- re-verified live: the identical
  10,000-char payload now gets a real `422`
  (`"String should have at most 255 characters"`); a legitimate
  200-char name still succeeds with a real `201` (no false-positive
  rejection).
- `frontend/src/applicants/ApplicantsPage.tsx`: every free-text
  `Table.Td` (`full_name`/`email`/`program`/`intake_cycle`) now has a
  `maxWidth`/`overflow: hidden`/`textOverflow: ellipsis`/
  `whiteSpace: nowrap` style plus a native `title` tooltip carrying
  the full value -- re-verified live via screenshot: the same
  pre-existing 10,000-char row (created before the fix, still in the
  table) now renders as a clean, truncated single line with the
  table's own column alignment fully intact.

**Deliberately left unfixed in this pass, disclosed explicitly:**
`UserCreateRequest.full_name`, `ChangeNameRequest.full_name`,
`PaymentClaimSubmitRequest.reference_number`,
`PaymentClaimResolveRequest.note`, and the Excel-import path's own
row-level text fields all share the identical unbounded pattern.
Fixing only `POST /applicants` (the one endpoint this audit actually
exercised, and the one every applicant-creation path -- including
Excel import -- ultimately writes into the same `applicant` table
this schema alone directly guards) is the proportionate, bounded scope
for this pass; a full sweep of every text field in the codebase is a
larger, separate piece of work, not silently rolled into this one.

### 3.2 Zero/negative payment-claim amount -- **real, severe defect found and fixed**

Before this fix, neither `PaymentClaimSubmitRequest` nor any database
constraint rejected `amount <= 0`.

- `amount: 0` submitted via `POST /finance/payment-claims` (as
  `financeviewer@sirius.app`, `FINANCE_STAFF`): accepted with a real
  `200`.
- `amount: -50000` submitted the same way: also accepted with a real
  `200` -- **and, once confirmed by `superadmin@sirius.app`
  (`SUPER_ADMIN`, a real, ordinary maker-checker action, not a special
  bypass), the existing `payment_claim_confirmed_increments_total_paid()`
  trigger (migration 0009) added that negative amount to
  `finance_record.total_paid` exactly as it adds any other confirmed
  claim's amount.** Observed live: a genuine, real `250000.00` dropped
  to `200000.00` from one confirmed negative claim, and the
  corruption propagated straight into `GET /finance/reconciliation`'s
  own aggregate totals with zero error, warning, or audit distinction
  from a legitimate payment. This is real, silent financial-data
  corruption through an ordinary, documented, intended workflow -- not
  a contrived edge case.

**Fixed at both layers, defense-in-depth, matching this project's own
ADR-07 precedent:**
- `api/app/schemas/payment_claim.py`: `amount: Decimal = Field(gt=0)`
  (strictly greater than zero, not `ge=0` -- a `0.00` "payment" is not
  a real transaction either).
- `api/alembic/versions/0013_positive_amount.py`: a matching
  `CHECK (amount > 0)` database constraint
  (`ck_payment_claim_amount_positive`), the same "an application-layer
  check alone is one omitted call path away from being wrong"
  reasoning this project already applies to
  `ck_payment_claim_distinct_submitter_confirmer`.

**Re-verified live at both layers, not merely re-read:**
- The same `amount: 0` and `amount: -50000` payloads now get a real
  `422` (`"Input should be greater than 0"`) from the schema.
- A raw SQL `INSERT` with `amount = -1` (as `FINANCE_STAFF`, bypassing
  Pydantic entirely) was rejected by the real database with
  `ERROR: new row for relation "payment_claim" violates check
  constraint "ck_payment_claim_amount_positive"` -- the defense-in-depth
  layer genuinely works independently of the application layer.
- `finance_record.total_paid` was manually restored to its correct,
  original `250000.00` (the negative claim's effect reversed) before
  the test claims were deleted; confirmed via a direct DB read.

**An incidental deployment defect found and fixed along the way,
documented in the migration's own docstring rather than glossed
over:** the migration's first attempt used the revision id
`0013_payment_claim_positive_amount` (34 characters), which made the
migration's own final `UPDATE alembic_version SET version_num = ...`
step raise a real `StringDataRightTruncationError`
(`alembic_version.version_num` is `character varying(32)`), rolling
the entire migration back cleanly (confirmed: both `alembic_version`
and the table's own constraints were still at their pre-migration
state afterward, exactly as "assume transactional DDL" promises).
Fixed by shortening the revision id to `0013_positive_amount`
(20 characters), not by widening the shared `alembic_version` column.

### 3.3 Unicode/emoji -- no defect found

A real applicant with `full_name = "Zoë 田中太郎 🎓✨ مرحبا שלום Ñoël"`
and `program = "CS 🖥️"` (Latin diacritics, CJK, emoji, and mixed
RTL Arabic/Hebrew in the same string) was submitted through
`POST /applicants`: accepted with a real `201`, stored and read back
byte-for-byte correct via a direct DB query, and rendered correctly in
the real browser UI (confirmed via screenshot) -- correct glyphs, no
mojibake, no layout break from the RTL segment, table alignment
intact.

### 3.4 Injection-shaped values against real parameterized queries -- no defect found

Both the **read** path (`GET /applicants?program=...`) and the
**write** path (`POST /applicants` with `program` set to an
injection-shaped literal) were tested with real payloads, not
hypothetical ones:

- `program = "CS'; DROP TABLE applicant; --"` as a filter value:
  real `200`, `items: []` (the string is correctly treated as a
  literal value with no row matching it, not executed as SQL) --
  confirmed the `applicant` table still existed and held its expected
  row count immediately after.
- `program = "' OR '1'='1"` as a filter value: real `200`,
  `items: []` -- confirms the parameterization genuinely holds (a real
  injection bypass would have returned all 312 rows via the tautology,
  not zero).
- `intake_cycle = "'; UPDATE applicant SET full_name='HACKED'; --"`
  as a filter value: real `200`, `items: []` -- confirmed via a direct
  `SELECT count(*) FROM applicant WHERE full_name = 'HACKED'` returning
  `0` immediately after; no row was actually mutated.
- The identical injection-shaped string (`"CS'; DROP TABLE applicant;
  --"`) submitted as a real, legitimate `program` *value* via
  `POST /applicants` (the write path, not the filter/read path): a
  real `201`, stored and read back verbatim as literal text -- the
  correct behavior, since this is legitimate user input that merely
  happens to look like SQL, and SQLAlchemy's parameterized queries
  hold on the write side exactly as on the read side.

SQLAlchemy's own parameter binding holds completely against every
payload tried, on both the filter/read path and the create/write path.

## 4. Frontend resilience -- **real defect found and fixed**

**Before this fix:** `frontend/src/app/router.tsx` declared no
`errorElement` on any route. A genuine unhandled render-time exception
was forced live (not hypothesized) by patching `window.fetch` in the
real, running browser to return a malformed
`GET /applicants/summary` shape (`{"total": 5, "by_status": null}` --
the same class of failure a real backend/frontend contract drift would
cause) and then triggering a real re-fetch via genuine SPA navigation
(not a hard reload, which would have lost the patch).

**Result: not a blank white screen** (the literal premise this check
set out to verify) -- react-router's own render-time error handling
did catch the exception and render *something*. But that something was
react-router's raw, unstyled default fallback: a full-page, top-to-
bottom JavaScript stack trace with **zero app chrome** (no header, no
nav, no logo) and, in the fallback's own on-screen text, an explicit
"Hey developer... you can provide a way better UX than this." A real
accessibility-tree query (`interactables`) against this screen returned
**zero interactable elements** -- confirmed, not assumed: a genuine
dead end for a real, non-technical user, indistinguishable in practice
from the blank-screen failure mode this check was written to catch.

**Fixed:** `frontend/src/app/RouteErrorBoundary.tsx` -- a real,
on-brand fallback component (Mantine `Center`/`Stack`/`Alert`, the
same component library every other page already uses) wired as the
`errorElement` on every top-level route in `router.tsx` (each
standalone unauthenticated route needs its own, since react-router's
`errorElement` inheritance only covers descendants of the route that
declares it; the single authenticated `/` route's own `errorElement`
covers every page under `AppShellLayout`). Shows the real underlying
error message (useful for support), states explicitly that no data was
changed, and provides one real recovery action: a "Back to home"
button that performs `window.location.assign("/")`, a genuine full
navigation (not a soft state reset) that reliably recovers from a
render-time exception whose root cause a client-side retry could not.

**Re-verified live, not merely re-read:** the identical malformed-fetch
patch and identical SPA-navigation trigger were re-run against the
fixed router. Result: a real screenshot shows the new fallback UI --
warning icon, "Something went wrong," the real error text
(`"can't access property "map", data.by_status is null"`) in a red
alert, and a working "Back to home" button. Clicking that real button
was itself tested: it performed a genuine navigation and the app
recovered to a fully working Home page afterward (confirmed via
`get_content`, not merely "no error thrown"). `tsc --noEmit` (run
inside the real `frontend` container) confirmed clean, both before and
after this fix.

## 5. Precision

### 5.1 Fractional paisa amount -- no defect found

A real payment claim with `amount = "33333.33"` was submitted, then
confirmed. `finance_record.total_paid` moved from `300000.00` to
`333333.33` exactly (`300000.00 + 33333.33`, confirmed via a direct DB
read) -- no rounding, no floating-point drift, because
`payment_claim.amount`/`finance_record.total_paid` are Postgres
`numeric(12,2)` (exact fixed-point decimal, not IEEE 754 float) end to
end, and SQLAlchemy's `Decimal` mapping preserves that exactness all
the way through Python. `GET /finance/reconciliation`'s own aggregate
(`583333.33` = `250000.00 + 333333.33`) was equally exact, in both the
top-level totals cards and the per-cycle table, confirmed via a real
screenshot of the live UI showing the precise figure in every location
it appears.

### 5.2 UTC-storage-vs-browser-render timestamp consistency -- **real, systemic defect found and fixed**

**Before this fix:** every timestamp column in this schema is
`timestamp without time zone` (confirmed via
`information_schema.columns`), and this codebase's own established
convention throughout (e.g. `app.routers.auth`'s repeated
`datetime.now(timezone.utc).replace(tzinfo=None)`) is "store a naive
value that is *implicitly* UTC." Pydantic's default JSON serialization
of a naive `datetime` produces a string with **no `Z` suffix and no
`+00:00` offset** -- e.g. `"2026-09-27T15:20:40.709030"`.

This is a real defect, not a theoretical spec-compliance nitpick,
confirmed with concrete evidence: the host machine's own clock (via
`Get-Date`) read `2026-09-27T20:51:31 +05:30` (IST) at the moment a
real payment claim was confirmed; Postgres's own `now()` read
`2026-09-27 15:21:29+00` (UTC) at the same instant -- a genuine,
observable 5.5-hour offset between server storage and the real local
viewer, not a hypothetical one. The API returned that claim's own
`created_at` as `"2026-09-27T15:20:40.709030"` (no offset marker). A
direct test in the real, live browser confirmed the actual parsing
consequence:

```
new Date("2026-09-27T15:20:40.709030")
  .toISOString()      -> "2026-09-27T09:50:40.709Z"   (WRONG -- the
                                                         browser silently
                                                         re-interpreted
                                                         the string as
                                                         its own local
                                                         time and
                                                         "corrected" it
                                                         backward again)
  .toLocaleString()    -> "27/9/2026, 3:20:40 pm"       (WRONG -- should
                                                         read 8:50:40 pm)
```

And confirmed visually in the real, live UI (`FinancePage`'s own
"Submitted" column, via `new Date(claim.created_at).toLocaleString()`):
the row displayed **"27/9/2026, 3:20:40 pm"** for an event that
genuinely happened at **20:50 IST**. Every timestamp displayed
anywhere in this app -- payment-claim submission/confirmation times,
applicant `created_at`/`updated_at`, status-history event times,
import-batch timestamps, user `last_login_at`/`activated_at` -- was
silently wrong by whatever offset separates the viewing browser's own
timezone from UTC, with zero error, warning, or visual indication
anything was off.

**Fixed at the serialization layer, not storage or any frontend file:**
`api/app/schemas/_datetime.py` introduces `UtcDatetime`, a Pydantic
`Annotated[datetime, PlainSerializer(...)]` type that attaches
`timezone.utc` to a naive value before calling `.isoformat()`,
producing e.g. `"2026-09-27T15:20:40.709030+00:00"`. Applied to every
response-schema `datetime` field across the codebase --
`app/schemas/reads.py` (`ApplicantSummary`/`StatusHistoryEvent`/
`PaymentClaimDetail`/`ImportBatchSummary`), `app/schemas/
payment_claim.py` (`PaymentClaimResponse.confirmed_at`),
`app/schemas/import_batch.py` (`ImportBatchResponse.completed_at`),
`app/schemas/status.py` (`StatusTransitionResponse.created_at`), and
`app/schemas/users.py` (`UserSummary.last_login_at`/`activated_at`/
`created_at`) -- a full, systemic sweep of every timestamp field this
API serializes, not a partial fix scoped only to the one field this
check happened to trip over. **Zero frontend files changed**: every
existing `new Date(...).toLocaleString()` call site already does the
right thing the instant the string itself unambiguously states its
own timezone.

**Re-verified live, exhaustively, not merely re-read:**
- The same real payment claim's `created_at` now serializes as
  `"2026-09-27T15:20:40.709030+00:00"` -- confirmed via a direct API
  call against the rebuilt, redeployed backend.
- The real, live `FinancePage` UI (reloaded, no frontend code
  changed) now displays **"27/9/2026, 8:50:40 pm"** for that exact
  same claim -- matching the real host clock reading captured
  moments before submission almost to the second, the correct,
  verifiable answer.
- A second, independent field (`GET /applicants`'s own `created_at`)
  was spot-checked and confirmed to carry the same `+00:00` marker,
  confirming the fix is systemic across schemas, not a one-off patch
  to the single field this check happened to observe first.
- `tsc --noEmit` (frontend, unchanged by this fix) still clean.

## Follow-up verification

Three gaps in this module's own prior verification, identified after
re-reading the report against what had actually been tested rather
than what was claimed. All three surfaced real, previously-unfixed
defects, not merely confirmed existing correctness -- consistent with
this session's own established pattern (the Module 20 exception-
handling defect, the reconciliation-at-volume self-correction above)
that a "verification" claim not backed by the exact evidence it
implies is a real gap worth closing, not a rounding error.

### Follow-up 1: the long-string fix never protected the Excel-import path

Section 3.1 above fixed `POST /applicants` (`ApplicantCreateRequest`)
with `max_length=255`, and its own docstring claimed this was
sufficient because every other applicant-creation path, including
Excel import, "ultimately funnels through the same `applicant` table
that this schema alone directly guards on the write side." That claim
was never actually tested against the import path -- and it was
false.

**Reproduced live.** A real `.xlsx` was built with three rows: two
ordinary applicants and one with a genuine 5,000-character `Full Name`
cell. Uploaded through the real `POST /import/applicants` (as
`superadmin@sirius.app`, a real TOTP-verified session): the response
was `{"created_count": 3, "rejected_count": 0}` -- the oversized row
was accepted with no rejection at all, and a direct DB read confirmed
it landed in the database in full (`SELECT length(full_name)` returned
exactly `5000`). `app.routers.import_.import_applicants` never
instantiates `ApplicantCreateRequest`; it builds `Applicant` ORM rows
directly from `app.services.excel_import.ParsedRow`, a plain
dataclass parsed straight out of the spreadsheet, completely bypassing
the schema the original fix relied on.

**Fixed, matching this codebase's own existing bad-row-rejection
pattern exactly, not a new convention.**
`app.services.excel_import.parse_workbook` already rejects a row with
a blank `full_name`/`email` individually -- one bad row does not abort
an otherwise-good import of hundreds of rows, and the caller gets a
real, specific reason in `error_detail`, counted under
`rejected_count`. An oversized field (`full_name`, `email`, `phone`,
`program`, or `intake_cycle` exceeding 255 characters) is now rejected
the identical way. A shared `app.core.field_limits.MAX_FIELD_LENGTH`
constant (255) is the single source of truth both
`ApplicantCreateRequest` and `parse_workbook` read from, so the two
application-layer bounds cannot silently drift apart from each other.

**Database-level `CHECK` constraint added as the defense-in-depth
backstop** (migration `0014_applicant_field_length`,
`ck_applicant_{full_name,email,phone,program,intake_cycle}_length`),
the same "an application-layer check alone is one omitted call path
away from being wrong" reasoning this project already applies to the
maker-checker and positive-amount constraints -- covering not just
these two application paths but any future or direct-SQL write
neither of them ever sees. **Verified no existing row violated it
before adding it**, the same "restore the corrupted row first"
precedent the negative-amount fix already established: the one
violating row (this follow-up's own reproduction) was deleted first;
`SELECT ... WHERE length(full_name) > 255 OR ...` confirmed zero
violations immediately before the migration ran.

**Re-verified live, all three layers independently:**
- The identical `.xlsx` re-uploaded against the rebuilt api: real
  `{"created_count": 2, "rejected_count": 1, "error_detail": "row 3:
  field(s) exceed 255 characters (full_name)"}` -- the two good rows
  created, the oversized row rejected individually with a real,
  specific reason, exactly mirroring the existing missing-field
  handling. A direct DB read confirmed the oversized row was never
  stored (`0` matching rows).
- A raw SQL `INSERT` (`app.actor_role='SUPER_ADMIN'`, bypassing both
  `ApplicantCreateRequest` and `parse_workbook` entirely) with a
  300-character `full_name`: rejected by the real database with
  `ERROR: new row for relation "applicant" violates check constraint
  "ck_applicant_full_name_length"`. A second raw insert with a
  legitimate short name succeeded normally -- no false-positive
  rejection.
- `app.schemas.applicant_create.ApplicantCreateRequest`'s own
  docstring corrected to state plainly that this schema only ever
  guarded its own endpoint, not every write path -- the false claim
  is preserved in the docstring's own text (marked as the original,
  incorrect claim) alongside the correction, not silently deleted.

All test applicants/import-batch rows from this follow-up were
deleted afterward; confirmed via direct queries returning
`applicants: 12`, `import_batches: 1` -- the exact pre-existing
baseline.

### Follow-up 2: payment-claim amount had no decimal-precision or magnitude bound

Section 3.2 above fixed `amount <= 0`; the amount field's own decimal
precision and magnitude, relative to its real column type
(`numeric(12, 2)`), had never been tested at all.

**Reproduced live, two distinct failure modes:**
1. **Silent rounding.** `POST /finance/payment-claims` with
   `amount: 100.005` (three decimal places) returned a real `200` with
   `"amount": "100.01"` -- not `100.005` echoed back, not a rejection,
   a silently different value than what was sent. A direct DB read
   confirmed `100.01` was genuinely stored, not a JSON-serialization
   artifact.
2. **A genuine unhandled `500`.** `amount: 99999999999.99` (13
   significant digits -- exceeding `numeric(12, 2)`'s own true
   capacity, confirmed by recomputing the column's real maximum,
   `9999999999.99`, 12 digits total) and `amount: 1e30` both produced
   a real `500 Internal Server Error`. The api container's own logs
   showed the actual cause: an unhandled
   `asyncpg.exceptions.NumericValueOutOfRangeError: numeric field
   overflow`, propagating all the way to the client as an opaque
   `"Internal Server Error"` -- exactly the "an opaque database error
   surfacing as a 500" failure mode this project's own established
   convention says a business-logic rejection must never be, and the
   same class of defect `app.routers.payment_claim`'s own maker-
   checker guard already exists to prevent for a *different* rejection
   reason. Confirmed the crashed transaction left no partial state
   (`finance_record.total_paid` unaffected by Postgres's own rollback).

**Fixed:** `PaymentClaimSubmitRequest.amount` is now
`Field(gt=0, max_digits=12, decimal_places=2)` -- matching
`payment_claim.amount`'s own real column precision and scale exactly,
not an arbitrarily chosen bound.

**Re-verified live, all three cases:**
- `amount: 100.005`: real `422`,
  `{"type": "decimal_max_places", "msg": "Decimal input should have no
  more than 2 decimal places"}`.
- `amount: 99999999999.99`: real `422`,
  `{"type": "decimal_max_digits", "msg": "Decimal input should have no
  more than 12 digits in total"}` -- no more `500`.
- `amount: 1e30`: identical real `422`, same reason.
- **No false-positive rejection**: the column's own true maximum,
  `amount: 9999999999.99` (10 nines plus `.99`, exactly 12 significant
  digits), was submitted and correctly accepted with a real `200`.

Both test claims (the pre-fix `100.005`/`100.01` row and the post-fix
`9999999999.99` row) were deleted afterward -- neither was ever
confirmed, so `finance_record.total_paid` required no reversal;
confirmed via direct query returning `payment_claim` count `3`, the
exact pre-existing baseline.

### Follow-up 3: a programmatic sweep for `UtcDatetime`, and a second real screen

Section 5.2 above fixed the UTC-timestamp-serialization defect and
spot-checked two schema files and one screen (`FinancePage`) by
inspection. Neither check was exhaustive by construction -- a spot
check proves the fields it happens to look at, not the ones it
doesn't.

**Programmatic sweep, not another manual spot check.** A small
AST-based script parsed every `.py` file under `api/app/schemas/`,
resolved each file's own `datetime`/`UtcDatetime` import aliases, and
flagged any class field whose type annotation references a bare
`datetime` name without also referencing `UtcDatetime` (covering
`datetime`, `datetime | None`, and any other structural position the
annotation might place it in). **Self-tested against a deliberately
broken sample file first** (`bad_field: datetime`,
`optional_bad: datetime | None`) to confirm the detector actually
fires rather than silently passing everything -- it correctly flagged
both fields. Run for real against `api/app/schemas/`: **zero
findings** across all 10 schema files. Cross-checked with a plain
grep for the literal string `datetime` across every schema file: every
occurrence is either the `UtcDatetime` import itself, internal to
`app/schemas/_datetime.py`'s own implementation (the definition of
`UtcDatetime`, not a consuming field), or docstring prose -- no schema
file has an unfixed bare-`datetime` field remaining.

**A second real screen, not only `FinancePage`.** A real status
transition was fired (`APPLIED -> IN_PROCESS` on a real seeded
applicant, `Asha Rao`) at a wall-clock time captured immediately
before the call via the host's own clock (`06:50:39 IST`, `+05:30`).
The applicant's own status-history timeline
(`ApplicantDetailDrawer`, a different component from `FinancePage`,
reading a different endpoint, `GET /applicants/{id}/status-history`)
was opened in the real, live browser: it displayed
**`28/9/2026, 6:50:42 am`** for that exact transition -- matching the
real wall-clock reading (a few hundred milliseconds later, consistent
with real network/processing latency, not a timezone discrepancy).
The transition's own note (`"Timezone verification test transition"`)
was also correctly displayed, confirming the right event was being
read. This closes the same class of gap Module 20's own Excel-import-
trigger follow-up already established this session -- a fix "spot
checked" on one path is not yet verified on every path it claims to
cover.

The test status-transition event was deleted and the applicant's
`current_status` restored to its original `APPLIED` value afterward;
confirmed via direct query.

### Cleanup for this follow-up

All test applicants/import batches/payment claims/status-events
created across the three follow-ups above were deleted; confirmed via
direct queries returning `applicants: 12`, `import_batches: 1`,
`payment_claim: 3`, `sum(total_paid): 550000.00` -- the exact same
pre-existing baseline this module's own original cleanup already
established, unchanged by this follow-up round. All temporary Python
helper scripts, `.xlsx` test files, SQL scripts, and curl cookie jars
(both on the host and every `docker cp`'d copy inside the `api`/
`postgres` containers) were deleted; `git status` confirmed a clean
tree (only this follow-up's own five real fix files: two new files,
`api/alembic/versions/0014_applicant_field_length.py` and
`api/app/core/field_limits.py`; three modified,
`api/app/schemas/applicant_create.py`,
`api/app/schemas/payment_claim.py`,
`api/app/services/excel_import.py`) before committing.

## Cleanup performed before treating this module as done

- All 300 seeded `ScaleTest Applicant N` rows and their
  `application_status_event` rows deleted; confirmed via
  `SELECT count(*) FROM applicant` returning `12`, the exact
  pre-audit baseline.
- All 150 seeded `ReconScaleTest Applicant N` rows and their real
  `finance_record`/`payment_claim`/`application_status_event` rows
  (created for the reconciliation-at-volume follow-up, section 2.2)
  deleted; confirmed via direct queries returning
  `applicants: 12`, `finance_records: 2`, `claims: 3`,
  `total_paid_sum: 550000.00` -- the exact pre-audit baseline across
  every one of these tables, not merely the `applicant` table alone.
- All 5 input-boundary test applicants (`longname@example.com`,
  `longname2@example.com`, `legitname@example.com`,
  `unicodetest@example.com`, `injectiontest@example.com`) and their
  status-event rows deleted.
- The real fractional-paisa precision-test claim
  (`PRECISION-TEST-001`) deleted, and its own genuine effect on
  `finance_record.total_paid` (`+33333.33`) manually reversed before
  deletion -- confirmed both `finance_record` rows match their exact
  pre-audit values (`250000.00`/`300000.00`) and `payment_claim`'s own
  row count is back to `3`.
- The two zero/negative-amount boundary-test claims (already deleted
  earlier, mid-section) confirmed absent; `finance_record.total_paid`
  confirmed restored to its correct pre-corruption value
  (`250000.00`) before the migration's own `CHECK` constraint was
  even added, so the constraint's own creation never had to contend
  with a genuinely-violating existing row.
- `financemanager@sirius.app`'s TOTP was left mid-enrollment by the
  concurrency test (a real, expected side effect of that test, not a
  bug) -- completed a fresh, real enrollment afterward so the account
  is left fully working (`totp_enabled: true`), matching this
  project's own established precedent (Modules 18-20) of leaving test
  accounts in a working state, not a broken one.
  `newhire@sirius.app`'s `is_active` was restored to `true`.
  `auditor@sirius.app` was already left fully enrolled and working by
  its own dual-device test.
- All temporary curl-cookie jars (`sa.txt`/`am.txt`/`fm.txt`/
  `fm2.txt`/`fv.txt`/`nc.txt`/`au.txt`/`au2.txt`/`ac.txt`), one-off
  JSON request-body files, one-off Python helper scripts (a
  urllib-based HTTP client used throughout this audit in place of
  curl's own Windows-shell quoting friction, and a TOTP-code
  generator matching Module 20's own established pattern), and every
  `docker cp`'d copy of them inside the `api`/`postgres` containers
  were deleted; `git status` confirmed a clean tree (only this
  module's own real fix files) before committing.

## Final checks

- `tsc --noEmit` (frontend, inside the real `frontend` container):
  clean, both before and after every frontend change in this module.
- `alembic upgrade head`: migration `0013_positive_amount` applied
  cleanly against the real running Postgres instance (after fixing
  its own first-attempt revision-id-length defect, documented in
  section 3.2 above); `ck_payment_claim_amount_positive` confirmed
  present via `pg_get_constraintdef`.
- Both `api` and `migrate` images rebuilt together for every backend
  change in this module (`docker compose build api migrate`) --
  Module 20's own already-documented lesson that Compose caches each
  service's image separately even when both share a Dockerfile/
  context, re-applied correctly throughout this module without
  repeating that defect.
- `git status`: only this module's own files touched --
  new: `api/alembic/versions/0013_positive_amount.py`,
  `api/app/schemas/_datetime.py`,
  `frontend/src/app/RouteErrorBoundary.tsx`; modified:
  `api/app/schemas/applicant_create.py`,
  `api/app/schemas/import_batch.py`,
  `api/app/schemas/payment_claim.py`, `api/app/schemas/reads.py`,
  `api/app/schemas/status.py`, `api/app/schemas/users.py`,
  `frontend/src/app/router.tsx`,
  `frontend/src/applicants/ApplicantsPage.tsx`; no stray temp files.

## Acceptance summary

| Category | Result | Evidence |
|---|---|---|
| Concurrency: role change vs. self-TOTP-reset | No defect | Both writes landed correctly; column-level ORM updates confirmed via direct DB read |
| Concurrency: dual-device TOTP enrollment | No defect (minor UX gap disclosed, not fixed) | Overwrite semantics hold; Device A's confirm correctly 400s, Device B's correctly 204s |
| Concurrency: deactivation vs. reset-token redemption | No defect | Deactivated account cannot log in even with a freshly, correctly reset password |
| Scale: applicants list at 312+ rows | No defect | Every tested offset/filter/aggregate exactly matched real ground truth; RLS scoping intact at volume |
| Scale: reconciliation aggregation at 152 finance_record/303 claim volume | No defect (gap self-corrected mid-audit -- original pass never actually seeded this volume, caught on re-read, closed for real) | Per-cycle and combined totals exactly matched real `GROUP BY` ground truth; live UI screenshot confirms |
| Input: extremely long strings | **Fixed** | `max_length=255` (schema) + CSS truncation (frontend); re-verified live via real `422` and real screenshot |
| Input: zero/negative payment amount | **Fixed (severe)** | `gt=0` (schema) + `CHECK` (DB); real confirmed data corruption (`250000.00` -> `200000.00`) reproduced, then closed and re-verified at both layers |
| Input: unicode/emoji | No defect | Real mixed-script string stored, read back, and rendered correctly |
| Input: injection-shaped filters/writes | No defect | Parameterization holds on both read and write paths against multiple real payloads |
| Frontend: unhandled render exception | **Fixed** | Real error boundary added; live screenshot before/after; recovery button tested working |
| Precision: fractional paisa | No defect | Exact `numeric(12,2)` arithmetic confirmed end to end, including live UI rendering |
| Precision: UTC vs. browser timestamp | **Fixed (systemic)** | Real 5.5-hour IST display error confirmed and reproduced; `UtcDatetime` fix applied across every response schema; re-verified live with a real host-clock-correlated timestamp |
| Follow-up 1: long-string fix on the Excel-import path | **Fixed (severe gap)** | Original fix never covered import; reproduced live (5,000-char name imported uncontrolled), fixed at parse-time + DB `CHECK`, re-verified at all 3 layers including a raw-SQL bypass test |
| Follow-up 2: payment amount decimal precision/magnitude | **Fixed (2 defects: silent rounding + real 500)** | `100.005` silently became `100.01`; `99999999999.99`/`1e30` both crashed with a real unhandled `500`; fixed with `max_digits=12, decimal_places=2`, re-verified live including the true column-max boundary |
| Follow-up 3: programmatic `UtcDatetime` sweep + 2nd screen | No further defect found | AST-based sweep (self-tested against a broken sample) found zero remaining bare-`datetime` fields; status-history timeline independently confirmed matching a real wall-clock reading |
