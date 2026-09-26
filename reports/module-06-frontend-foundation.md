# Module 06: Frontend Foundation — completion report

## Scope

Scaffold `frontend/` alongside `api/` and `deploy/` in the same repo: Vite +
React 19 + TypeScript, Mantine as the sole component library, Tailwind CSS
with Preflight disabled so it doesn't fight Mantine's own base styles,
TanStack Query v5 for all server state, and Phosphor Icons (Light weight) —
this project's standing frontend stack default, no substitutions. Wire it
to the real backend on `127.0.0.1:38210` with `credentials: "include"` on
every request (the httpOnly session cookie is the entire auth story, not a
bearer token), and add the frontend's dev origin to the backend's
`CORS_ORIGINS` rather than routing around CORS with a dev-server proxy.
Build the login flow end to end against the real `/auth/*` endpoints:
email/password → branch on `totp_required`/`totp_enrollment_required` → a
real QR code + ten backup codes for first-time mandatory-TOTP enrollment, a
six-digit verify step for already-enrolled mandatory-TOTP users, plain
success for roles where TOTP isn't mandatory. A `useMe()` TanStack Query
hook wrapping `GET /auth/me`, an authenticated app shell (nav + logout
wired to the real `POST /auth/logout`) that only renders after that query
resolves, and route guarding that redirects to `/login` on a 401. Nav items
gated by the six real roles, matching Modules 03-05's own server-side role
gates — a UI convenience, not a security boundary. Every data page
(applicant list, status transitions, payment workflow, reconciliation)
left as an empty placeholder route for later modules.

## What was built

### Stack (`frontend/`)

Scaffolded with `npm create vite@latest -- --template react-ts` (Vite
8.3, React 19.3, TypeScript ~6.0), then added: `@mantine/core`,
`@mantine/hooks`, `@mantine/form` (9.6.2, peer-compatible with React
`^19.2.0`), `@tanstack/react-query` 5.104, `react-router-dom` 7.18,
`@phosphor-icons/react` 2.1.10 (used exclusively at `weight="light"` per
this project's standing default), `qrcode.react` 4.2 (`QRCodeSVG`, for
rendering the real `otpauth://` provisioning URI as an actual scannable
code, not a placeholder image), and Tailwind CSS v4 (`tailwindcss`,
`@tailwindcss/postcss`). `src/index.css` imports only
`tailwindcss/theme.css` and `tailwindcss/utilities.css` layers —
deliberately **not** `tailwindcss/preflight.css` — so Tailwind's own base
reset never fights Mantine's (`@mantine/core/styles.css`, imported once in
`main.tsx`). `npm run build` (`tsc -b && vite build`) and `npx tsc -b`
both pass clean with zero errors.

### API wiring (`src/api/`)

- `client.ts` — a thin `fetch` wrapper. Every call sets `credentials:
  "include"` unconditionally; there is no code path that omits it. `ApiError`
  carries the real HTTP status and extracts FastAPI's own `{"detail": "..."}`
  shape verbatim, so the UI surfaces the backend's exact wording
  ("invalid email or password", "invalid TOTP code") rather than a generic
  frontend message.
- `types.ts` — request/response shapes copied field-for-field from
  `api/app/schemas/auth.py` (`LoginResponse.totp_required`/
  `totp_enrollment_required`, `TotpEnrollStartResponse.provisioning_uri`/
  `backup_codes`, `MeResponse`, etc.) — not a reshaped superset.
- `useMe.ts` — `useQuery(["auth", "me"], () => api.get("/auth/me"))`,
  `retry: false` (a 401 means "no session," not a transient failure worth
  retrying three times). `useInvalidateMe()` is called by every mutation
  that changes session state (login, TOTP enroll-confirm, TOTP verify,
  logout) so the shell/guard re-fetch against the new session rather than
  serving stale cached identity.
- `useAuth.ts` — `useMutation` wrappers for
  `login`/`logout`/`totp/enroll/start`/`totp/enroll/confirm`/`totp/verify`/
  `totp/verify-backup-code`, each hitting the real endpoint path.

