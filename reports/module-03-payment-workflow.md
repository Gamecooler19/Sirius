# Module 03: Payment workflow — completion report

## Scope

Build the payment-claim submit/confirm/reject workflow on top of
`finance_record` (existing since Module 01/02) and `payment_claim`
(existing table, but missing `payment_mode`/`reference_number` and an
`UPDATE` RLS policy until this module). Three endpoints:
`POST /finance/payment-claims` (submit), `POST
/finance/payment-claims/{id}/confirm`, `POST
/finance/payment-claims/{id}/reject` — maker-checker enforced (submitter
cannot resolve their own claim), `total_paid` rollup owned entirely by a
database trigger fired on confirm, never application code.

## What was built

### Migration 0009: `payment_claim_workflow`

- New native enum `payment_mode`: `CASH`, `CHEQUE`, `BANK_TRANSFER`,
  `UPI`, `CARD`, `OTHER`.
- `payment_claim.payment_mode` (not null, no default — every claim must
  state how it was paid) and `payment_claim.reference_number` (nullable
  varchar — cash payments legitimately have none).
- `finance_record_update` RLS policy. Migration 0007 (Module 02) added
  `finance_record_select`/`finance_record_insert` but never an `UPDATE`
  policy — under `FORCE ROW LEVEL SECURITY` this silently blocks *any*
  `UPDATE`, including one issued by a role that should be allowed, since
  Postgres has nothing to check the row against. Reuses the exact
  allowlist migration 0007's `SELECT` policy already established
  (`SUPER_ADMIN`, `FINANCE_STAFF`, `FINANCE_MANAGER`, `AUDITOR`) rather
  than introducing a new GUC or role set — deliberately **not**
  unconditional like migration 0007's `INSERT` policy, since (unlike the
  auto-create trigger, which needed `WITH CHECK (true)` because it fires
  under whichever role happened to trigger the status transition) the
  confirm/reject endpoint that performs this `UPDATE` is already
  RBAC-restricted at the application layer to `FINANCE_MANAGER`/
  `SUPER_ADMIN`, both already inside that allowlist — no role gap to
  paper over with an unconditional policy.
- `payment_claim_increment_finance_record_total_paid()`, fired `AFTER
  UPDATE OF status ON payment_claim WHEN (NEW.status = 'CONFIRMED' AND
  OLD.status IS DISTINCT FROM NEW.status)`. Adds `NEW.amount` to the
  parent `finance_record.total_paid`. Fires exactly once per
  confirmation (the `IS DISTINCT FROM` guard prevents a no-op `UPDATE`
  that re-sets `status = 'CONFIRMED'` — not reachable through this
  module's own endpoints, which check `status != PENDING` before writing,
  but guarded at the trigger level anyway since nothing stops a future
  caller from writing to this table directly).

`app/models/enums.py` (`PaymentMode`) and `app/models/payment_claim.py`
(`payment_mode`, `reference_number` columns) updated to match.

**Migration run live** against a fully fresh stack (`docker compose down
-v` then up) — all 9 migrations applied clean from zero. `\d+
finance_record` and `\d+ payment_claim` confirmed the new columns, the
`finance_record_update` policy with the correct allowlist, and both
triggers (`payment_claim_confirmed_increments_total_paid`, correctly
scoped to the `status` column and the `CONFIRMED`-only `WHEN` clause) all
present exactly as migrated.

### Payment-claim endpoints (`app/routers/payment_claim.py`)

**`POST /finance/payment-claims`** (submit). `SUPER_ADMIN`,
`FINANCE_STAFF`, `FINANCE_MANAGER` may call. `submitted_by` is taken from
the authenticated session's own user id — never from the request body
(`app/schemas/payment_claim.py`'s `PaymentClaimSubmitRequest` has no such
field at all, so there is no client-supplied value to even accidentally
trust). A `finance_record_id` that does not exist, or exists but is
RLS-invisible to the caller, is reported 404 — matching this project's
established RLS-invisible-is-404 convention from Module 02's status
endpoint.

