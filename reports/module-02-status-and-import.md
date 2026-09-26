# Module 02: Status transitions and Excel import — completion report

## Scope

Fix a naming drift in the `ApplicationStatus` enum introduced unilaterally
in Module 01, then build two new endpoints on top of Module 01's schema:
a status-transition endpoint enforcing an explicit transition table, and
an Excel-import endpoint reconciling uploaded applicant rows against the
existing `applicant` table. Payment-claim submit/confirm is explicitly
deferred to Module 03 — `finance_record` and its trigger already exist
from Module 01 and needed no schema change for this module beyond the
enum fix.

## What was built

### Migration 0006: `ApplicationStatus` enum correction

Module 01 chose `INQUIRY`, `APPLICATION_STARTED`, `DOCUMENTS_SUBMITTED`,
`UNDER_REVIEW`, `OFFER_MADE`, `ADMISSION_TAKEN`, `REJECTED`, `WITHDRAWN`
unilaterally, drifting from the pipeline actually agreed for this project.
Migration `0006_status_enum_rename` recreates the Postgres enum type with
the correct vocabulary — `IMPORTED`, `APPLIED`, `IN_PROCESS`, `ON_HOLD`,
`ADMISSION_OFFERED`, `ADMISSION_TAKEN`, `REJECTED`, `WITHDRAWN` — via the
standard swap-to-text/remap/swap-back pattern (not `ALTER TYPE ... RENAME
VALUE`, since this is a genuine vocabulary change, not a 1:1 rename: five
old values collapse and reorder into five new ones with no clean
correspondence). `applicant.current_status` gets a database-level default
of `'IMPORTED'`. `ENROLLED` was never added — out of scope per the
correction. The `finance_record_requires_admission_taken()` trigger is
recreated in the same migration (its string-literal comparison,
`'ADMISSION_TAKEN'`, did not need to change, but the function is
recreated anyway for auditability — see the migration's own docstring).

The SQLAlchemy `ApplicationStatus` enum (`app/models/enums.py`) and
`Applicant.current_status`'s ORM-level default (`app/models/applicant.py`)
were updated to match.

**Verified live**: `SELECT enumlabel FROM pg_enum WHERE enumtypid =
'application_status'::regtype` against the freshly-migrated database
returned exactly the eight correct values in order, with `IMPORTED`
first; `SELECT 'ENROLLED'::application_status` correctly raised `invalid
input value for enum application_status`; a fresh `applicant` insert with
no `current_status` specified defaulted to `IMPORTED`; the admission-gate
trigger correctly blocked/allowed `finance_record` creation using the new
spelling (`"...current_status is ADMISSION_TAKEN (was IMPORTED)"` in the
rejection message).

### Migration 0007: `finance_record` auto-creation trigger

Module 01 built `finance_record_requires_admission_taken()` as a gate
(blocks a manual insert unless the applicant is already at
`ADMISSION_TAKEN`) but nothing that *creates* the row automatically. This
module's status-transition endpoint needs exactly that — "relies on the
existing database trigger to create the finance_record automatically the
moment status reaches Admission Taken rather than doing that in
application code," per the module prompt — so migration
`0007_finance_record_auto_create` adds
`applicant_create_finance_record()`, firing `AFTER UPDATE OF
current_status ON applicant WHEN (NEW.current_status = 'ADMISSION_TAKEN'
AND OLD.current_status IS DISTINCT FROM NEW.current_status)`.

This migration also had to touch `finance_record`'s RLS policy, and this
is where live verification earned its keep (see Defects section below).

### Migration 0008: `import_batch` counts and checksum

Extends `import_batch` (Module 01's table-only scaffold) with `checksum`
(sha256 of the uploaded file, used for the dedup no-op),
`created_count`/`updated_count`/`flagged_count`/`rejected_count` (a
breakdown "the person who ran it can actually see," per the module
prompt, not only a single total), and `flagged_rows` (JSONB array of the
rows this import flagged for manual review).

### Status-transition endpoint (`app/routers/status.py`)

`POST /applicants/{id}/status` moves an applicant from its current status
to a requested one only if the move is in the explicit table
(`app/services/status_transitions.py`):

    IMPORTED -> APPLIED
    APPLIED -> IN_PROCESS
    IN_PROCESS -> ON_HOLD, ADMISSION_OFFERED
    ON_HOLD -> IN_PROCESS
    ADMISSION_OFFERED -> ADMISSION_TAKEN
    {APPLIED, IN_PROCESS, ON_HOLD, ADMISSION_OFFERED} -> REJECTED, WITHDRAWN

`ADMISSION_TAKEN`, `REJECTED`, `WITHDRAWN` are terminal (no dictionary
entry, so no allowed destinations for any of them). Every transition
writes an `application_status_event` row with the acting user and an
optional note. An invalid transition returns 422 naming both the current
and requested status, never a 500. RBAC: `SUPER_ADMIN`,
`ADMISSIONS_MANAGER`, `ADMISSIONS_COUNSELOR` may call this endpoint at
all; within that set, RLS (module 01's `applicant` policy) does the actual
per-row scoping — a counselor's request against another counselor's
applicant matches zero rows and reports 404, not 403, since the applicant
is RLS-invisible to that actor rather than merely off-limits.

A new dependency, `require_role_session` (`app/core/deps.py`), yields
`(user, db)` together from the *same* RLS-scoped transaction the role
check ran under, so the whole read-check-write-log sequence happens in one
transaction rather than the route reopening a second scoped session.

### Excel-import endpoint (`app/routers/import_.py`)

`POST /import/applicants` accepts an uploaded `.xlsx`. Column mapping
(`app/services/import_config.py`) is a reviewed dict, not hardcoded
literal header strings at each field-access site — a renamed/missing
header raises before any row is processed, surfaced as a 422 naming the
missing column. The uploaded file's sha256 checksum is looked up against
prior `COMPLETED` batches first; a match short-circuits as a no-op
(`deduplicated: true` on the response, zero new rows/writes). Each parsed
row is matched against existing applicants by normalized phone
(`app/services/excel_import.py`'s `normalize_phone`, strips to digits
only) first, then normalized email if no phone match. An unmatched row
creates a new `Applicant` at `IMPORTED`. A matched row updates only
`full_name`/`program`/`intake_cycle`/`email`/`phone` — `current_status` is
never touched. If a matched row's email or phone differs from what is
already stored, the row is recorded in `import_batch.flagged_rows` (with
old/new values and a reason) and counted under `flagged_count` rather than
silently overwritten and called `updated_count`. RBAC: `SUPER_ADMIN` and
`ADMISSIONS_MANAGER` only.

## Verification against the live stack

All verification below is real HTTP calls (`curl`) against the running
`api` container on `127.0.0.1:38210`, real `.xlsx` files built with
`openpyxl`, and direct `psql` checks connected as the ordinary
`sirius` role (never superuser) — not code review alone, per this
project's own bug-class discipline (see Module 01's report for the two
defects that discipline already caught once).

### Status-transition endpoint

- `IMPORTED -> APPLIED` (200), `APPLIED -> ADMISSION_TAKEN` skipping states
  (422, `"invalid status transition: APPLIED -> ADMISSION_TAKEN"`),
  `APPLIED -> IN_PROCESS` (200), `IN_PROCESS -> ON_HOLD` (200),
  `ON_HOLD -> IN_PROCESS` (200, confirming the bidirectional pair),
  `IN_PROCESS -> ADMISSION_OFFERED` (200), `ADMISSION_OFFERED ->
  ADMISSION_TAKEN` (200) — the full happy path, walked one HTTP call at a
  time.
- `ADMISSION_TAKEN -> REJECTED` rejected (422) — confirmed
  `ADMISSION_TAKEN` is terminal.
- A separate applicant `APPLIED -> REJECTED` (200), then `REJECTED ->
  IN_PROCESS` rejected (422) — confirmed `REJECTED` is terminal.
- `application_status_event` rows for all of the above, queried directly,
  showed the correct `from_status`/`to_status`/`changed_by`/`note` for
  every transition, including the manager's and a counselor's own
  transitions correctly attributed to each actor's own user id.
- `finance_record` auto-creation confirmed through the **full HTTP path**
  (not a direct SQL trigger test): after the manager's `ADMISSION_OFFERED
  -> ADMISSION_TAKEN` call returned 200, a direct `psql` check (connected
  as superuser, to bypass this role's own lack of `finance_record` SELECT
  access) showed a `finance_record` row for that applicant with
  `total_fee_due = 0`.
- RBAC: `ADMISSIONS_MANAGER` reached the endpoint (200); `FINANCE_STAFF`
  (fully TOTP-verified) was rejected (403, `"insufficient role for this
  action"`); a counselor attempting another counselor's applicant got 404
  (`"applicant not found"`) — RLS-invisible, not merely forbidden; the
  actual assigned counselor succeeded (200) against their own applicant.

### Excel-import endpoint

- A fresh 2-row `.xlsx` (both new applicants) returned `created_count: 2,
  updated_count: 0, flagged_count: 0, rejected_count: 0`; both rows
  confirmed present in `applicant` at `IMPORTED` status, linked to the
  new `import_batch` row.
- Re-uploading the **identical file** returned `deduplicated: true`, the
  same `import_batch.id` as the first upload, and the applicant count
  confirmed unchanged (still exactly 2, no duplicates created).
- A second file matching one existing applicant by phone with an
  unchanged email (name/program changed) returned `updated_count: 1`; a
  `psql` check confirmed the name/program updated and `current_status`
  untouched.
- The same file's second row matched an existing applicant by phone but
  with a **changed email** returned `flagged_count: 1` with a
  `flagged_rows` entry naming the applicant id and old/new email — `psql`
  confirmed the applicant's email *was* updated (the endpoint still
  applies the new contact detail) but the row was correctly counted as
  flagged, not updated, and `current_status` was untouched.
- An applicant advanced to `APPLIED` via the status endpoint, then
  matched again by a subsequent import with a further name/program
  change: `psql` confirmed `current_status` remained `APPLIED` — a
  re-import genuinely never resets or advances the pipeline position,
  verified against a real prior status transition, not only against a
  freshly-created `IMPORTED` row.
- A row matched by **email fallback** (phone changed, email unchanged)
  correctly matched the existing applicant rather than creating a
  duplicate — confirmed `created_count: 0`, and the row was flagged
  (phone changed) rather than silently overwritten.
- A file with a renamed header (`Full Name` -> `Applicant Name`) was
  rejected (422, `"import rejected: missing expected column(s): Full
  Name"`) before any row was processed — confirmed no `applicant` row for
  that file's data was created.
- A file with two malformed rows (one missing both `full_name`/`email`,
  one missing only `email`) alongside one good row returned
  `created_count: 1, rejected_count: 2`, with `error_detail` naming each
  rejected row number and which field(s) were missing — one bad row did
  not abort the otherwise-good import.
- A non-`.xlsx` upload was rejected (422, `"only .xlsx files are
  accepted"`).
- RBAC: `ADMISSIONS_COUNSELOR` was rejected (403) for this endpoint,
  confirming it is `SUPER_ADMIN`/`ADMISSIONS_MANAGER`-only as scoped.
- `audit_log` correctly captured every `import_batch`/`applicant`
  INSERT/UPDATE this endpoint performed, attributed to the manager's own
  `actor_id`. A counselor's session correctly saw zero `import_batch` rows
  via RLS (ADR-03 scopes that table to
  `SUPER_ADMIN`/`ADMISSIONS_MANAGER`/`AUDITOR`).

## Real defects found and fixed during this verification

**Defect 1 — `INSERT ... ON CONFLICT DO NOTHING` under `FORCE ROW LEVEL
SECURITY` implicitly requires SELECT policy access, which
`ADMISSIONS_COUNSELOR` (and every other non-finance role) does not have on
`finance_record`.** The first draft of migration 0007's auto-create
trigger used `INSERT INTO finance_record (...) VALUES (...) ON CONFLICT
(applicant_id) DO NOTHING` for idempotency. This is documented Postgres
behavior (`CREATE POLICY` reference: "If an INSERT has ... an ON CONFLICT
DO NOTHING clause with an arbiter index or constraint specification, then
SELECT permissions are required on the relation, and the rows proposed
for insertion are checked using the relation's SELECT policies") but was
not anticipated — the RLS policy split (`finance_record_insert`, `WITH
CHECK (true)`) looked sufficient on inspection and was *not* sufficient
in practice. Live verification caught this directly: a counselor
transitioning their own assigned applicant to `ADMISSION_TAKEN` failed
with `new row violates row-level security policy for table
"finance_record"`, reproduced cleanly multiple times with fresh test data
after ruling out several false leads (stale test state, wrong
`actor_id`) before isolating the actual cause to the `ON CONFLICT` clause
itself — confirmed by testing the identical statement with and without
that clause against the live database. Fixed by replacing `ON CONFLICT DO
NOTHING` with a plain `INSERT` wrapped in a nested `BEGIN ... EXCEPTION
WHEN unique_violation THEN NULL` block, which gives the same idempotency
guarantee without triggering the SELECT-policy requirement. Re-verified
end-to-end (counselor login -> HTTP status transition -> `finance_record`
row confirmed present) after the fix.

**Defect 2 — naive/aware `datetime` mismatch crashed the import endpoint
with a 500 on every single call.** `import_.py` used `datetime.now(UTC)`
(timezone-aware) for `import_batch.completed_at`, but that column is
`TIMESTAMP WITHOUT TIME ZONE` (naive) — SQLAlchemy/asyncpg raised
`DataError: can't subtract offset-naive and offset-aware datetimes` on
every write, meaning the endpoint had never actually completed a single
import before this was caught. Fixed by storing
`datetime.now(timezone.utc).replace(tzinfo=None)` instead. Found on the
very first real upload attempt, not by code review — the code looked
correct on inspection (`datetime.now(UTC)` is the normally-correct
pattern) and only failed once run against the real column type.

**Defect 3 — an `import_batch` row for a rejected upload (missing
header) was silently never persisted.** The first draft committed the
`FAILED` status/`error_detail` with `await db.flush()` before raising
`HTTPException`. `get_scoped_session` (module 01's own dependency) wraps
the entire request in one `session.begin()` block, which rolls back the
whole transaction — including the flushed-but-not-committed `FAILED`
batch row — the instant the exception propagates out of the route. The
endpoint returned the correct 422 to the caller, but a direct `psql`
check afterward showed **no `import_batch` row at all** for that
rejected file — silently violating "writes one ImportBatch row per
import" for the one case (a rejected upload) where an audit trail of the
rejection matters most. Fixed by calling `await db.commit()` before
raising in that one path. Re-verified: a fresh rejected upload now shows
a real `FAILED` row with the exact `error_detail` message.

## Deferred to Module 03 (per scope)

Payment-claim submit/confirm endpoints. `finance_record` and its
admission-gate/auto-create triggers already exist from this and the prior
module and needed no further schema change here.

## Follow-up verification

Three open items from the review of the work above, closed before starting
Module 03. All verification here is against the same live stack this
module's own report already establishes, not a re-read of code or SQL.

### 1. Migration 0006's old-to-new status remap: semantic, not positional

Checked whether `OLD_TO_NEW` in `0006_status_enum_rename.py` was a
reviewed correspondence or an accidental positional/ordinal mapping (e.g.
old value N silently mapped to new value N regardless of meaning). It is
genuinely semantic: `DOCUMENTS_SUBMITTED` and `UNDER_REVIEW` -- two
different old values, at different ordinal positions -- both map to the
single new value `IN_PROCESS`, which a positional mapping could not
produce (a positional scheme is 1:1 by construction; this one is
deliberately many-to-one where the old vocabulary was finer-grained than
the new one warrants). The migration's own docstring already carried an
explicit `OLD_VALUE -> NEW_VALUE` table before this review, stating the
mapping decision in prose for each of the eight old values, including the
rationale for the two-old-values-into-one-new-value case
(`UNDER_REVIEW`'s only reasonable new-vocabulary home is `IN_PROCESS`,
the same bucket `DOCUMENTS_SUBMITTED` lands in). No code change was
needed here -- the existing docstring already meets the bar this item was
checking for. The rows this remap actually touched were disposable
dev-verification data (this module's own report already states the table
was empty when the migration was first run), but the pattern -- an
explicit, reviewed `OLD_TO_NEW` dict driving a `CASE`-expression `UPDATE`,
not a bare ordinal reindex -- is the one to keep using for any future
enum vocabulary change that does have to remap real applicant rows.

### 2. Defect 1's fix did not loosen `finance_record`'s SELECT policy

Verified live, through the real application code path, not by re-reading
`0007_finance_record_auto_create.py`'s policy SQL:

1. Seeded a fresh `ADMISSIONS_COUNSELOR` user and an applicant assigned to
   them, already at `ADMISSION_OFFERED`.
2. Logged in as that counselor over real HTTP (`POST /auth/login`).
3. Called the real `POST /applicants/{id}/status` endpoint as that
   counselor to transition their own applicant to `ADMISSION_TAKEN` (200
   OK) -- this is the exact call that fires the
   `applicant_create_finance_record()` trigger and, per Defect 1, needed
   the `finance_record_insert` policy fix to succeed at all.
4. Immediately afterward, in a **fresh `open_scoped_session` call carrying
   that same counselor's real `actor_id`/`actor_role`** -- the identical
   mechanism `app.core.deps.get_scoped_session` uses for every real
   request -- queried `finance_record` for that applicant.

Result: `0` rows visible. A parallel superuser connection confirmed the
row genuinely exists (`total_fee_due = 0.00`), and a `FINANCE_MANAGER`-
scoped session correctly saw it. This confirms the split introduced by
Defect 1's fix (`finance_record_select` restricted to `SUPER_ADMIN`/
`FINANCE_STAFF`/`FINANCE_MANAGER`/`AUDITOR`, `finance_record_insert` with
`WITH CHECK (true)`) did exactly what it was supposed to and nothing
more: the counselor's *write* (via the trigger) is permitted, their
*read* remains correctly denied, including of the very row their own
action just created. Migration `0007`'s docstring was strengthened with
an explicit paragraph stating this (mirroring the equivalent statement
Module 01 made for `audit_log`) and recording this verification.

### 3. `get_scoped_session`'s transaction-scoped GUCs, and a corrected finding

Added a note to `open_scoped_session` (`app/core/db.py`) and its wrapper
`get_scoped_session` (`app/core/deps.py`) flagging that the `SET LOCAL`
GUCs they set belong to the one transaction `session.begin()` opens, so a
mid-request `db.commit()` -- the exact shape Defect 3's fix introduced,
committing a `FAILED` `import_batch` row before raising a 422 -- ends
that transaction.

**The first draft of this note, written before checking, was wrong about
the actual failure mode**, and was corrected after live reproduction:

- **Initial (incorrect) assumption**: a mid-request commit would silently
  drop back to unscoped behavior, so any further database work in the
  same request would quietly see zero rows (RLS fail-closed) rather than
  erroring -- "easy to misread as no matching rows."
- **What was actually reproduced**, using the identical
  `async_session_factory() as session, session.begin()` shape
  `open_scoped_session` uses: calling `session.commit()` mid-transaction
  and then calling `session.execute(...)` again on that same session
  raises `sqlalchemy.exc.InvalidRequestError: Can't operate on closed
  transaction inside context manager` **immediately, every time** -- not
  a silent fallback, a hard error. Calling `commit()` and then *not*
  touching the session again before the request ends (Defect 3's own
  fix's actual shape, where `db.commit()` is immediately followed by
  `raise HTTPException`) is safe: the exception propagates into the
  generator dependency at its `yield` point, `session.begin()`'s own
  `__aexit__` attempts a rollback against the already-committed
  transaction, and SQLAlchemy accepts that as a no-op. Re-ran the real
  live `POST /import/applicants` rejected-header case one more time after
  this check to confirm the actual endpoint still behaves correctly (422
  returned, `FAILED` `import_batch` row correctly persisted) -- it does.

Both docstrings (`open_scoped_session` and `get_scoped_session`) were
rewritten with the corrected, empirically-verified behavior: a mid-request
commit followed by immediately raising is safe; a mid-request commit
followed by *any further use of that session* is a hard `InvalidRequestError`,
not a silent scope loss. This is materially relevant to Module 03: a
payment-claim confirm endpoint that needs to persist a confirmation and
then perform further RLS-scoped work in the same request cannot reuse the
session past a mid-request commit -- it must open a fresh
`open_scoped_session` for that further work, or it will crash with a 500,
not silently return wrong data.

