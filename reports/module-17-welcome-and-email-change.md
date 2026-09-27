# Module 17: admin-created-user welcome email (no admin-supplied password) and self-service email-change confirmation

## Scope

Two pieces, both reusing Module 16's `password_reset_token` machinery
rather than forking a parallel one:

1. **Admin-created accounts get no admin-supplied initial password.**
   `POST /users` no longer accepts a `password` field at all. Instead
   it creates the account with a real, immediately-discarded, never-
   revealed credential (structurally un-loggable-in-with), and sends a
   real welcome email through Mailpit carrying a single-use activation
   link. The account is genuinely unusable until the new hire follows
   that link and sets their own real password.
2. **Self-service email-change confirmation.** An authenticated user
   can request a change to their own login email; nothing changes
   until they click a confirmation link sent to the *new* address,
   proving they actually control that mailbox.

## Design decisions (made and documented, not left implicit)

### 1. How does an admin-created account stay genuinely unusable until activated?

**Considered:** a sentinel/null value in `password_hash`, or a separate
`is_activated` boolean gate checked at login.

**Chosen:** a real Argon2id hash of a random, `secrets.token_urlsafe(32)`
value that is generated once inside `create_user`, used for exactly one
`hash_password` call, and then thrown away -- never logged, stored a
second time, or transmitted anywhere. `POST /auth/login`'s own
`verify_password` call runs completely unmodified against this hash;
it simply can never match anything a caller submits, because the
plaintext behind it no longer exists anywhere.

**Why not a null/sentinel column or a login-time boolean check
instead:** either would require a new branch in the login route
itself -- and a new branch is a new place to get the logic wrong, and
a new observable difference (an early-return vs. a real hash
comparison) that could reopen a timing side-channel Module 16's
`verify_password_dummy` already closed for the "account doesn't
exist" case. Reusing the exact same `verify_password` call path for
"not yet activated" means there is no new timing signature to reason
about at all -- the unactivated case *is* a real password verification
attempt, it just always fails.

`User.activated_at` (new nullable column) is a deliberately separate,
**display-only** signal: "has this account ever successfully
completed a password-setting redemption" (welcome or later
forgot-password, whichever happens first), not itself a login gate.
It exists purely so `UsersPage` can show a genuine "Pending
activation" badge to an admin, distinguishing "never set up" from
"already active" -- the actual security boundary is the unguessable
password hash above, this column never gates anything.

Backfilled to `created_at` for every pre-existing account in the
migration -- every account that existed before this module always had
a real, admin-supplied password from creation, so none of them are
genuinely "pending" and none should suddenly show a false "pending
activation" badge the moment this migration runs.

### 2. Fork a new token table, or reuse `password_reset_token`?

**Chosen:** reuse. `PasswordResetToken` gained one new nullable
column, `new_email`. `NULL` means "password-type token" (redeemable
by the existing `POST /auth/reset-password`, used for both an
ordinary self-service password reset *and* welcome/activation --
they are mechanically identical: prove you hold the raw token, set a
new password). Non-`NULL` means "email-change token" (redeemable only
by the new, distinct `POST /auth/confirm-email-change`).

**Why not a second table:** the two token kinds share every real
property that matters -- single-use, Argon2id-hashed, expiring, tied
to one user -- and forking a table would have meant duplicating the
hash-comparison linear scan, the used/expired distinction logic, and
the audit-trigger wiring, all for a difference that is really just
"what does redeeming this token change." One extra nullable column
and a `new_email IS NULL` / `IS NOT NULL` filter at each redemption
endpoint keeps the two kinds mutually exclusive without any of that
duplication.

### 3. Should a pending email-change be visible to the user before they confirm it?

**Chosen: visible.** `GET /auth/me` gained a `pending_email` field
(queries `PasswordResetToken` directly for the session's own user --
no new column needed) so `ProfilePage` can show a real "Pending
change to X" badge immediately after the request is submitted.

