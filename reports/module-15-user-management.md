# Module 15: Self-service profile management and SUPER_ADMIN user administration

## Scope

Two related but distinct pieces:

1. **Self-service profile management** (every role): view your own
   identity (email, role, 2FA enrollment status) and change your own
   password, with the current password verified server-side before the
   change is accepted.
2. **SUPER_ADMIN-only user administration**: list all accounts, create a
   new account (any role, including the three mandatory-TOTP roles),
   change an existing account's role or active status, and reset a
   mandatory-TOTP account's TOTP enrollment for the lost-device recovery
   case -- with a self-lockout guard so a SUPER_ADMIN cannot strip their
   own access through this endpoint.

Per this project's ADR-03 precedent (`role`/`user` are the identity axis
and structurally cannot be RLS-scoped, since login must look up a user by
email before any session or `app.actor_role` exists), all of this is
RBAC-only. No RLS policy is added, changed, or removed by this module.

## Part 1 -- backend

### `POST /auth/change-password` (`api/app/routers/auth.py`)

- New `ChangePasswordRequest` schema (`api/app/schemas/auth.py`):
  `current_password` + `new_password` only. **No `user_id` field at
  all** -- the endpoint sources the target account exclusively from the
  authenticated session (`get_current_user`, not `get_current_session`,
  since this is a genuine credential mutation and should require a
  fully-verified session, not a TOTP-pending one). This mirrors the
  `submitted_by` pattern already established for payment claims: never
  trust an identity field in the request body when the session already
  carries it.
- Current-password verification reuses `verify_password` -- the exact
  same Argon2id path `/auth/login` itself uses. A wrong current password
  returns the real, specific error text `"current password is
  incorrect"` (not `/auth/login`'s generic "invalid email or password",
  since the anti-enumeration reasoning behind that generic message does
  not apply to an already-authenticated, self-service action).
- Success returns `204`.

### `/users*` router (new files: `api/app/routers/users.py`,
`api/app/schemas/users.py`)

| Route | Behavior |
|---|---|
| `GET /users` | Paginated (`limit`/`offset`, same shape as every other list endpoint in this codebase), all six roles visible, hand-declared `UserSummary` response model that never leaks `password_hash`/`totp_secret_encrypted` |
| `POST /users` | Creates a new account. Always `totp_enabled=False` by construction -- see below for why this is load-bearing |
| `PATCH /users/{id}` | Changes `role_code` and/or `is_active`. Self-lockout guard rejects a SUPER_ADMIN changing their own role away from SUPER_ADMIN, or deactivating their own account, with `422` -- checked via `model_fields_set` before any write, so an update that only touches one field can't be misread as silently touching the other |
| `POST /users/{id}/reset-totp` | Clears `totp_secret_encrypted` + `totp_enabled`, forcing genuine re-enrollment (not re-verification) on the account's next login |

All four routes are gated by `require_role_session(RoleCode.SUPER_ADMIN)`
only -- no new RLS code, reusing ADR-03's own precedent directly.

**Why `POST /users` always sets `totp_enabled=False`:** this is not
incidental, it's the entire mechanism by which a freshly admin-created
mandatory-TOTP account (SUPER_ADMIN, FINANCE_STAFF, FINANCE_MANAGER)
goes through the real, existing enrollment flow
(`/auth/totp/enroll/start` + `/confirm`) on its very first login, with
zero new authentication code written by this module. `POST /auth/login`
already branches on `totp_enabled`; a new account created here is
indistinguishable, from that endpoint's point of view, from a role
enrolled by hand in Module 11.

**Existing `user_write_audit` trigger** (from Module 01) already fires on
INSERT/UPDATE/DELETE against the `user` table -- confirmed still present,
zero new trigger code needed for this module's writes to be audited.

Router registered in `api/app/main.py`.

## Part 2 -- frontend

- `api/types.ts`: `ChangePasswordRequest`, `UserSummary`,
  `UserListResponse`, `UserCreateRequest`, `UserUpdateRequest`.
- `api/client.ts`: added a `patch` method (list/create already had
  `get`/`post`).
