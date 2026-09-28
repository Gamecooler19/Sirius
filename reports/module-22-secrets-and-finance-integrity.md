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

*(pending)*