**`POST /finance/payment-claims/{id}/confirm`** and **`/reject`**.
`FINANCE_MANAGER`/`SUPER_ADMIN` only — `FINANCE_STAFF` is rejected 403
before ever reaching the claim, matching the intent that staff may
originate a claim but never resolve any claim, including one submitted
by a different staff member. Within that role gate, the maker-checker
conflict (`claim.submitted_by == user.id`) is checked at the application
layer and rejected 422, naming the conflict explicitly — **before**
the database's own `ck_payment_claim_distinct_submitter_confirmer` CHECK
constraint would otherwise surface the same rejection as an unhandled
`IntegrityError` (a 500). The CHECK constraint itself is left in place
unchanged as the database-level backstop, per this project's established
defense-in-depth pattern (ADR-07) — the endpoint's check is the first
line, not the only one. A claim not currently `PENDING` (already
resolved, either way) is rejected 422 naming its current status, whether
called via `/confirm` or `/reject`.

Confirming (`status -> CONFIRMED`) is the endpoint's only database write
beyond the `status`/`confirmed_by`/`confirmed_at` update itself — the
`finance_record.total_paid` rollup happens entirely inside migration
0009's trigger on the same `UPDATE`, without `app/routers/payment_claim.py`
importing or writing to `FinanceRecord` at all. `confirmed_at` uses
`func.now()` as an ORM attribute assignment, the same pattern already
live-verified for `UserBackupCode.used_at` in Module 01's
`totp_verify_backup_code`.

**Single request-scoped transaction, no mid-request commit**, in either
endpoint's normal path. `require_role_session` yields `(user, db)` from
one RLS-scoped transaction; neither endpoint calls `db.commit()` before
returning. Unlike Module 02's Defect 3 (which had a real reason to
persist a `FAILED` batch row ahead of raising), no state here is worth
persisting ahead of a 4xx response — a rejected submit or a rejected
confirm/reject has written nothing yet.

## Verification against the live stack

All verification below is real HTTP calls (`curl`) against the running
`api` container on `127.0.0.1:38210`, with real session cookies obtained
through the actual login + mandatory-TOTP-enrollment flow (not a bypass),
and direct `psql` checks against the live database — not code review
alone.

Test identities created for this module: `FINANCE_STAFF`, two
`FINANCE_MANAGER` accounts (a second manager was needed specifically to
exercise a *legitimate* cross-user confirm/reject once the first
manager's own claim needed resolving by someone else), one
`ADMISSIONS_COUNSELOR`. An applicant was walked from `IMPORTED` to
`ADMISSION_TAKEN` via a genuine `UPDATE`, not a same-row `INSERT`,
since the auto-create trigger only fires `AFTER UPDATE OF current_status`
— confirmed by re-reading `\d+ applicant` before seeding, avoiding a
wasted seed attempt) to get a real, trigger-created `finance_record` with
`total_fee_due` set to a nonzero value for a meaningful rollup check.

- **Submit.** `FINANCE_STAFF` submitted a `BANK_TRANSFER` claim for
  100000.00 against the seeded `finance_record` — 200, `status: PENDING`,
  `submitted_by` correctly the staff user's own id (never client-supplied
  — the request body has no such field).
- **Role gate on confirm/reject.** `FINANCE_STAFF` attempting `/confirm`
  on their own just-submitted claim — 403, `"insufficient role for this
  action"` — confirming this is a role rejection, not (yet) a
  maker-checker rejection; staff never reaches the maker-checker check at
  all. Separately, `FINANCE_STAFF` attempting `/reject` on a different
  manager's claim also 403, for the same reason.
- **Genuine same-user maker-checker 422.** `FINANCE_MANAGER` #1 submitted
  their own claim (50000.00, UPI), then called `/confirm` on it
  themselves — 422, `"cannot confirm or reject a payment claim you
  submitted yourself (maker-checker separation)"`. This is the real
  maker-checker path (role check passed; the same-user check is what
  actually fired), not the role-gate 403 above.
- **Legitimate cross-manager confirm.** `FINANCE_MANAGER` #1 confirmed
  `FINANCE_STAFF`'s 100000.00 claim — 200, `status: CONFIRMED`,
  `confirmed_by` correctly manager #1's id, `confirmed_at` populated.
- **`total_paid` rollup via trigger, confirmed by direct `psql`** (not
  inferred from the HTTP response): before any confirm,
  `finance_record.total_paid = 0.00`; after the above confirm,
  `total_paid = 100000.00`, exactly matching the confirmed claim's
  amount, with no application code in `payment_claim.py` touching
  `finance_record` at all.