**Why not stay silent until confirmation:** the alternative leaves the
account holder with no way to tell, short of manually checking the
new inbox, whether their own change request actually registered --
indistinguishable from the request having silently failed. Showing it
costs nothing security-relevant: this is the account's own
authenticated session reading back its own pending state, not a third
party learning anything about someone else's account.

## Backend

- **Migration `0011_welcome_and_email_change.py`**: adds
  `user.activated_at` (backfilled to `created_at`), adds
  `password_reset_token.new_email`.
- **`User`/`PasswordResetToken` model docstrings** rewritten to
  explain both reuse decisions above in place, not just in this
  report.
- **`POST /users` (`create_user`)** rewritten: no `password` field on
  `UserCreateRequest` anymore. Generates the throwaway password,
  leaves `activated_at=None`, issues a 24-hour welcome token (new
  `WELCOME_TOKEN_TTL_HOURS`, deliberately longer than password-reset's
  30-minute `PASSWORD_RESET_TOKEN_TTL_MINUTES` -- an admin's welcome
  email may sit unread over a weekend in a way a self-initiated
  password reset never should), sends a real welcome email with
  **no TOTP secret/QR/instructions**, just a generic "you'll be
  prompted if your role requires it" line -- TOTP enrollment still
  goes through the exact same in-session `enroll/start`+`confirm`
  flow every account has always used, never through an email channel.
- **`POST /auth/reset-password`** extended: filters on
  `new_email IS NULL` so an email-change token can never be redeemed
  here; stamps `user.activated_at` on the account's first-ever
  successful redemption (checked before the write, so a later,
  ordinary reset never re-stamps it).
- **New `POST /auth/change-email`** (`get_current_user`): issues an
  email-change token, sends the confirmation to the **new** address,
  deliberately stays silent about whether that address is already
  taken by a different account (anti-enumeration for an authenticated
  caller probing on someone else's behalf, the same reasoning
  `forgot-password` already established for an unauthenticated one).
