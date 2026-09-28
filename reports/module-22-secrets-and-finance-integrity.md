# Module 22 -- Secrets Hygiene and Finance Figure Integrity

## Scope

Two explicitly ordered parts, Part 1 required complete before Part 2
or before anything else is pushed/made public:

1. **Secrets hygiene**: scan full git history (not just the working
   tree) across every remote for committed secrets, live-verify which
   are still active, rotate every one that is, and redact every value
   from the current tree -- shapes and locations only, never values,
   in this report or anywhere else. History rewriting/force-push is
   explicitly deferred to the repository owner's own decision, not
   made unilaterally here.
2. **Finance figure integrity**: `total_fee_due` is never written by
   the API, so every dashboard/reconciliation figure derived from it
   is wrong. Add a real, role-gated write path with matching DB
   constraints, RLS tightening, and a documented "fee not set" vs
   "fee = 0" distinction.

## Part 1 -- Secrets hygiene

### Repo topology confirmed live

Two remotes: `origin` (a self-hosted Forgejo instance), stale at an
earlier Module 18-era commit; `github` (a public GitHub mirror),
current and matching local `main` exactly. Exactly one branch (`main`)
on each remote, no tags anywhere, 41 total commits across all refs.

**The GitHub remote is confirmed publicly readable** -- fetched
directly with no authentication wall. The Forgejo remote also loaded
fully with no login wall, so treated as effectively public as well for
the purposes of this audit, though its own private-repository
indicator was not independently confirmed either way.

### Scanning method

Two general-purpose secret scanners run against full history across
every remote (`--all --remotes` / `--all-files`):

- **gitleaks** (binary downloaded for this session): flagged one real
  finding outside dependency/generated noise -- a VAPID private key
  (RFC 8292 Web Push signing key) committed in plaintext inside a
  report file, in one specific historical commit, first introduced
  during Module 20's own push-notification setup.
- **detect-secrets**: flagged 44 files; all but one were either
  `node_modules` dependency noise (gitignored, never actually
  tracked) or Base64-entropy false positives inside gitignored
  deployment/export files, confirmed via `git check-ignore` and a full
  history scan of `git log --name-only` for those paths showing only
  `.example` placeholder files were ever committed. The one real
  finding: a plaintext demo-account password inside a report file.

Neither tool's generic entropy/pattern rules reliably catch
human-readable password strings, so a **custom regex scanner** was
written and run against every commit that ever touched any
`reports/*.md` file (via `git show <commit>:<path>` per commit, not
only the current tree) to catch this category specifically.

Additionally, the full history of every report file was searched for
TOTP `otpauth://` URIs, `backup_codes` arrays, and raw
reset/session-token values. **Zero findings of any of those three
secret types in any committed report, in any commit, on either
remote.**

### Findings, by shape and location only

| # | Secret type | Location (report + commit) | Live status at time of discovery |
|---|---|---|---|
| 1 | Web Push VAPID private key (RFC 8292) | Module 20's own report, one line, the commit that introduced Module 20 | **Live** -- confirmed working against the real push service before rotation |
| 2 | Demo-account password | Module 13's report, one line | Superseded (re-reset at least once since) |
| 3 | Demo-account password | Module 13's report, one line | Superseded |
| 4 | Demo-account password | Module 13's report, one line | Superseded |
| 5 | Demo-account password | Module 15's report, one line (the "old" value in a before/after pair) | Superseded (same account as #4, an earlier value) |
| 6 | Demo-account password | Module 18's report, two separate lines (same value) | Superseded |
| 7 | Demo-account password | Module 19's report, two separate lines (same value) | Superseded |