- **Legitimate cross-manager reject.** `FINANCE_MANAGER` #2 rejected
  `FINANCE_MANAGER` #1's own PENDING 50000.00 claim — 200, `status:
  REJECTED`, `confirmed_by` correctly manager #2's id. `psql` confirmed
  `total_paid` was **unaffected** (still 100000.00) — the rollup trigger's
  `WHEN (NEW.status = 'CONFIRMED')` guard correctly excludes rejections.
- **Double-resolve rejected.** Manager #2 attempting `/confirm` on the
  already-`CONFIRMED` claim from above — 422, `"payment claim is not
  PENDING (current status: CONFIRMED)"`, not a 500 and not a silent
  second increment.
- **404s.** Submit against a nonexistent `finance_record_id` (all-zero
  UUID) — 404, `"finance record not found"`. Confirm against a
  nonexistent claim id — 404, `"payment claim not found"`.
- **RLS-blindness (counselor).** `ADMISSIONS_COUNSELOR` attempting to
  submit a claim — 403 (role gate; `ADMISSIONS_COUNSELOR` was never in
  the submit allowlist to begin with, so this exercises the role
  dependency, not RLS row-visibility directly — `finance_record`'s own
  `SELECT` policy already excludes this role per Module 02's follow-up
  verification of the same allowlist).
- **Audit trail.** `audit_log` (queried as `postgres` superuser, bypassing
  RLS for direct inspection) showed exactly four `payment_claim` rows —
  two `INSERT` (the two submits) and two `UPDATE` (the confirm and the
  reject) — each `actor_id` correctly attributed to the acting user, not
  the claim's original submitter. `finance_record`'s own audit rows
  showed the `total_paid` transition from `0.00` to `100000.00` on the
  `UPDATE` row corresponding to the confirm, and a separate no-op
  `total_fee_due`-only `UPDATE` row from the manual seed step, confirming
  the write-audit trigger captures every `finance_record` mutation
  regardless of source.

## Real defects found and fixed during this module

**Proactive catch — `finance_record` had no `UPDATE` RLS policy at all.**
Found during a precheck run *before* writing any endpoint code: `\d+
finance_record` against the live stack showed only
`finance_record_select`/`finance_record_insert` from migration 0007.
Under `FORCE ROW LEVEL SECURITY`, an `UPDATE` with no matching policy is
silently blocked for every role, including the finance roles this
module's confirm endpoint needs to update `total_paid` through. Since
this was caught by re-checking the live schema before writing the
`total_paid` rollup trigger, rather than discovered by a 500 during
verification afterward, it does not count as one of this module's
"defects found during verification" in the sense Modules 01/02 used that
phrase — no broken code was ever run against the live stack — but it is
recorded here because it was a real, load-bearing schema gap the live
stack itself surfaced, consistent with this project's standing rule to
verify against the live stack rather than assume a migration is complete
from reading it. Fixed as part of migration 0009 (`finance_record_update`
policy) rather than as a follow-up migration, since no endpoint code
depending on the missing policy had shipped yet.

No other defects were found during live HTTP verification of the
submit/confirm/reject endpoints themselves — the maker-checker 422 path,
the role-gate 403 path, the 404 paths, and the trigger-owned rollup all
worked as designed on first live test.

## Cleanup

All ad hoc seed SQL files and curl cookie jars used for this module's
live verification (`m3_seed.sql`, `m3_seed2.sql`,
`m3_*_cookies.txt`) were deleted after verification completed; none were
staged or committed. The seeded test users/applicant/finance_record/
payment_claim rows themselves remain in the running dev stack's database
(as with prior modules — this is disposable Docker Compose dev data, not
committed to git).

## Definition of done

- [x] Migration 0009 written, applied to a live fresh stack, and its
      schema output (`\d+`) verified column-by-column and policy-by-policy.
- [x] Three endpoints built: submit, confirm, reject.
- [x] Maker-checker enforced at the application layer with a 422, ahead
      of the database's own CHECK constraint.
- [x] `total_paid` rollup owned entirely by a database trigger, verified
      live via direct `psql`, not inferred from the HTTP response alone.
- [x] RBAC verified live for all three endpoints across
      `FINANCE_STAFF`/`FINANCE_MANAGER`/`ADMISSIONS_COUNSELOR`.
- [x] No mid-request commits introduced.
- [x] `submitted_by` sourced from session identity only, verified by the
      schema's own field omission, not merely by convention.
- [x] Audit trail verified live for both `payment_claim` and
      `finance_record`.
- [x] Report committed as `reports/module-03-payment-workflow.md`.
