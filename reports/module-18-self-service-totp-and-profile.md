# Module 18: self-service name edit, self-service TOTP re-enrollment, and voluntary TOTP opt-in

## Scope

Three pieces:

1. **Self-service name edit**: confirm whether `User.full_name` (which
   `UsersPage` has displayed since Module 15) is a real column or a
   display artifact, and if real, add a self-service
   `POST /auth/change-name` endpoint + `ProfilePage` form.
2. **Self-service voluntary TOTP re-enrollment**: let an already-
   enrolled account discard its current secret and go through a fresh
   enroll/confirm cycle, gated on re-authentication (current password
   **and** a live current TOTP code, not either alone), with the
   account's *other* live sessions force-logged-out but the acting
   session kept alive through the multi-step flow.
3. **Voluntary TOTP opt-in for non-mandatory roles**: confirm whether
   `ADMISSIONS_COUNSELOR`/`ADMISSIONS_MANAGER`/`AUDITOR` currently have
   any way to enable TOTP at all (login only ever prompts the three
   mandatory roles), and if not, add a `ProfilePage` entry point
   reusing the existing enroll endpoints verbatim.

## Part 1 -- `User.full_name`: real column, not a display artifact

Checked directly against the live database, not by re-reading the
model file: `\d "user"` on the real running Postgres instance shows
`full_name character varying NOT NULL` as a genuine column, with real,
non-null data for every one of the 9 current accounts. Traced it back
to migration `0002_schema.py` -- the very first schema migration, not
something added incidentally later. **No migration needed for this
part** -- the premise that it might be display-only was checked and
found false, stated plainly rather than silently assumed either way.

### Backend

New `ChangeNameRequest` schema and `POST /auth/change-name`
(`api/app/routers/auth.py`), following the exact "trust the session,
never the body" pattern every other self-service mutation in this
router already uses -- no `user_id` field. Deliberately has **no
confirmation step, no token, and no force-logout** unlike
`change-email`/`change-password`/the new TOTP self-reset below: a name
is pure display data, changes nothing `get_current_user`/`require_role`
or any RLS policy checks, so none of the machinery that exists to
protect an actual credential applies here.

### Frontend

`ProfilePage` gained a "Change name" form (`useChangeName`, wired to
the new endpoint, invalidates `/auth/me` on success so the summary
card and the app-shell header both update immediately).

## Part 2 -- self-service TOTP re-enrollment

### Design decision: why both password AND current TOTP code, not either alone

**A password check alone is not sufficient.** An attacker who has
only compromised the password (phished, reused, leaked in an
unrelated breach) would otherwise be able to strip the account's real
second factor and install their own -- exactly defeating the entire
point of requiring a factor beyond "something you know." Requiring a
live code from the **existing** secret specifically (not a backup
code, and not the new secret's own code, which doesn't exist yet at
that point in the flow) proves the caller currently possesses the
already-enrolled physical device/app -- the one thing a password-only
attacker does not have.

### Design decision: partial, not blanket, force-logout

`destroy_sessions_for_user` (Module 15's own force-logout, reused
verbatim by `reset-password` and admin `reset-totp`) deletes **every**
session for the account, including the one issuing the call. That is
correct for those two callers -- both are either unauthenticated
(reset-password) or admin-on-someone-else's-account (reset-totp), so
there is no "acting session" to preserve. Self-service TOTP reset is
different in kind: it is, by construction, performed *from inside* an
already-live session that is about to invalidate its own account's
sessions, and needs to survive long enough to drive the immediate
follow-up `enroll/start` + `enroll/confirm` calls. Blanket deletion
would destroy the very session running the flow it is itself
performing.

