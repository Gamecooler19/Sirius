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