### Login flow (`src/pages/LoginPage.tsx`)

One component, three stages, driven exactly by `LoginResponse`'s own two
flags — not a client-side guess:

1. `totp_required: false` → `navigate("/")` immediately.
2. `totp_required: true, totp_enrollment_required: true` → calls
   `/auth/totp/enroll/start` itself (no separate button), renders the real
   `provisioning_uri` as a `QRCodeSVG` (an actual scannable QR of the real
   `otpauth://...` URI, not a static image) and all ten real backup codes
   in a "shown only once" callout with a copy-all button, then a
   `PinInput` + "Confirm enrollment" that calls
   `/auth/totp/enroll/confirm`.
3. `totp_required: true, totp_enrollment_required: false` → a `PinInput` +
   "Verify" calling `/auth/totp/verify`.

Errors from any stage populate one `Alert` (Mantine, `WarningCircle`
Phosphor icon) with the caught `ApiError`'s own `.message` — the real
backend text, not a rewritten one.

### App shell and routing (`src/app/`, `src/auth/`)

- `AppShellLayout.tsx` — Mantine `AppShell` with header (app name, current
  user's `full_name`/`role_code`, a "Logout" button calling the real
  `useLogout()` mutation then navigating to `/login`) and a navbar. Only
  ever reached through `RequireAuth`, and additionally guards on
  `meQuery.data` being present before rendering its own content.
- `RequireAuth.tsx` — the one route guard. Renders a `Loader` while
  `useMe()` is in flight, `<Navigate to="/login" />` if it errors (a real
  401 from the backend), children otherwise. No independent "am I logged
  in" client state exists anywhere else.
- `router.tsx` — `/login` standalone; `/`, `/applicants`, `/finance` all
  nested under one `RequireAuth`-wrapped `AppShellLayout` route.
- `auth/roles.ts` — `APPLICANTS_ROLES` (`SUPER_ADMIN`,
  `ADMISSIONS_MANAGER`, `ADMISSIONS_COUNSELOR`) and `FINANCE_ROLES`
  (`SUPER_ADMIN`, `FINANCE_STAFF`, `FINANCE_MANAGER`, `AUDITOR`), copied
  from `app.routers.status`'s and `app.routers.payment_claim`/
  `reconciliation`'s own role allowlists respectively — not invented
  independently. `hasRole()` is a plain array `.includes()`, nothing
  resembling RBAC enforcement. The module docstring is explicit that this
  is UI convenience only; the backend remains the actual enforcement
  point, and every existing role gate (`require_role`/
  `require_role_session`) is untouched.

### Placeholder pages (`src/pages/`)

`HomePage`, `ApplicantsPage`, `FinancePage` — each a `Stack`/`Title`/`Text`
naming what arrives in a later module. No data fetching, no forms, no
tables.

### CORS (`deploy/.env`)

`CORS_ORIGINS` already contained both `http://localhost:5173` and
`http://127.0.0.1:5173` from Module 01's own default — no backend change
was needed this module. `vite.config.ts` pins `port: 5173, strictPort:
true` so the dev server's own origin matches those entries exactly (see
Defect 1 below for why `host: true` was also required).

## Verification against the live stack

Verified against the actual running Docker Compose stack
(`sirius-api-1` on `127.0.0.1:38210`, already up) and a real
Firefox browser session driving the actual Vite dev server at
`http://127.0.0.1:5173` — not a mocked backend, not `jsdom`. Three fresh
test users were inserted directly into the live `user` table for this
verification (argon2id-hashed via the running API container's own
`app.core.security.hash_password`, so the hashes are byte-for-byte what
the real login endpoint would produce): `frontend-manager@...`
(`ADMISSIONS_MANAGER`, non-mandatory TOTP), `frontend-superadmin@...`
(`SUPER_ADMIN`, mandatory TOTP, unenrolled), `frontend-auditor@...`
(`AUDITOR`, non-mandatory TOTP) — left in place afterward, consistent with
this project's existing precedent of `m3-`/`m4-`-prefixed test fixtures
from prior modules' own live verification still present in the database.

