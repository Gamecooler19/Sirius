# Module 16: Email infrastructure (Mailpit) and self-service password reset

## Scope

Two pieces:

1. **Real local SMTP infrastructure**: Mailpit as a new Docker Compose
   service -- a real SMTP server on the internal bridge network plus its
   own web UI/REST API on a loopback-published port, matching every
   other dev-facing service in this stack. No external email provider,
   no third-party API key.
2. **Self-service password reset**: `POST /auth/forgot-password` (takes
   an email, always returns the identical generic response regardless
   of whether that email exists) and `POST /auth/reset-password` (takes
   the raw token + new password, validates against a stored hash and
   expiry, rejects an expired/invalid or already-used token with a real,
   distinct reason). Frontend: a "Forgot password?" link on the login
   page, a forgot-password request page, and a reset-password page that
   reads the token from its own URL.

## Part 1 -- Mailpit (`deploy/docker-compose.yml`)

New `mailpit` service: `axllent/mailpit:latest`, SMTP exposed internally
(`expose: "1025"`, reachable as `mailpit:1025` by the `api` container
over the bridge network), web UI published on loopback only
(`127.0.0.1:8025:8025`) -- the same dual-surface pattern `rustfs`
already follows in this stack. The upstream image's own Dockerfile
(confirmed by fetching it directly) bakes in a `HEALTHCHECK` using a
`/mailpit readyz` subcommand -- no curl/wget dependency, no custom
healthcheck override needed here, unlike postgres/pgbouncer/valkey/
rustfs which do define their own. `api`'s `depends_on` now includes
`mailpit: condition: service_healthy`.

New `api`/`migrate`-adjacent settings (`api/app/core/config.py`):
`SMTP_HOST` (`mailpit`), `SMTP_PORT` (`1025`), `SMTP_FROM_ADDRESS`
(`no-reply@sirius.app`), `FRONTEND_BASE_URL` (the origin reset links
point at -- the Vite dev server's own address, not the API's own).

## Part 2 -- backend

### `api/app/core/mail.py` (new)

`send_mail(to_address, subject, body)` -- stdlib `smtplib`, not an
async SMTP client library, wrapped in `asyncio.to_thread` (defensive,
not load-bearing: a local Mailpit send is a few-millisecond operation,
and this codebase already has one precedent for calling a sync,
blocking library directly from an async route without a thread wrapper
at all -- `app.services.excel_import.parse_workbook`/`openpyxl`). No
real delivery ever leaves the stack: `SMTP_HOST`/`SMTP_PORT` are fixed
to `mailpit`/`1025` in `docker-compose.yml`, never user- or
attacker-controlled.

### `PasswordResetToken` (new model + migration `0010_password_reset_token`)

One row per issued reset request: `user_id` (FK), `token_hash`
(Argon2id, the same hasher `UserBackupCode.code_hash` already uses --
new `hash_reset_token`/`verify_reset_token` wrappers added to
`app.core.security`, same underlying `PasswordHasher`, not a distinct
algorithm), `expires_at`, `used_at`. Not RLS-scoped -- joins `user`/
`role`/`user_backup_code` as ADR-03's identity axis, for the same
structural reason: both endpoints touching this table are
unauthenticated by definition, so there is no `app.actor_role`/
`app.actor_id` GUC set when either endpoint's queries run. Gets the
standard `write_audit()` trigger (ADR-07) and an index on `user_id`,
matching `user_backup_code`'s own precedent.

### `POST /auth/forgot-password`