- `api/useAuth.ts`: `useChangePassword` hook.
- `users/useUsers.ts` (new): list/create/update/reset-TOTP hooks, all
  invalidating a shared `usersKeys.all` query key so the table reflects
  writes immediately.
- `auth/roles.ts`: `USERS_ROLES` (SUPER_ADMIN only) and
  `MANDATORY_TOTP_ROLES` (SUPER_ADMIN, FINANCE_STAFF, FINANCE_MANAGER)
  constants.
- `pages/ProfilePage.tsx` (new, all roles): identity display
  (email/role/2FA badge) + change-password form, reusing
  `LoginPage`'s own `PasswordInput`/`Alert` patterns rather than
  reinventing them.
- `users/UsersPage.tsx` (new, SUPER_ADMIN-only): paginated table
  (`Table.ScrollContainer`, `EmptyState` for the zero-rows case),
  create-user modal, per-row activate/deactivate button (disabled for
  the signed-in admin's own active row -- a UX mirror of the backend
  guard, not a substitute for it), per-row "Reset TOTP" button shown only
  for `MANDATORY_TOTP_ROLES`.
- `app/router.tsx`: `/profile`, `/users` routes wired in.
- `app/AppShellLayout.tsx`: "Profile" nav link visible to all roles,
  "Users" nav link gated by `USERS_ROLES` (absent entirely for
  non-SUPER_ADMIN roles, not merely disabled).

`tsc --noEmit` and `impeccable detect` both clean at time of writing.

## Part 3 -- live verification (real Docker stack, real browser UI, real DB)

Every check below was performed against the actual running containers
(`api`, `frontend`, `postgres`) -- curl for backend-only checks, the real
browser UI (clicks, forms, real login/logout cycles) for the checks that
specifically needed to prove the UI path, not just the API.

### Change-password (backend, curl)

- Wrong current password on a real account -> `400`, body genuinely
  contains `"current password is incorrect"` (not a generic message).
- Correct current password -> `204`.
- Immediately re-logged in with the *old* password -> genuine `401`.
- Re-logged in with the *new* password -> genuine `200`.
- Reverted the test account's password back afterward for session
  consistency.

### Change-password (real browser UI)

- Logged in as `admissionscounselor@sirius.app` through the actual login
  form, navigated to `/profile`. Confirmed correct identity display
  (email, role, "NOT ENROLLED" 2FA badge) and correct nav (Profile
  visible; Users correctly absent for this non-admin role).
- Filled and submitted the real change-password form
  (`AdmissionsCounselor123!` -> `NewCounselor789!`) -- real success
  alert.
- Logged out, tried the *old* password through the real login form ->
  genuine "invalid email or password" rejection, screenshot-confirmed.