- **Non-mandatory-TOTP role straight to the shell.** Filled the real login
  form for `frontend-manager@...` / a real password, submitted, landed on
  `/` with the full authenticated shell: header showing "Frontend Test
  Manager · ADMISSIONS_MANAGER", a working Logout button, and a navbar
  showing exactly **Home** and **Applicants** — no Finance link, matching
  `ADMISSIONS_MANAGER` being outside `FINANCE_ROLES`.
- **Mandatory-TOTP enrollment with a real generated code.** Logged in as
  `frontend-superadmin@...` (unenrolled `SUPER_ADMIN`): the app called
  `/auth/totp/enroll/start` itself and rendered a real `QRCodeSVG` of the
  actual returned `otpauth://` URI plus all ten real backup codes. The
  provisioned secret was decrypted directly from Postgres
  (`app.core.crypto.decrypt_totp_secret`, run inside the live `api`
  container against the just-created `user.totp_secret_encrypted`), fed to
  `pyotp.TOTP(secret).now()` to produce a real live 6-digit code, typed
  into the app's `PinInput`, and "Confirm enrollment" clicked — the app
  called the real `/auth/totp/enroll/confirm`, which returned 204, and the
  app navigated straight to the authenticated shell showing **Home**,
  **Applicants**, and **Finance** (all three, correctly, since
  `SUPER_ADMIN` is in both role sets). A **second, independent** run
  logged in again after re-provisioning a fresh secret, entered a fresh
  live code, and reached the shell the same way — not a one-off.
- **Already-enrolled mandatory-TOTP role, verify step.** Logged out, back
  in as the now-enrolled `frontend-superadmin@...`: the app skipped
  enrollment and showed the six-digit "Verify" `PinInput` directly
  (`totp_enrollment_required: false` branch). A wrong code (`000000`)
  produced the real backend text **"invalid TOTP code"** in the error
  `Alert`; a fresh correct live code (regenerated via the same decrypt +
  `pyotp` path) verified successfully and reached the shell.
- **Wrong password, real backend error text.** Submitted
  `frontend-manager@...` with a deliberately wrong password: the login
  form showed **"invalid email or password"** — the exact FastAPI
  `detail` string from `app.routers.auth.login`, not a rewritten frontend
  message.
- **Logout actually clears the session; refresh redirects to login.**
  Clicked the real Logout button; the app navigated to `/login`. Called
  `GET /auth/me` directly against the live backend with the browser's
  existing credentials afterward — **401 `{"detail": "not authenticated"}`**,
  confirming the Valkey-backed session was genuinely destroyed
  server-side, not just forgotten client-side. Then navigated directly to
  `/` (simulating a refreshed tab on a previously-authenticated URL):
  `RequireAuth`'s `useMe()` call 401'd and the app redirected to `/login`
  — the exact "refresh redirects back to login" behavior required.
- **Nav role-gating across all three relevant role shapes**, each
  confirmed live in the running shell (not just read from source):
  `ADMISSIONS_MANAGER` → Home + Applicants only; `AUDITOR` → Home +
  Finance only; `ADMISSIONS_COUNSELOR` (the pre-existing seeded
  `m3-counselor@...` fixture, password reset for this test) → Home +
  Applicants only; `SUPER_ADMIN` → all three (Home, Applicants, Finance).
  No role outside `APPLICANTS_ROLES`/`FINANCE_ROLES` was ever shown a link
  it isn't in the allowlist for.