- Always returns the identical `ForgotPasswordResponse` regardless of
  whether the email exists -- the same anti-enumeration reasoning
  `/auth/login`'s own unknown-email path already established
  (`verify_password_dummy`'s docstring), taken further here since there
  is no password comparison to time-match at all: every code path
  returns the exact same response object.
- When the email does exist (and the account is active): generates a
  `secrets.token_urlsafe(32)` raw token (the same primitive
  `create_session` already uses for session ids), stores only its hash,
  sends a real email through Mailpit with a link
  `{FRONTEND_BASE_URL}/reset-password?token={raw_token}`. The raw token
  is never persisted anywhere after the response returns.

### `POST /auth/reset-password`

- Looks up the token by hash comparison against every unexpired,
  unused row (the same linear-scan-by-verify shape
  `totp_verify_backup_code` already uses for backup codes -- Argon2id's
  own random salt means there is no direct hash-equality lookup).
- **Real, distinct rejection reasons**: no match at all among
  unexpired/unused rows -> `"invalid or expired reset token"`; a token
  that matches by hash but was already used -> a separate query finds
  it specifically to return `"this reset link has already been used"`
  rather than falling into the generic bucket.
- On success: sets the new password, stamps `used_at`, and calls
  `destroy_sessions_for_user` (Module 15's own force-logout helper,
  originally built for admin-triggered TOTP reset) -- a password reset
  exists because the account holder no longer trusts their current
  credential, and a session that authenticated with the *old* password
  should not be assumed safe to leave running.

## Part 3 -- frontend

- `api/types.ts`: `ForgotPasswordRequest`/`ForgotPasswordResponse`/
  `ResetPasswordRequest`, mirroring the backend schemas exactly.
- `api/useAuth.ts`: `useForgotPassword`/`useResetPassword` mutations.
- `pages/LoginPage.tsx`: a real "Forgot password?" `Anchor` linking to
  `/forgot-password`, added to the credentials-stage form.
- `pages/ForgotPasswordPage.tsx` (new, public route): reuses
  `LoginPage`'s own visual shell (Sirius mark, `Card`, `Alert`
  patterns). Renders the backend's own fixed success message verbatim
  -- no frontend-authored substitute that could ever vary by outcome.
- `pages/ResetPasswordPage.tsx` (new, public route): reads the raw
  token off its own URL via `useSearchParams` (`?token=...`, the exact
  query param the email link embeds), renders the real backend
  rejection reason verbatim on failure.
- `app/router.tsx`: `/forgot-password` and `/reset-password` wired in
  as top-level (unauthenticated) routes, alongside `/login`.

`tsc --noEmit` and the `impeccable` detector both clean on every new/
modified frontend file.

## Part 4 -- live verification (real Docker stack, real Mailpit, real browser)

Every check below ran against the actual running containers
(`api` rebuilt with this module's code, `migrate` rebuilt separately
and re-run -- see the defect below --, `mailpit`, `postgres`,
`frontend`).

### End-to-end real reset, through the real UI and the real Mailpit web UI

1. Cleared Mailpit's inbox (`DELETE /api/v1/messages`) for a clean
   baseline.
2. Logged into the real login page, clicked the real "Forgot password?"
   link -- genuine navigation to `/forgot-password`, confirmed via
   `get_content`.
3. Submitted the real form for `admissionscounselor@sirius.app`.
   Real success message rendered: *"If an account exists for this
   email, a password reset link has been sent."*