- Tried the *new* password through the real login form -> genuinely
  logged in, landed on the authenticated dashboard
  (`document` content confirmed: "Admissions Counselor ·
  ADMISSIONS_COUNSELOR" plus the real applicants-by-status widget).
- Reverted the password back to the original through the real UI
  (Profile page's own change-password form) for account consistency,
  confirmed with a second real "Password changed successfully" response.

### Non-SUPER_ADMIN nav and route access (real browser UI)

- Confirmed no "Users" link exists in `admissionscounselor@sirius.app`'s
  nav (`Home / Applicants / Profile` only).
- Navigated directly to `/users` by URL as this role anyway (the route
  itself has no client-side role gate -- only the nav link is
  conditionally rendered). The page rendered and the real backend `403`
  ("insufficient role for this action") surfaced correctly as the page's
  error state, screenshot-confirmed. This is the intended defense in
  depth: even a user who bookmarks or guesses the URL gets a real,
  server-enforced rejection, not a client-side illusion of one.

### GET/POST/PATCH `/users`, reset-TOTP (backend, curl)

- `GET /users` as SUPER_ADMIN -> all 6 seeded users, no sensitive fields
  on the wire (checked directly).
- `GET /users` as AUDITOR (non-admin) -> genuine `403`.
- `POST /users` created a real `ADMISSIONS_COUNSELOR`
  (`newcounselor@sirius.app`) -- immediately logged in as that account
  successfully.
- Self-lockout guard: SUPER_ADMIN attempting to deactivate their own
  account -> real `422`; attempting to change their own role away ->
  real `422`. A legitimate `PATCH` on a *different* account (deactivate
  -> login correctly rejected `401` -> reactivate -> login worked again)
  succeeded normally, proving the guard is scoped to "your own account,"
  not "any SUPER_ADMIN account."
- `POST /users/{id}/reset-totp` on `financestaff@sirius.app` (a real
  mandatory-TOTP account) cleared TOTP; confirmed the next login response
  showed `totp_enrollment_required: true` (re-enters enrollment, not
  verify) -- then genuinely re-enrolled that account with a fresh secret
  so it was left in working state.
- OpenAPI schema checked for zero `password_hash`/`totp_secret_encrypted`
  leakage across every new response model.

### SUPER_ADMIN user administration (real browser UI)

Logged in as `superadmin@sirius.app` through the real login form,
including its real mandatory-TOTP verify step (a live code computed from
the account's own enrolled secret, entered into the real 6-box PIN
input).

- **Users table renders correctly**: all 8 accounts (6 seeded + 2 created
  earlier this module) with correct email/name/role/status/2FA columns.
  SUPER_ADMIN's own row visibly shows a **disabled** "Deactivate" button
  (confirmed at the DOM level: `button.disabled === true`) -- the UI
  mirror of the backend self-lockout guard. "Reset TOTP" only appears for
  `MANDATORY_TOTP_ROLES` rows, matching the frontend constant.
- **Create user through the real form**: opened the "Create user" modal,
  filled email/full name/initial password/role
  (`financeviewer@sirius.app`, FINANCE_STAFF) through the actual form
  fields (confirmed each field's live DOM value immediately before
  submit), submitted. The new row appeared in the table live, no page
  reload. Logged in as this brand-new account through the real login form
  -- it genuinely required TOTP enrollment (QR code + ten backup codes
  rendered), the real end-to-end proof that `POST /users` correctly
  routes a mandatory-TOTP role's new account through actual enrollment,
  not a bypass.
- **Reset TOTP through the real button**: clicked "Reset TOTP" on
  `financestaff@sirius.app`'s row (an already-enrolled account). Its 2FA
  badge flipped from "ENROLLED" to "NOT ENROLLED" live in the table.
  Logged out, logged back in as that account through the real login form
  with its real password -- it genuinely re-entered the **enrollment**
  flow (fresh QR code, fresh backup codes), not the verify flow, proving
  the reset genuinely took effect and the next login correctly
  distinguishes "never enrolled" from "still enrolled." Re-enrolled the
  account with a fresh secret via curl afterward (confirming `204`) so it
  was left in working state.
- **Deactivate/reactivate through the real buttons**: clicked
  "Deactivate" on `newcounselor@sirius.app`'s row -- status flipped to
  `INACTIVE` live, button label flipped to "Activate." Confirmed via curl
  that a login attempt against this now-inactive account gets a genuine
  `401`. Clicked "Activate" on the same row -- status flipped back to
  `ACTIVE`, button label back to "Deactivate."

## Defects found and fixed during this module

None found in the shipped behavior. One cosmetic non-issue was
investigated and ruled out: immediately after opening the create-user
modal, a `computed opacity: 0` briefly appeared on
`.mantine-Modal-content` in one DOM inspection (traced to Mantine's own
enter-transition inline style, not a class our code controls, and not a
functional block -- the form's fields accepted and retained values
correctly throughout, and the create action itself succeeded and was
verified via the resulting table row and a real subsequent login as the
new account). No code change was made for this; it did not affect any
outcome that was checked.

## Temp files

All temporary cookie jars (`_admin_cookies.txt`, `_fs2_cookies.txt`,
`_fv_cookies.txt`) and temp TOTP-code generator scripts
(`_totp_gen.py`, `_totp_gen2.py`) used during verification were deleted
from the host repository before committing. No TOTP secret or backup
code appears in this report or anywhere else committed -- every raw
secret generated this module was printed to chat only.