- **New `POST /auth/confirm-email-change`** (unauthenticated,
  token-only): filters `new_email IS NOT NULL`; real, distinct
  rejection reasons ("invalid or expired confirmation token" vs. "this
  confirmation link has already been used"); checks the email
  collision **at confirmation time**, not request time, with a real
  `409` if it's since been taken; updates `User.email`; deliberately
  does **not** force-logout existing sessions, since only the
  identity label changes, not credential trust (contrast
  `reset-password`, which does force-logout, since a password reset
  implies the old credential is no longer trusted).
- **`GET /auth/me`** extended with `pending_email`.
- **Schemas**: `UserCreateRequest` lost `password`; `UserSummary`
  gained `activated_at`; new `ChangeEmailRequest`/`ChangeEmailResponse`/
  `ConfirmEmailChangeRequest`, extended `MeResponse`.

## Frontend

- **`SetInitialPasswordPage.tsx`** (new): a deliberately separate
  component from `ResetPasswordPage`, not a reused prop-flag variant
  -- copy consistently says "activate"/"choose," never "reset," since
  there is no prior password to reset.
- **`ConfirmEmailChangePage.tsx`** (new): requires an explicit button
  click, never auto-confirms on page load -- avoids an email client's
  own link-prefetcher (Outlook safe-links, Gmail image-proxying
  crawlers, etc.) silently burning the single-use token before the
  real person ever sees the page.
- **`ProfilePage.tsx`**: new email-change form plus the pending-change
  badge described above.
- **`UsersPage.tsx`**: removed the password field from the create-user
  form (replaced with explanatory copy about the welcome email), added
  a tooltip-explained "Pending activation" badge next to Active/Inactive.
- Types/hooks/routes wired through `types.ts`, `useAuth.ts`,
  `router.tsx` (`/set-initial-password`, `/confirm-email-change`).

## Live verification

All of the following were exercised against the real running stack
(Docker, real Postgres, real Mailpit, real browser UI where noted),
not inferred from reading the code.

### Welcome / activation flow

1. Logged in as `SUPER_ADMIN` via the real UI (with live TOTP),
   created `newhire@sirius.app` (role `FINANCE_MANAGER`, mandatory
   TOTP) through the real create-user form -- no password field
   present. "PENDING ACTIVATION" badge appeared correctly in the real
   table immediately.
2. Read the real welcome email directly in Mailpit's own UI: correct
   subject, correct role name, real activation link, correct 24-hour/
   single-use copy, **confirmed no TOTP secret, QR code, or
   enrollment instructions present anywhere in the body**.
3. Confirmed via curl and via the real login UI that logging in
   against the not-yet-activated account is genuinely rejected --
   real `401`, generic message, no signal distinguishing it from a
   wrong password on any other account.
4. Followed the real activation link, set a real password through
   `SetInitialPasswordPage` -- real success.
5. Logged in with the new password: genuinely entered real TOTP
   enrollment (QR + ten backup codes) exactly like any other new
   mandatory-TOTP account. Completed enrollment for real (separate
   curl session, secrets printed to chat only, never committed) to
   leave the account in a working state.
6. Re-checked the Users page: "Pending activation" badge genuinely
   disappeared, matching the real `activated_at` transition.

### Email-change flow

1. Logged in as `admissionscounselor@sirius.app`, submitted a real
   email-change request via `ProfilePage` to
   `counselor-new-address@sirius.app` -- current `Email` field stayed
   unchanged, "PENDING CHANGE TO..." badge appeared correctly.
2. Confirmed via curl: old email still logs in (`200`), new email
   genuinely rejected (`401`) -- nothing changed yet, as designed.
3. Read the real confirmation email in Mailpit (correct new-address
   recipient, correct 30-minute/single-use copy).
4. Followed the real confirmation link, clicked the explicit "Confirm
   email address" button -- the page did **not** auto-confirm on
   load, confirmed by loading it and observing no state change until
   the click. Real success message shown.
5. Confirmed via curl: old email now genuinely rejected (`401`), new
   email now genuinely works (`200`, **same `user_id`** as before --
   proving an update, not a new account).
6. Confirmed the same login also works through the real browser login
   form, not just curl -- logged in via the UI with the new email,
   landed on the real Home page as `ADMISSIONS_COUNSELOR`. Checked the
   real Profile page afterward: shows the new email, no pending badge
   remaining.

### Rejection-path spot checks for `confirm-email-change` specifically

Module 16's rejection-path testing only covered password-reset tokens;
this module's `confirm-email-change` has its own distinct branches
worth checking on their own:

- **Already-used token**: replayed the exact token from the
  already-completed confirmation above -- real `400`,
  `"this confirmation link has already been used"`, distinct from the
  generic invalid/expired message.
- **Never-existed token**: an arbitrary string -- real `400`,
  `"invalid or expired confirmation token"`.
- **Collision at confirmation time**: logged in as
  `counselor-new-address@sirius.app`, requested a change to
  `auditor@sirius.app` (a real, already-existing account's email).
  The *request* succeeded silently (by design -- see decision 3's
  reasoning extended to this endpoint). Retrieved the real token from
  Mailpit and attempted to confirm it: real `409`,
  `"this email address is now in use by another account"`. Confirmed
  via curl afterward that **both** accounts were left completely
  unaffected by the rejected attempt -- the counselor account's email
  never changed, and `auditor@sirius.app` still logs in normally.

### `audit_log` sanity check (same standard Module 16's follow-up applied)

Queried `audit_log` directly after the full sequence above: every
`user` UPDATE (activation stamp, email change) and every
`password_reset_token` INSERT/UPDATE (welcome token issuance and
redemption, email-change token issuance and redemption) appears with
matching timestamps in correctly paired rows -- confirming the
existing `write_audit()` trigger fires for this module's new columns
and new write paths exactly as it does for everything else, with no
new code required to make that true.

## Cleanup performed before treating this module as done

- `newhire@sirius.app` intentionally left in its final working state
  (activated, TOTP-enrolled) -- a real account demonstrating the
  full flow, not reverted.
- `admissionscounselor@sirius.app`'s email reverted back to its
  original value via a second real change-email/confirm cycle, then
  verified via login that the original email works again.
- All temporary cookie jars and Mailpit's inbox cleared.
- No temporary TOTP-generator or credential-holding scripts remain in
  the repo (`_totp_gen.py`, `_totp_newhire.py`,
  `_newhire_cookies.txt` never survived past the session that created
  them; none are present now).

## Process note: a debugging detour that was not a real app bug

A significant amount of time went into investigating what looked like
a broken Mantine `Modal` (the create-user modal appearing empty when
inspected). Multiple false leads were chased -- React fiber
inspection, portal container checks, coordinate-scaling theories,
click-mechanism theories -- before finding the actual cause: the
browser automation tool's default `eval` executes in an **isolated
extension JS world** that cannot see React-portaled DOM content at
all, while `page_world: true` executes in the real page context and
sees it correctly. Every "modal is empty" finding before that point
was an artifact of using the wrong `eval` context, not a defect in the
app. No code changed as a result -- worth recording here since it
consumed real verification time and could recur in a future module
against any other portal-rendered UI (other modals, popovers, etc.)
unless `page_world: true` is used from the start when inspecting them.

## Infrastructure notes

Both `api` and `migrate` images were rebuilt explicitly for this
module (`docker compose build api migrate`), applying the lesson
Module 16 first established: they are separate images despite sharing
a build context, and rebuilding only one leaves the other running
stale code against a schema it doesn't expect. Migration `0011`
applied cleanly; `alembic_version` confirmed `0011`; all 8 pre-existing
accounts confirmed backfilled with `activated: true`.

## Final checks

- `tsc --noEmit`: clean.
- `impeccable detect` against every new/modified frontend file: no
  findings.
- `git status`: only this module's own files touched; no stray temp
  files.

## Follow-up verification

Two real gaps closed after this module's original verification, the
same shape every prior follow-up in this project used.

### 1. Rate limiting for `POST /auth/change-email`

**Decision: yes, needed, and implemented** -- the same conclusion
Module 16's own follow-up reached for `forgot-password`, extended
here rather than accepted as a difference.

**Why being authenticated does not change the answer.** The task
description's own framing was checked directly rather than assumed:
does `change-email` genuinely create the identical third-party-
mail-bombing exposure `forgot-password` has? Yes. `change-email`
requires `get_current_user`, but that dependency only proves *who the
caller is* -- it proves nothing about whether the caller owns
`new_email`, the address the side effect (a real email) actually
lands on. An authenticated `ADMISSIONS_COUNSELOR` account can name
`victim@sirius.app` as `new_email` and this endpoint will happily
send that address mail, repeatedly, with no proof of ownership
required -- mechanically the same gap `forgot-password` has for an
unauthenticated caller naming an arbitrary email. The harm lands on a
third party (whoever owns the named address) either way, not on the
caller's own account, which is the actual load-bearing fact -- not
"is the caller authenticated." Being authenticated only means the
*caller* is accountable and identifiable after the fact (their own
session is on record); it does not mean the *target* consented to
receiving the mail, which is what the rate limit actually protects
against.

**Considered and rejected: no limiter, on the theory that
authentication alone is a sufficient deterrent.** Rejected because an
attacker does not need a *fresh* or *anonymous* account to abuse
this -- any already-compromised, or even a legitimately-owned but
malicious, authenticated session can target an arbitrary victim
address with the exact same lack of ownership proof an unauthenticated
`forgot-password` caller has. "The caller had to log in first" raises
the bar for who can attempt this at all, but does not lower the
per-attempt harm to the victim once someone clears that bar, and this
codebase already has plenty of ordinary, legitimately-issued accounts
(every role) capable of clearing it.

**Implementation.** Reused the exact Valkey fixed-window pattern
`check_forgot_password_rate_limit` already established
(`app.core.rate_limit`): new `check_change_email_rate_limit`, same
threshold (3 requests / 15-minute window), same `INCR`+`EXPIRE`
mechanism, factored through a shared `_check_fixed_window_rate_limit`
helper both functions now call rather than duplicating the counter
logic a second time. **Keyed by the target `new_email`** (lowercased),
under a distinct `change_email_rl:` prefix so the two endpoints'
windows never share or interfere with each other's counts -- not by
the calling account, for the same reason `forgot-password`'s own
limiter is not keyed by caller IP: the threat is "this address gets
flooded regardless of who is doing the flooding." A limiter keyed by
the caller's own account would let a single attacker rotate through
several different authenticated accounts (or simply reuse the same
one, since nothing here throttles requests *from* an account) to keep
sending the same victim address confirmation mail past any
per-account ceiling; keying by the target address closes that
regardless of how many different accounts are involved. Checked
before any database work or token issuance, in `change_email` itself.

**Live verification, real HTTP responses, genuine repeated requests**
(same methodology as Module 16's own follow-up):

- Logged in as `admissionscounselor@sirius.app`, sent 4 real
  `POST /auth/change-email` requests to the identical target address
  (`ratelimit-target@sirius.app`) in sequence: requests 1-3 -> real
  `200` with the real success body; request 4 -> real `429`,
  `{"detail":"too many email-change requests for this address; try
  again later"}`.
- Confirmed via `valkey-cli GET`/`TTL` on the real key
  (`change_email_rl:ratelimit-target@sirius.app`) that the counter
  (value `5` after the test sequence) and its ~900-second expiry are
  genuinely present in Valkey, not merely inferred from response
  codes.
- **Keyed-by-target, not by caller, confirmed directly**: logged in
  as a completely different account (`auditor@sirius.app`) and sent a
  `POST /auth/change-email` naming the *same*, already-throttled
  target address -- real `429`, from a session that had made zero
  prior requests of its own. Proves the limiter protects the victim
  address regardless of which account is doing the requesting, not
  merely the requesting account's own quota.
- Confirmed normal single-request flow is unaffected: the same
  second account requesting a change to a fresh, never-targeted
  address (`fresh-unthrottled-target@sirius.app`) -> real `200`,
  and a distinct Valkey key (`change_email_rl:fresh-unthrottled-
  target@sirius.app`) created for it, independent of the throttled
  one.
- All test Valkey keys, Mailpit messages, and `password_reset_token`
  rows created by this verification were deleted afterward.

### 2. Expired-token rejection for `confirm-email-change`

Module 16's own expired-token test only covered password-reset
tokens; `confirm-email-change` has its own distinct query and rejection
branches, so this was checked directly rather than assumed to behave
identically by symmetry with `reset-password`.

Requested a real email change from `admissionscounselor@sirius.app`
to `expiry-test-target@sirius.app`, extracted the real raw token from
Mailpit's own API, located that exact row in `password_reset_token`
by its real `id`, then forced `expires_at` five minutes into the past
via a direct `UPDATE` -- the identical technique Module 16 used for
password-reset tokens, applied here to an email-change row instead
(the only practical way to test a 30-minute TTL without an actual
30-minute wait).

Attempting to confirm that now-expired token -> real `400`,
`"invalid or expired confirmation token"` -- **correctly the generic
bucket, not misrouted into the "already been used" branch**, confirming
the `expires_at > now()` filter on the main query genuinely excludes
it before the already-used fallback query ever runs (that fallback
query has no `expires_at` filter of its own by design -- an
already-used token is already-used regardless of whether it also
happens to be expired -- so an expired-but-never-used token correctly
falls through to the generic message instead).

Confirmed no side effects from the rejected attempt: re-queried the
row directly -- `used_at` still `NULL` (the rejection happened before
any write, not after an update that was then rolled back) -- and
confirmed `admissionscounselor@sirius.app`'s original email still
logs in normally afterward, completely unaffected.

Cleaned up the test row and Mailpit message afterward.