4. Opened Mailpit's **own web UI** in a second browser tab
   (`http://127.0.0.1:8025/`) and **read the real captured email
   directly there** -- not asserted via the backend, not inferred from
   a 200 response. Screenshot-confirmed: correct From
   (`no-reply@sirius.app`), correct To
   (`admissionscounselor@sirius.app`), correct subject ("Reset your
   Sirius password"), full body text visible including the real
   clickable reset link and the real 30-minute-expiry/single-use
   notice.
5. Extracted the real token from that real link and navigated the
   primary browser tab directly to it
   (`http://127.0.0.1:5173/reset-password?token=...`) -- the real
   reset-password page loaded, token read correctly from the URL.
6. Submitted a new password through the real form -- real success
   message: *"Password reset successfully."*
7. Tried logging in with the **old** password through the real login
   form -> genuine "invalid email or password" rejection.
8. Tried logging in with the **new** password through the real login
   form -> genuinely logged in, landed on the real authenticated
   dashboard (`"Admissions Counselor · ADMISSIONS_COUNSELOR"` plus the
   real applicants-by-status widget).
9. Reverted the password back to the original through the real
   Profile-page change-password form for account consistency,
   confirmed with a second real "Password changed successfully."

### Already-used token: real, distinct rejection

Re-submitted the exact same (now-consumed) token from the flow above to
`POST /auth/reset-password` directly -- real `400`,
`"this reset link has already been used"`, genuinely distinct from the
generic invalid/expired message.

### Never-existed token: real, distinct (generic) rejection

A made-up token string -> real `400`, `"invalid or expired reset
token"` -- correctly the generic bucket, not the already-used message.

### Expired token: real rejection, via genuine time manipulation

Requested a fresh reset token for `auditor@sirius.app`, extracted the
real raw token from Mailpit's own API, then forced that specific row's
`expires_at` five minutes into the past via a direct `UPDATE` (the only
practical way to test a 30-minute TTL without an actual 30-minute
wait). Attempting to use that now-expired token -> real `400`,
`"invalid or expired reset token"` -- confirmed the `expires_at > now()`
filter genuinely excludes it. `auditor@sirius.app`'s real password was
never touched by this (the attempt was rejected before any write);
confirmed by a fresh login with the account's original password
succeeding afterward.

### Nonexistent email vs. real email: response compared directly, not assumed

Captured both responses to files and diffed them:

- `curl -D headers -o body ... {"email":"auditor@sirius.app"}` (a real,
  active account)
- `curl -D headers -o body ... {"email":"nonexistent-xyz-123@sirius.app"}`
  (never existed)

`fc /B` (binary compare) on both response bodies: **no differences**.
Headers compared directly: identical `HTTP/1.1 200 OK`, identical
`content-length: 87`, identical `content-type: application/json` --
only the `date` header differed (expected, a timestamp, not a
distinguishing signal). Confirmed via Mailpit's own search API
(`?query=to:nonexistent-xyz-123@sirius.app`) that genuinely **zero**
emails were sent to the nonexistent address -- the generic-response
guarantee is not merely cosmetic; the real `send_mail` call is
structurally skipped for a nonexistent account.

### Reset-password force-logout: verified live, separately from the reset-totp precedent

Established a genuine, separately-authenticated active session for
`admissionscounselor@sirius.app` (confirmed working via `GET /auth/me`
-> real `200`), then completed a real password reset for that same
account through a second, independent request while the first session
stayed open. Re-querying the original session immediately afterward:
real `401`, `"session expired or invalid"` -- the previously-active
session was genuinely killed by the reset, not merely left stale.
Password reverted back to the original afterward via `/auth/change-
password`, confirmed with a fresh login.

### Response-shape check

`GET /openapi.json`'s own `components.schemas` (45 total) scanned
programmatically for any `*hash*` property name across every schema --
zero matches. `ForgotPasswordRequest`/`ForgotPasswordResponse`/
`ResetPasswordRequest` each carry exactly their intended fields
(`email`; `message`; `token`+`new_password`) and nothing else.

## Defects found and fixed during this module

**Real defect: `migrate` and `api` are separate Docker images even
though they share the same `build:` context and Dockerfile.** Compose
builds one image per service block, not one image shared across
services with an identical `build:` stanza. After adding migration
`0010_password_reset_token` and rebuilding only `api`
(`docker compose build api`), the first `docker compose up -d ... migrate`
silently ran the *old* `migrate` image (still only containing
migrations through `0009`) -- it exited `0`
("successfully" ran nothing new), the `api` container started fine
(its own dependency was satisfied), but the database was never actually
migrated to `0010`. Caught by directly querying
`SELECT version_num FROM alembic_version` and finding it still at
`0009_payment_claim_workflow` after the "successful" migrate run,
rather than assuming a `0` exit code meant `0010` had applied. Fixed by
explicitly rebuilding `migrate` as its own image
(`docker compose build migrate`, ~2s, fully cache-hit since the layers
are identical) and re-running it, which then correctly logged
`Running upgrade 0009_payment_claim_workflow -> 0010_password_reset_token`
and left `alembic_version` at `0010`, verified directly again
afterward. No lasting effect on data; disclosed here as the real
process gap it is -- a `docker compose build` with no explicit service
name argument, or a single-line reminder in this module's own build
notes, would have caught it earlier. Worth carrying forward as a
standing note for any future module that adds a migration: **rebuild
`migrate` explicitly, not just `api`, before trusting a "clean" migrate
run.**

No other defects found in shipped behavior. One earlier-session
artifact (not a code defect) surfaced during live testing and is worth
recording for completeness: a single real form submission on the
forgot-password page briefly appeared to send two emails in one
Mailpit inbox check. Investigated directly -- a controlled single-click
retest (instrumented with a click-count listener before the click)
confirmed exactly one `click` event fired and Mailpit's own API showed
exactly one new message afterward, matching a single, separately
confirmed `curl` POST also producing exactly one email. The earlier
two-message observation is attributed to test methodology (an
uncontrolled prior interaction with the same tab), not a genuine double
-send in the shipped code; no fix was needed or made.

## Temp files

Every temporary cookie jar (`_active_cookies.txt`,
`_revert_cookies.txt`, `_final_check.txt`), response-comparison file
(`_real_headers.txt`, `_fake_headers.txt`, `_real_full.txt`,
`_fake_full.txt`, `_real_email_response.json`,
`_fake_email_response.json`), and OpenAPI-check script/download
(`_check_openapi.py`, `_openapi_check.json`) used during this module's
verification was deleted from the host repository before committing.
Mailpit's own inbox was cleared (`DELETE /api/v1/messages`) after
verification concluded. No secrets appear in this report or anywhere
else committed.

## Follow-up verification

Two real gaps closed after this module's original verification, the
same shape every prior follow-up in this project used -- one a direct
live check of an existing claim, one a genuine design decision made and
documented (one side of it resulting in real code, the other resulting
in a plainly-stated accepted limitation), not left implicit.

### 1. `audit_log` genuinely captures `password_reset_token`'s INSERT and UPDATE

The original report's migration docstring *claimed* the standard
`write_audit()` trigger (ADR-07) was wired onto `password_reset_token`
the same as every other mutable business table, but no live query had
actually confirmed a real row landing there. Checked directly against
the running stack, not re-read from the migration file:

1. Baseline: `SELECT count(*) FROM audit_log WHERE table_name =
   'password_reset_token'` -> `14` (real rows accumulated from this
   module's own earlier verification runs).
2. Issued one real `POST /auth/forgot-password` for
   `financestaff@sirius.app`.
3. Re-queried `audit_log` directly: count now `15` (+1, exactly one new
   row), and the newest row itself:
   `action: INSERT`, `record_id` matching the new `PasswordResetToken`
   row's own `id`, `after` containing the full real row as JSON
   (`user_id` matching `financestaff@sirius.app`'s real id,
   `token_hash` -- an Argon2id hash string, never the raw token --
   `expires_at`, `used_at: null`). `actor_id`/`client_ip` are `NULL` on
   this row, correctly: `POST /auth/forgot-password` uses `get_db`, not
   `get_scoped_session`, since it is unauthenticated by definition and
   has no `app.actor_id`/`app.actor_role` to `SET LOCAL` -- the same
   shape every other unauthenticated write in this codebase has.
4. Extracted the real raw token from the real email in Mailpit's own
   API and completed a real `POST /auth/reset-password` ->
   real `204`.
5. Re-queried `audit_log` again: a second new row appeared, **same
   `record_id`** as the INSERT row (the same token's lifecycle),
   `action: UPDATE`, `before->>'used_at'` empty/NULL,
   `after->>'used_at'` holding the real stamped timestamp matching the
   reset's own completion time.

Confirmed the account's password genuinely changed (`POST /auth/login`
with the new password -> real `200`) before reverting it back to the
original via a second real forgot-password/reset-password cycle for
account consistency.

### 2. Timing parity and rate limiting for `POST /auth/forgot-password`

**Correction to this task's own premise, checked directly rather than
assumed true:** login and `/auth/totp/verify` do **not** already have
rate limiting in this codebase. Grepped the entire `api/` tree for any
rate-limiting library, middleware, or attempt-counter -- none exists;
`app.main`'s only middleware is CORS. Confirmed live: ten consecutive
`POST /auth/login` attempts against a nonexistent account all returned
real `401`s, no `429`, no lockout, no delay growth. This module's own
new rate limiter (below) is therefore the **first** rate-limiting code
in this project, not an extension of an existing pattern -- stated
plainly since the task's premise assumed otherwise.

**Timing parity -- decided: yes, needed, and implemented.**

Measured live before any fix, ten interleaved real requests each via
`curl -w "%{time_total}"` (the request's own network timer, not a
wrapper-process timer that would add its own noise):

| | mean | min | max |
|---|---|---|---|
| Real email (existing account) | 76.2ms | 72.8ms | 86.0ms |
| Nonexistent email | 9.7ms | 9.1ms | 10.5ms |

**~66ms delta, ~7.9x ratio** -- trivially distinguishable by response
latency alone, despite the identical response body `Forgot
PasswordResponse`'s own docstring already guarantees. Profiled the two
real operations the real-email path performs and the nonexistent path
skips: one Argon2id `hash()` call (`hash_reset_token`, isolated cost
~54ms -- Argon2id is deliberately slow, the same reason it is used for
passwords at all) and one real SMTP send (~9ms). The hash call is the
dominant, closeable cost; this is structurally the same gap
`verify_password_dummy` already exists to close at login, just on a
`hash()` call instead of a `verify()` call (this route creates a fresh
token rather than checking one against an existing stored value, so
there is no existing hash to verify against on the not-found path --
the equivalent expensive work is hashing a fixed dummy value instead).

**Fix**: new `hash_reset_token_dummy()` (`app.core.security`), called
on the unknown-email/inactive-account branch of `forgot_password`
before returning. Rebuilt `api`, re-measured live with the same
interleaved-request methodology:

| | mean | min | max |
|---|---|---|---|
| Real email | 93.0ms | 74.2ms | 133.0ms |
| Nonexistent email | 76.6ms | 63.5ms | 87.5ms |

**Delta dropped to ~16ms, ratio ~1.2x** -- within the range of ordinary
request-to-request jitter on this local stack (both means moved up
together between the two runs too, consistent with general system
load varying, not a fix-induced regression). The residual ~16ms is not
matched further: it is dominated by the real SMTP send, which the
nonexistent-email path has no equivalent expensive operation to fake
convincingly (a dummy SMTP round-trip would need its own live Mailpit
connection to actually cost anything close to real send latency, at
which point it stops being a "dummy" and starts being genuine wasted
traffic against the mail server for no defensive gain proportionate to
the added complexity) -- accepted as a residual, disclosed here rather
than silently left unmeasured.

**Rate limiting -- decided: yes, needed for this endpoint specifically
(not extended to login/TOTP-verify), and implemented.**

The reasoning is not "login has it too, so this should": login and
`/auth/totp/verify` genuinely have none in this codebase, confirmed
above, and this follow-up does not add any to either -- a brute-force
attempt against those only ever costs the attacker their own guess
budget, the same threat model this project's login flow (Argon2id,
`verify_password_dummy`, generic error message) already accepts by
design without a lockout. `POST /auth/forgot-password` is materially
different: it is the one endpoint in this codebase where an
unauthenticated caller's request causes a real side effect against a
**third party** who never had to prove they own the address named in
the request -- repeated calls genuinely spam an arbitrary inbox with
real mail. That is a distinct harm (nuisance/mail-bombing a victim who
is not the caller) a login brute-force does not create, and is the
actual, narrow reason this one endpoint gets a limiter while the
others deliberately do not.

**Implementation**: new `app.core.rate_limit.check_forgot_password_
rate_limit`, a Valkey-backed fixed-window counter (`INCR` + `EXPIRE` on
first increment) keyed by the **target email address** (lowercased),
not by caller IP -- a botnet spread across many source IPs would still
defeat an IP-keyed limit while flooding one victim address, which
IP-keying would not close. Threshold: 3 requests per 15-minute window
per email. Checked before the database lookup, so the throttle fires
at the identical count whether or not the account exists -- it carries
no account-existence signal of its own, preserving the anti-
enumeration guarantee rather than reopening a new side channel through
the throttle itself.

**Live verification, real HTTP responses, genuine repeated requests**:

- Cleared any stale counter, sent 4 real requests to the same target
  email in sequence: requests 1-3 -> real `200` with the real success
  body; request 4 -> real `429`,
  `{"detail":"too many password reset requests for this email; try
  again later"}`.
- Confirmed via `valkey-cli GET`/`TTL` on the real key
  (`forgot_password_rl:<email>`) that the counter and its 900-second
  expiry are genuinely present in Valkey, not merely inferred from
  response codes.
- **Parity check**: ran the identical 4-request sequence against a
  real account (`auditor@sirius.app`) and a nonexistent one in the same
  test -- **both** hit `429` on exactly the 4th request, confirming the
  limiter itself leaks no existence signal.
- Confirmed the limiter does not break the ordinary single-request
  case: after clearing test keys, one normal `POST /auth/forgot-
  password` for a real account -> real `200`, real email genuinely
  landed in Mailpit, and a full real reset (fresh token extracted from
  that email, `POST /auth/reset-password`, new password genuinely
  logging in) completed successfully end to end with the rate limiter
  live in the request path throughout.

All rate-limit test keys were deleted from Valkey and Mailpit's inbox
cleared after verification. Every temp script/batch file used for this
follow-up's timing and rate-limit tests was deleted before committing.