**New `destroy_other_sessions_for_user(user_id, keep_session_id)`**
(`api/app/core/sessions.py`) -- a genuine, deliberate variant, not the
same call reused unchanged: reads the same `user_sessions:{user_id}`
Valkey index, deletes every member except the one to keep, and removes
only the deleted ids from the index (the surviving session stays
correctly tracked). **New `mark_totp_pending(session_id)`** -- the
mirror image of the existing `mark_totp_verified`: flips an
already-verified session's `totp_verified` back to `False` *in place*
without deleting it, so the acting session survives but is forced back
through `get_current_user`'s own TOTP gate for anything beyond
`enroll/start`/`enroll/confirm` (which only depend on
`get_current_session`, the same as an ordinary first-time mandatory
enrollment).

### `POST /auth/totp/self-reset` (`api/app/routers/auth.py`)

New `SelfTotpResetRequest` (`current_password`, `current_totp_code`).
Requires `get_current_user` (a fully-verified session, matching
`change_password`'s own baseline). Checks, in order: account has
`totp_enabled=True` at all (`400` otherwise -- this is re-enrollment,
not first-time enrollment, which stays on `totp_enroll_start`);
`verify_password` against the real stored hash (`400` "current
password is incorrect" on mismatch); `verify_code` against the
*existing* decrypted secret (`400` "invalid or expired TOTP code" on
mismatch). On success: provisions a fresh secret exactly like
`totp_enroll_start` does, deletes the old backup codes and issues ten
new ones, flushes, then calls `destroy_other_sessions_for_user` +
`mark_totp_pending` on the acting session. Returns the same
`TotpEnrollStartResponse` shape ordinary enrollment does -- the client
still must call `POST /auth/totp/enroll/confirm` with a live code from
the *new* secret to actually flip `totp_enabled` back to `True`,
reusing that endpoint verbatim rather than forking a distinct confirm
route.

### Frontend

`ProfilePage`'s "Two-factor authentication" section now branches on
`me.totp_enabled`: not enrolled -> voluntary opt-in button (Part 3);
already enrolled -> "Reset two-factor authentication" button opening a
password + current-code form, which on success feeds directly into the
same QR/backup-code/confirm UI the voluntary-enrollment and
`LoginPage` flows already use.

## Part 3 -- voluntary TOTP opt-in for non-mandatory roles

**Checked directly, not assumed**: grepped `LoginPage.tsx` and
`auth.py`'s login route -- the only path into TOTP enrollment was
`POST /auth/login`'s own `totp_enrollment_required` branch, which only
ever fires for `MANDATORY_TOTP_ROLES`. `ADMISSIONS_COUNSELOR`/
`ADMISSIONS_MANAGER`/`AUDITOR` genuinely had no way to enable TOTP at
all before this module -- confirmed live later in this same session
(see verification below) by finding `admissionscounselor@sirius.app`
had `totp_enabled=false` and no entry point to change that anywhere in
the app.

**Fix**: `ProfilePage` gained a "Set up two-factor authentication"
button, shown only when `!me.totp_enabled`, reusing
`POST /auth/totp/enroll/start` + `POST /auth/totp/enroll/confirm`
**verbatim** -- the exact same two calls `LoginPage`'s own mandatory-
enrollment stage already makes, not a new enrollment mechanism. Gated
on `!me.totp_enabled` only, not on role: `MANDATORY_TOTP_ROLES`
already have their own forced path through `LoginPage` on first login,
so surfacing this button to them too would be a redundant, confusing
second entry point into the same flow (and in practice never shown to
them, since a mandatory-role account reaching `ProfilePage` at all
already has `totp_enabled=true`).

### The real gap this surfaced: login gated on role, not on enrollment state

Building this exposed a genuine, previously-latent defect, found by
reasoning through the new feature rather than by an isolated test:
`POST /auth/login`'s own `totp_verified_initial` computation was
`not (role in MANDATORY_TOTP_ROLES)` -- correct for the three
mandatory roles, but silently wrong for any account that is
TOTP-enrolled *without* its role requiring it. Such an account would
have sailed straight through login with `totp_verified=True`, never
once being asked for the very second factor it just voluntarily set
up -- the new opt-in feature would have been enrollment theater, a QR
code and backup codes a subsequent login never actually checks.

**Fixed** by keying the initial `totp_verified` value off
`user.totp_enabled` first, falling back to role mandate only when
`totp_enabled` is `False`:

```python
totp_mandatory = RoleCode(role_code) in MANDATORY_TOTP_ROLES
totp_active = user.totp_enabled or totp_mandatory
totp_verified_initial = not totp_active
```

`LoginResponse.totp_required`/`totp_enrollment_required` follow the
same `totp_active` value, so a voluntarily-enrolled account is now
correctly told to verify (not enroll again) on every subsequent login.
This was caught and fixed *before* any live verification below, not
discovered by the verification itself -- but the verification still
exercises it directly (see "login now genuinely requires TOTP" below),
since a fix that looks right on paper deserves the same live check
every other claim in this project gets.

## Live verification

Every claim below was exercised against the real running stack, not
inferred from reading the code.

### Part 1: name change

- Logged in as `admissionscounselor@sirius.app` via the real login UI,
  submitted a real name change ("Admissions Counselor Jane") via the
  real `ProfilePage` form. Confirmed immediately: nav-bar header and
  the Profile summary card both updated without a page reload.
- Confirmed directly in the live database: `full_name` genuinely
  updated for that row.
- Logged in as `SUPER_ADMIN` (real UI, real TOTP), navigated to the
  real `UsersPage` table: confirmed the same new name appeared there
  too, via both `GET /users` (raw JSON) and the rendered table.
- Reverted the name back to "Admissions Counselor" afterward via a
  second real `POST /auth/change-name` call, confirmed via a fresh
  `GET` that it reverted cleanly.

### Part 2: self-service TOTP re-enrollment

Using `admissionscounselor@sirius.app` (already voluntarily enrolled
by this point, see Part 3 below) as the test account:

- **Wrong current password, correct-shaped TOTP field**: submitted
  via the real `ProfilePage` form -> real rejection, the backend's own
  literal text ("current password is incorrect") surfaced verbatim in
  the UI. Confirmed via direct DB query afterward: `totp_enabled`
  unchanged, no mutation occurred.
- **Correct current password, wrong/stale TOTP code**: real rejection,
  "invalid or expired TOTP code" -- a distinct, real message, not
  folded into the password-failure bucket. Confirmed no side effects
  the same way.
- **Real second session established first, independently**: logged
  into the *same* account via a separate curl-based session (fully
  through the real login + real TOTP verify flow, not a synthetic
  cookie), confirmed live via `GET /auth/me` before proceeding.
- **Correct password + correct live TOTP code**: real success --
  genuine fresh QR code and ten new backup codes returned and rendered
  in the UI.
- **Second session confirmed force-logged-out**: immediately after
  the successful self-reset, the separate curl session's own
  `GET /auth/me` returned a real `401` ("session expired or invalid")
  -- confirming `destroy_other_sessions_for_user` genuinely closed it.
- **Acting session confirmed still alive**: the browser tab that
  performed the reset was checked directly (its own `fetch('/auth/me')`
  in-page) immediately after -- returned a real `200` with
  `totp_enabled: false` (the correct mid-reset state), proving the
  session survived and was merely flipped back to TOTP-pending, not
  destroyed, exactly as `mark_totp_pending`'s own docstring claims.
- **Completed the multi-step flow in the same session**: entered a
  live code from the new secret via `POST /auth/totp/enroll/confirm`
  (real UI submission) -> real success, badge returned to "Enrolled".
  Confirmed in the database: `totp_enabled=true`, exactly 10 backup
  codes present (the old set fully replaced, not accumulated
  alongside the new one).
- **`audit_log` sanity check**: queried directly after the full
  sequence -- the self-reset's own write landed as one real `user`
  UPDATE plus ten real `user_backup_code` DELETEs and ten real INSERTs
  at the identical timestamp, confirming the existing `write_audit()`
  trigger fires for this module's new write path with no code change
  required, same as every prior module's own audit-log check.

### Part 3: voluntary opt-in + the login-flow fix

- Confirmed `admissionscounselor@sirius.app` started this module at
  `totp_enabled=false` with no in-app path to change that.
- Logged in via the real UI (no TOTP prompt, correctly, since neither
  mandated nor yet enrolled), navigated to `ProfilePage`, clicked the
  new "Set up two-factor authentication" button -- real QR code and
  ten real backup codes returned. Confirmed in the database
  immediately: a real secret genuinely persisted for the correct
  account (see "process note" below for a self-inflicted mixup this
  caught).
  Confirmed via a real `enroll/confirm` submission with a live code:
  real success, badge flipped to "Enrolled" in the UI.
- **Logged out and logged back in as this same account** -- the real
  point of this whole feature: confirmed via curl (`totp_required:
  true, totp_enrollment_required: false`) and via the real login UI
  (prompted for a six-digit code, not silently let through) that this
  now-voluntarily-enrolled, non-mandatory-role account genuinely
  requires TOTP on login where it did not before. Completed the real
  verify step -> landed on the real Home page as `ADMISSIONS_COUNSELOR`.
  This is the login-flow fix's own live proof: before that fix, this
  exact sequence would have skipped straight past the TOTP prompt.

## Process note: a real self-inflicted verification mistake, caught and corrected

While setting up a second browser tab to check `UsersPage` as
`SUPER_ADMIN`, both tabs were pointed at the same origin
(`127.0.0.1:5173`) and therefore shared the same browser cookie jar --
logging into `superadmin` in the second tab silently replaced the
session cookie for the *first* tab too, where `admissionscounselor`'s
voluntary-enrollment test was about to run. The resulting "Set up
two-factor authentication" click landed on `superadmin`'s account
instead, calling `enroll/start` and flipping `superadmin.totp_enabled`
to `false` -- a real, if self-inflicted, security-relevant mutation
against the wrong account. Caught immediately by checking the database
directly after every enrollment click (the established verification
discipline this project uses) rather than trusting the UI's own
success message: `admissionscounselor`'s row showed no secret at all,
while `superadmin`'s `totp_enabled` had unexpectedly flipped to
`false`. Fixed by completing the real, genuine re-enrollment already
in flight for `superadmin` (a live code from the newly-provisioned
secret), restoring `totp_enabled=true` before continuing. No code
defect -- this was purely a test-methodology error (two tabs, one
origin, one cookie jar) -- but it is the reason every subsequent
multi-session test in this module used one browser tab plus
independent curl cookie jars instead of multiple browser tabs on the
same origin, and it is worth recording since the exact same mixup
could recur in a future module's verification if not deliberately
avoided.

A second, smaller mistake surfaced during login-flow verification: a
`browser eval` click on `LoginPage`'s "Verify" button (using
`page_world: true`) once produced a silent no-op that left the browser
on the login page despite the backend having already accepted the
code (confirmed independently via curl: real `204`). A direct `click`
action using a scoped selector, tried immediately after, worked
correctly and completed the real login. Not investigated further as a
possible app bug, since the backend was independently proven correct
via curl in the same window and the direct-click retry succeeded on
the very first attempt -- most likely the same eval-context class of
tooling gotcha Module 17 already documented for Mantine modals, not a
new one.

## Cleanup performed before treating this module as done

- `admissionscounselor@sirius.app`'s `full_name` reverted to
  "Admissions Counselor" (the name-change test's own artifact).
- `admissionscounselor@sirius.app`'s TOTP enrollment intentionally
  left in its final, working, re-enrolled state (this module's own
  real feature demonstrated end to end) -- not reverted, matching
  Module 17's precedent for `newhire@sirius.app`.
- `superadmin@sirius.app`'s password was changed once, mid-session,
  via a real `forgot-password`/`reset-password` cycle (its original
  value was never known to this session) so a real SUPER_ADMIN login
  could be exercised for the `UsersPage` cross-check; left at the new
  working value (`[REDACTED-Module22]`) rather than reverted, since the
  original was never available to revert to. `superadmin`'s TOTP
  enrollment was restored to its correct, working state after the
  accidental disable described above.
- All temporary cookie jars and the one-off TOTP-code-generator script
  copied into the `api` container were deleted; Mailpit's inbox
  cleared.
- `auditor@sirius.app` had a dangling, never-confirmed TOTP secret and
  ten unconfirmed backup codes left over from an earlier curl-based
  check of `POST /auth/totp/enroll/start`'s own DB-persistence
  behavior (part of diagnosing the cross-tab cookie mixup above) --
  harmless (`totp_enabled` stayed `false` throughout, so login was
  never affected), but cleared directly (`totp_secret_encrypted` reset
  to `NULL`, the ten orphaned backup-code rows deleted) for account
  consistency. Confirmed via a real login attempt afterward that
  `auditor@sirius.app` still authenticates normally.

## Follow-up verification: the real 400 for a not-yet-enrolled account

One gap remained open after the rest of this module's own verification:
`POST /auth/totp/self-reset`'s own docstring and route body both claim a
third, distinct `400` -- "TOTP is not currently enrolled for this
account" -- for the case where the caller's account has never enrolled
at all (`user.totp_enabled is False`), separate from either of the two
credential-mismatch rejections ("current password is incorrect" /
"invalid or expired TOTP code") Module 18's own live verification above
already exercised. That third path had never actually been called
against a real, live `totp_enabled=False` account and observed -- it was
read off the code, not proven.

**Finding the right account, live.** Queried the running database
directly (`SELECT email, totp_enabled FROM "user"`, joined against
`role`): `admissionsmanager@sirius.app` (`ADMISSIONS_MANAGER`) genuinely
had `totp_enabled=false` at the moment of this check -- a real account
still in its pre-opt-in state, not one that needed to be reset back into
it. No reset-to-that-state step was necessary.

**Call**: logged in as `admissionsmanager@sirius.app` for a real,
fully-authenticated session (`totp_required: false` in the login
response, confirming this account is neither TOTP-mandatory nor
currently enrolled -- exactly the precondition this check needs), then
called `POST /auth/totp/self-reset` directly with an otherwise
well-formed body (`current_password` correct, `current_totp_code` a
syntactically valid six-digit placeholder):

```
POST /auth/totp/self-reset
{"current_password": "[REDACTED-Module22]", "current_totp_code": "123456"}
```

**Real result**: `400`, body `{"detail": "TOTP is not currently
enrolled for this account"}` -- confirmed live, not inferred. This is
the exact literal string the route body raises on
`user.totp_enabled is False`, checked *before* either the password or
TOTP-code comparison runs (the placeholder code was never actually
verified against anything, since the enrollment check short-circuits
first) -- correctly and distinctly worded from the other two rejections:
this says "you're not enrolled, use the opt-in/first-enrollment path
instead" (`POST /auth/totp/enroll/start`), not "your credentials for
your existing enrollment didn't check out." All three of this endpoint's
documented `400` rejection reasons are now live-verified, each with its
own distinct, real message:

1. Not enrolled at all -- "TOTP is not currently enrolled for this
   account" (this follow-up).
2. Enrolled, wrong password -- "current password is incorrect" (Part 2
   above).
3. Enrolled, wrong/stale TOTP code -- "invalid or expired TOTP code"
   (Part 2 above).

No mutation occurred (this account's `totp_enabled` stayed `false`
throughout, confirmed by the rejection itself never reaching the
provisioning code path). No cleanup needed beyond deleting the one
throwaway curl cookie jar used for this check.

## Final checks

- `tsc --noEmit`: clean.
- `impeccable detect` against `ProfilePage.tsx`: no findings.
- `git status`: only this module's own files touched; no stray temp
  files.