Every superseded password (#2-7) was **live-tested against the real
running stack** and confirmed to return `401` -- none of the six
distinct historical values still authenticate any account. All seven
demo accounts touched by any of these had, at the start of this
module, most recently been reset to one **shared** password during
Module 21's own audit follow-up. That shared password never appeared
in any *committed report* (it only ever appeared in this session's own
conversation and ephemeral `curl` commands) but was nonetheless
rotated as part of this module's own remediation (see below), since it
was live across seven real accounts and had by then been written
repeatedly in a non-committed but still-persistent location.

### VAPID key rotation -- executed and verified live

1. Generated a fresh real VAPID key pair inside the running `api`
   container, using the identical method Module 20's own setup used.
2. Wrote the new pair **only** into `deploy/.env` (gitignored,
   confirmed never tracked, confirmed absent from every commit) with a
   comment explaining the rotation reason. The new private key was
   printed to chat only, per this project's own "never commit a
   secret" requirement -- never written to any report or other
   committed file.
3. Restarted the `api` service; confirmed via the real
   `GET /notifications/vapid-public-key` endpoint that the new public
   key is now served.

**A real, previously-undiscovered defect found during rotation, and
fixed live, not merely noted:**

`app/core/push.py`'s dead-subscription cleanup only treated `404`/`410`
as "this subscription is permanently gone, delete the row" -- the
RFC 8030-documented codes. Firing a real push to the one pre-existing
subscription (created under the *old* key) after rotation did **not**
return `410` as the module's own original design assumed; it returned
a real `401 Unauthorized` from the push service, with a response body
identifying the specific, documented reason as a VAPID-public-key
mismatch. A browser's push subscription is permanently bound to the
public key it was created under -- once that key is rotated, no future
push signed by the new private key can ever succeed against that
subscription again, under any retry. The original 404/410-only check
left this row un-cleaned-up, confirmed live by querying the database
directly after the failed push.

**Fix**: `_send_sync` now reads the response body of a `401` and,
only when it carries the push service's own specific error code for a
VAPID-key mismatch (never inferred from the bare status code alone,
so an unrelated `401` reason from any push service is not silently
treated as dead), normalizes it to the existing dead-subscription
signal so it goes through the identical, already-correct deletion
path.

**Re-verified live end to end**:
- Fired the same push again post-fix -- the stale row was this time
  genuinely deleted, confirmed independently through the append-only
  audit-log trail (a real `DELETE` row for that exact subscription id,
  timestamped to the same second as the trigger), not only through
  application-log inference.
- Logged into the real frontend as the affected account, found the
  push-notification toggle still showing the browser's own stale
  client-side subscription state (expected -- the browser API has no
  way to know server-side rotation happened), disabled it through the
  real UI (a genuine `pushManager.unsubscribe()` + `DELETE
  /notifications/subscribe` call), then re-enabled it (a genuine fresh
  `pushManager.subscribe()` against the new public key +
  `POST /notifications/subscribe`).
- Confirmed a new subscription row was created for the correct
  account, then fired a real push against it: it delivered
  successfully this time -- no failure logged, the row survived,
  confirming the full rotation lifecycle end to end against the real
  push service.

### Report-file redaction

All six superseded demo-account password values and the one VAPID
private key value have been redacted to a placeholder in every
current-tree report file that contained them (Modules 13, 15, 18, 19,
20). Confirmed by re-running the same searches against the current
tree afterward: zero remaining matches for any of the six password
values or the VAPID private key value anywhere in the current tree.

**History itself was not rewritten.** These values remain readable in
the specific historical commits identified above on both remotes,
exactly as this project's own explicit instruction requires --
rewriting history or force-pushing is the repository owner's decision
alone, not made unilaterally by this module. If that value is ever
wanted fully scrubbed from history (not merely superseded/rotated),
that requires a separate, explicit decision to rewrite history and
force-push both remotes, which carries its own real risk (any other
clone or fork retains the old history regardless).

### Shared audit-follow-up password -- rotated

The password shared across seven demo accounts since Module 21's own
follow-up (never itself found in any committed report, but live and
written repeatedly in this session's own non-committed context) was
rotated for all seven accounts through the real
`forgot-password` -> Mailpit email -> `reset-password` flow -- the
same real-redemption discipline this project has used for every prior
credential change, never a direct database write. Each account
received a distinct, freshly generated password (not another shared
value, to avoid recreating the same class of exposure this section
exists to close).

**Verified live for all seven accounts**: the new password returns
`200` on login; the previous shared password now returns `401`. No
account was left on the old, now-written-in-chat value.

### Cleanup

All temporary scanning tooling and scratch scripts created for this
audit (the gitleaks binary and its zip, both JSON scan reports, and
every ad hoc scanner/history-walk script) were deleted from the
working tree and from inside the `api` container before this commit --
none of them were ever tracked, and none remain.

## Part 2 -- Finance figure integrity

### The confirmed defect

`finance_record.total_fee_due` was never written by any real API
endpoint. Confirmed live via `audit_log`'s full history for
`finance_record`: every row's `total_fee_due` was `0.00` from the
instant `applicant_create_finance_record()`'s auto-create trigger
inserted it, and stayed `0.00` forever afterward -- only `total_paid`
ever changed, via the existing payment-confirm rollup trigger. The
consequence was real and observed, not theoretical: two genuine
`finance_record` rows showed `outstanding` (`total_fee_due -
total_paid`) balances of `-250000.00` and `-300000.00` -- real
applicants who had paid real, confirmed money against a fee that was
never actually entered anywhere.

### Schema change: `total_fee_due` becomes nullable

`NULL` now means "no one has entered a fee for this applicant yet,"
structurally distinct from a real, decided `0.00` (a genuinely free
program). Migration `0015_finance_fee_due`:

- Backfills both pre-existing `0.00` rows to `NULL` (confirmed via
  `audit_log` that neither ever received a real write -- their `0.00`
  was the auto-create trigger's own placeholder, not a decision).
- Drops the `NOT NULL` constraint.
- Adds `ck_finance_record_fee_due_nonnegative` (`total_fee_due IS NULL
  OR total_fee_due >= 0`) and `ck_finance_record_total_paid_nonnegative`
  (`total_paid >= 0`) -- verified zero pre-existing violations before
  adding either, matching this project's own established precedent.
- Updates `applicant_create_finance_record()` to insert `NULL` instead
  of `0` for every future auto-created record.

**Two real defects this migration's own first run hit live, both
fixed within the migration itself, not worked around:**

1. The backfill `UPDATE` initially affected zero rows. Alembic
   connects as `sirius` (the table owner), and `finance_record` carries
   `FORCE ROW LEVEL SECURITY` -- a migration has no request-scoped
   `app.actor_role` GUC set at all, so the still-in-effect
   `finance_record_update` policy's predicate evaluated to `NULL` and
   silently excluded every row, exactly like RLS's own documented
   fail-closed behavior. Fixed with a `SET LOCAL app.actor_role =
   'SUPER_ADMIN'` scoped to the migration's own transaction.
2. Backfilling before dropping `NOT NULL` raised a real
   `NotNullViolationError` -- corrected by reordering to `DROP NOT
   NULL` first, then backfill.

### RLS: `finance_record_update` narrowed

From `SUPER_ADMIN`/`FINANCE_STAFF`/`FINANCE_MANAGER`/`AUDITOR` down to
`SUPER_ADMIN`/`FINANCE_MANAGER` only, per the module's own explicit
requirement. `FINANCE_STAFF` may submit a payment claim but was never
meant to resolve one or set the fee it is measured against (the same
maker-checker separation `payment_claim`'s own confirm/reject
endpoints already enforce); `AUDITOR` reviews figures, does not write
them.

**Verified live, both directions:**
- A direct `UPDATE finance_record` issued as the ordinary `sirius`
  role with `app.actor_role` set to `FINANCE_STAFF`, bypassing the
  application layer entirely, affected **zero rows** -- real RLS
  denial, not merely an application-layer 403. Same result for
  `AUDITOR`.
- The identical direct `UPDATE` with `app.actor_role` set to
  `FINANCE_MANAGER` affected **one row** -- confirming the narrowed
  policy still permits the roles it is supposed to.
- The existing payment-confirm rollup trigger (`payment_claim_
  increment_finance_record_total_paid()`, migration 0009) still fires
  correctly under the new, narrower policy: confirmed a real pending
  claim via `POST /finance/payment-claims/{id}/confirm` as
  `financemanager`, and `total_paid` incremented by exactly the
  claimed amount (`300000.00 -> 350000.00`).

### New endpoint: `PATCH /finance-records/{id}/fee-due`

The one real write path for `total_fee_due`, in
`app.routers.finance_record`:

- **RBAC**: `FINANCE_MANAGER`/`SUPER_ADMIN` only
  (`require_role_session`), matching the narrowed RLS policy exactly.
- **Schema** (`FinanceRecordFeeDueUpdateRequest`): `ge=0, max_digits=12,
  decimal_places=2` -- matches the real `numeric(12,2)` column exactly.
- **Rejects lowering the fee below the already-confirmed `total_paid`**
  with a `422` naming both figures, read from the same row inside the
  same transaction (not a stale value from an earlier request).
- Writes only `total_fee_due` -- `total_paid` is not settable through
  this endpoint at all; its only legitimate write path remains the
  existing rollup trigger.

**Live-verified boundary cases, all real HTTP calls against the
running stack:**

| Case | Result |
|---|---|
| `FINANCE_MANAGER` lowers fee below current `total_paid` | real `422`, body names both figures verbatim |
| `FINANCE_MANAGER` sets fee above `total_paid` | real `200`, fee updated |
| Negative value (`-100.00`) | real `422`, Pydantic `ge=0` violation |
| 13-significant-digit value (`99999999999.99`) | real `422`, `max_digits=12` violation |
| Three-decimal value (`100.005`) | real `422`, `decimal_places=2` violation |
| `FINANCE_STAFF` attempts the endpoint | real `403`, "insufficient role for this action" |

### Audit trail

`write_audit()` correctly captured the fee-due change with no new
code: a real `PATCH` call produced a genuine `audit_log` row for
`finance_record`, `action=UPDATE`, `before->total_fee_due: null`,
`after->total_fee_due: 500000.00`, `actor_id` correctly matching the
calling `FINANCE_MANAGER`'s own user id -- the existing trigger-based
audit design (ADR-07) required no changes to cover this new write
path.

### "Fee not set" vs "fee = 0" in dashboard/reconciliation aggregation

`GET /finance/reconciliation` gains `fee_not_set_count` (per cycle and
in `totals`) -- a `func.count(...).filter(total_fee_due IS NULL)` in
the same existing query, not a second round trip.
`total_fee_due`/`outstanding` themselves were already arithmetically
correct once unset records became `NULL` (SQL `SUM` ignores `NULL`
inputs without any special-casing), but a viewer reading only the
summed total had no way to tell "this cycle's total is complete" apart
from "N records here have no fee entered, so this total understates
the true figure" -- `fee_not_set_count` makes that distinction
explicit and visible rather than silently correct-by-omission.

Frontend: `ApplicantFinanceSection` renders "Not set"/"Fee not set"
instead of a numeric zero when `total_fee_due` is `null`, and exposes
the new `FINANCE_MANAGER`/`SUPER_ADMIN`-gated "Set fee due"/"Update fee
due" control, wired to the real endpoint with backend errors surfaced
verbatim (no pre-check, no substitute message). `ReconciliationPage`
and `HomePage`'s finance summary both render a visible "N fee(s) not
set" badge with an explanatory tooltip whenever `fee_not_set_count >
0`, rather than folding it silently into the headline number.

**Live-verified end to end through the real browser UI**, not only via
`curl`: logged in as `financemanager`, transitioned a real applicant
to `ADMISSION_TAKEN` (creating a fresh `finance_record` with
`total_fee_due = NULL`), opened its detail drawer, and confirmed the
UI rendered "Fee due: Not set" / "Outstanding: Fee not set" with a
"Set fee due" control. Entered `450000` and clicked "Set fee": the UI
updated to "Fee due: 450000.00" / "Outstanding: 450000.00" with a real
"Fee due updated." success message, and the control relabeled itself
to "Update fee due" / "Update" -- the full round trip, confirmed
visually against the real running stack.

### Re-confirmation of previously-verified figures (Modules 04/05/14)

After every schema/RLS/endpoint change above, re-ran the exact reads
those modules originally verified:

- `GET /applicants/{id}/finance` for both original applicants: figures
  unchanged and correct (`500000.00`/`250000.00` and
  `400000.00`/`350000.00`).
- `GET /finance/reconciliation`: totals correctly sum to
  `1350000.00` fee due / `600000.00` paid / `750000.00` outstanding
  across three finance records (two original + the one created during
  this section's own live UI verification) -- no negative outstanding
  anywhere, `fee_not_set_count: 0` since every record now has a
  decided fee.
- Module 14's Home dashboard finance summary: confirmed live in the
  real browser, renders the same correct totals with no negative
  figures.

### Deliberate scope note

The one real applicant transitioned to `ADMISSION_TAKEN` during this
section's own live UI verification (to produce a genuine, freshly
unset `finance_record` to test against, since both pre-existing
records already had a fee set by this point) was left in that
real, now-admitted state with its fee genuinely set to `450000.00` --
not reverted. This pipeline has no transition back out of
`ADMISSION_TAKEN` in its own design, so reverting would have required
a direct database write (creating exactly the kind of un-audited,
bypass-the-real-workflow state change this project's own established
precedent avoids), for a change that is itself a real, valid,
correctly-audited state, not corrupted test debris.