- **Placeholder routes.** `/applicants` and `/finance` both render their
  named placeholder text ("Applicant list and status transitions arrive in
  a later module." / "Payment claims and reconciliation arrive in a later
  module.") under the full authenticated shell chrome — confirmed by
  direct navigation while authenticated as `SUPER_ADMIN`.
- **Build and typecheck.** `npx tsc -b` and `npm run build` both pass with
  zero errors against the final source tree (confirmed after removing all
  temporary debug instrumentation added mid-verification — see Defect 2).

## Real defects found and fixed during this verification

**Defect 1 — the session cookie never reached the backend from
`localhost:5173`, even though CORS allowed the origin.** The first attempt
opened the frontend at `http://localhost:5173` (Vite's own default
`server.host`, which resolves to `localhost` only) against the backend at
`http://127.0.0.1:38210`. Login returned a real `200` with
`Set-Cookie: sirius_session=...; SameSite=Strict`, and the
browser's own network layer confirmed the CORS preflight/response headers
were correct (`access-control-allow-origin: http://localhost:5173`,
`access-control-allow-credentials: true`) — but the very next
`GET /auth/me` came back `401 {"detail": "not authenticated"}`, and
`document.cookie` (run in-page) showed no cookie stored at all for the API
origin. Root cause: `localhost` and `127.0.0.1` are **different sites**
under the browser's `SameSite` algorithm (distinct registrable-domain-ish
identities for this purpose) even though CORS treats them as two
explicitly-allowed-but-distinct origins — a `SameSite=Strict` cookie set
by a response from `127.0.0.1:38210` is never attached to a subsequent
request whose page origin is `localhost:5173`, regardless of what CORS
permits. This is a real, load-bearing interaction between
`SameSite=Strict` (a deliberate, documented Module 01 choice — see that
module's own `app/core/cookies.py` docstring) and *which* dev origin the
frontend actually runs on, not a CORS misconfiguration and not fixable by
changing `CORS_ORIGINS` — `CORS_ORIGINS` already listed both
`http://localhost:5173` and `http://127.0.0.1:5173`, and the failure
happened only for the `localhost` one. **Fix:** added `host: true` to
`vite.config.ts`'s `server` block so the dev server actually binds and
serves on `127.0.0.1` (not just `localhost`), and standardized on
`http://127.0.0.1:5173` as the frontend's real dev origin for this
project — matching the origin the backend's own cookie-issuing host
(`127.0.0.1:38210`) shares a site identity with. Re-verified live:
identical login flow from `http://127.0.0.1:5173` stored the cookie
correctly, and every subsequent `/auth/me` call succeeded. This is worth
flagging forward: any future real deployment must ensure the frontend and
backend are served from hostnames that are same-site with each other (or
relax `SameSite` deliberately with a documented reason), not merely
CORS-compatible.

**Defect 2 — none found in the actual enrollment/verify navigation logic;
an initial false alarm during verification was investigator timing, not a
code defect, and is recorded here for completeness.** Early in
verification, clicking "Confirm enrollment" and "Verify" appeared to leave
the app stuck on `/login` when checked via an immediate follow-up
`get_content` call, while a direct `GET /auth/me` in the same moment
showed the session had, in fact, already become fully authenticated
server-side. This looked at first like a `navigate("/")` call being lost
after a successful mutation. Root-caused by instrumenting
`handleEnrollConfirm`/`handleVerify` with timestamped markers around the
`await mutateAsync(...)` and the subsequent `navigate(...)` call: repeated
live runs showed `mutateAsync` resolving and `navigate("/", { replace:
true })` executing within ~30-40ms of the click, and the shell rendering
correctly every time once the check allowed that time to elapse. The
one-off "stuck" appearances were this investigation's own tool-call
sequencing (checking page state in a separate round-trip issued before
the in-page async chain had finished, and once, a stale bundle reload
resetting mid-flow selectors), not a defect in
`LoginPage.tsx`'s control flow. The temporary debug instrumentation was
removed before the final build/typecheck pass above; no source change was
needed to fix this because there was nothing to fix.

## Explicitly out of scope (per module boundary)

Applicant list, status-transition UI, payment-claim submission/
confirmation UI, and the reconciliation view are all untouched empty
placeholder routes, per this module's own instruction — later modules'
scope. No RBAC logic was duplicated client-side beyond the nav-visibility
booleans in `auth/roles.ts`, which the module docstring itself flags as
non-authoritative; every actual access decision still happens exclusively
in the FastAPI backend (`require_role`/`require_role_session`/RLS),
unchanged by this module.
