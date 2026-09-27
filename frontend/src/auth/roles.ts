/** Nav-visibility role gates. This is a UI convenience only -- deciding
 * what to render -- not a security boundary; the backend's own
 * `require_role`/`require_role_session` dependencies (Modules 03-05) are
 * the actual enforcement point regardless of what this file says. Every
 * set below is copied from that backend source, not invented here:
 *
 * - Applicants: `app.routers.status` (`SUPER_ADMIN`, `ADMISSIONS_MANAGER`,
 *   `ADMISSIONS_COUNSELOR` may drive transitions; `applicants_read` itself
 *   is open to all six roles with RLS doing the narrowing, but the nav
 *   entry point is gated to the roles that actually own this workflow).
 * - Finance: `app.routers.payment_claim._LIST_ROLES` and
 *   `app.routers.reconciliation._ROLES` (`SUPER_ADMIN`, `FINANCE_STAFF`,
 *   `FINANCE_MANAGER`, `AUDITOR`).
 * - Import upload vs. import history: a genuine asymmetry, not one
 *   uniform gate -- `app.routers.import_.import_applicants`
 *   (`SUPER_ADMIN`/`ADMISSIONS_MANAGER` only) is narrower than
 *   `app.routers.import_batches_read.list_import_batches`'s own
 *   `_LIST_ROLES` (`SUPER_ADMIN`/`ADMISSIONS_MANAGER`/`AUDITOR`) -- an
 *   `AUDITOR` can see the batch history but has no legitimate reason to
 *   run an import themselves.
 * - Payment-claim submit vs. resolve: another genuine asymmetry, and a
 *   sharper one than import's -- `app.routers.payment_claim`'s
 *   `submit_payment_claim` allows `SUPER_ADMIN`/`FINANCE_STAFF`/
 *   `FINANCE_MANAGER`, but `confirm_payment_claim`/`reject_payment_claim`
 *   allow only `SUPER_ADMIN`/`FINANCE_MANAGER` -- `FINANCE_STAFF` may
 *   originate a claim but can never resolve *any* claim, including one
 *   submitted by a different staff member. This is the real
 *   maker-checker separation the backend enforces (plus an
 *   application-layer same-user check on top, for the case where a
 *   `FINANCE_MANAGER` tries to resolve their own submission); the
 *   frontend's role sets below reflect that split exactly, not a milder
 *   version of it.
 */

import type { RoleCode } from "../api/types";

export const APPLICANTS_ROLES: RoleCode[] = [
  "SUPER_ADMIN",
  "ADMISSIONS_MANAGER",
  "ADMISSIONS_COUNSELOR",
];

export const FINANCE_ROLES: RoleCode[] = [
  "SUPER_ADMIN",
  "FINANCE_STAFF",
  "FINANCE_MANAGER",
  "AUDITOR",
];

export const IMPORT_UPLOAD_ROLES: RoleCode[] = ["SUPER_ADMIN", "ADMISSIONS_MANAGER"];

export const IMPORT_HISTORY_ROLES: RoleCode[] = [
  "SUPER_ADMIN",
  "ADMISSIONS_MANAGER",
  "AUDITOR",
];

/** `app.routers.payment_claim.submit_payment_claim`'s own
 * `require_role_session` allowlist.
 */
export const PAYMENT_SUBMIT_ROLES: RoleCode[] = [
  "SUPER_ADMIN",
  "FINANCE_STAFF",
  "FINANCE_MANAGER",
];

/** `app.routers.payment_claim.confirm_payment_claim`/`reject_payment_claim`'s
 * own `require_role_session` allowlist -- deliberately excludes
 * `FINANCE_STAFF`, matching the backend's real maker-checker asymmetry.
 */
export const PAYMENT_RESOLVE_ROLES: RoleCode[] = ["SUPER_ADMIN", "FINANCE_MANAGER"];

/** `app.routers.reconciliation._ROLES`'s own `require_role_session`
 * allowlist, copied verbatim -- identical membership to `FINANCE_ROLES`
 * today (both mirror the same underlying `finance_record`/`payment_claim`
 * RLS allowlist per that router's own docstring), but named as its own
 * constant rather than reusing `FINANCE_ROLES` directly, matching this
 * file's existing convention of one named constant per distinct backend
 * `require_role_session` call site (see `PAYMENT_SUBMIT_ROLES` vs.
 * `PAYMENT_RESOLVE_ROLES` above for the same reasoning) -- a future
 * change to either allowlist independently should not have to first
 * notice the two names are secretly the same list.
 */
export const RECONCILIATION_ROLES: RoleCode[] = [
  "SUPER_ADMIN",
  "FINANCE_STAFF",
  "FINANCE_MANAGER",
  "AUDITOR",
];

export function hasRole(role: RoleCode, allowed: RoleCode[]): boolean {
  return allowed.includes(role);
}

/** Module 14 Home-dashboard section gates. Deliberately distinct from
 * `APPLICANTS_ROLES` above rather than reusing it directly: `APPLICANTS_ROLES`
 * is scoped to "the roles that actually own the transition workflow"
 * (per that constant's own comment), but `GET /applicants/summary`'s real
 * backend RBAC (`app.routers.applicants_read`, "intentionally none beyond
 * any authenticated session" per that module's own docstring) is open to
 * all six roles, RLS-narrowed per caller. `AUDITOR` genuinely has
 * applicant read visibility through that RLS-open design -- they already
 * have `IMPORT_HISTORY_ROLES` nav access for the same auditing reason --
 * so the dashboard's applicant-summary section includes `AUDITOR`
 * alongside the three workflow-owning roles, even though the applicants
 * *nav link* itself does not. `DASHBOARD_FINANCE_ROLES` reuses
 * `FINANCE_ROLES` verbatim (identical membership, no asymmetry to
 * preserve here) rather than being redefined, since finance visibility
 * for a dashboard summary is not narrower than the existing finance nav
 * gate the way applicant visibility is.
 *
 * Membership overlap is intentional and exact: `SUPER_ADMIN` and
 * `AUDITOR` are the only two roles in both sets, so they are the only two
 * roles that see both dashboard sections; `ADMISSIONS_MANAGER`/
 * `ADMISSIONS_COUNSELOR` see only the applicant section;
 * `FINANCE_STAFF`/`FINANCE_MANAGER` see only the finance section. Every
 * one of the six roles is in at least one set today, so "a role in
 * neither section" is not a case any current role hits, but the
 * `hasRole` checks on `HomePage` are written to support it correctly if a
 * future role is ever added that genuinely belongs in neither.
 */
export const DASHBOARD_APPLICANTS_ROLES: RoleCode[] = [
  "SUPER_ADMIN",
  "ADMISSIONS_MANAGER",
  "ADMISSIONS_COUNSELOR",
  "AUDITOR",
];

export const DASHBOARD_FINANCE_ROLES: RoleCode[] = FINANCE_ROLES;

/** `app.routers.users`'s own `require_role_session(RoleCode.SUPER_ADMIN)`
 * allowlist, copied verbatim (Module 15) -- `GET /users`/`POST /users`/
 * `PATCH /users/{id}`/`POST /users/{id}/reset-totp` all gate on exactly
 * this one role, with no asymmetry between them the way payment-claim
 * submit/resolve or import upload/history have. Used both for the Users
 * nav link and for `RequireAuth`-style route gating on `/users` itself.
 */
export const USERS_ROLES: RoleCode[] = ["SUPER_ADMIN"];

/** Mirrors `api/app/models/enums.MANDATORY_TOTP_ROLES` exactly -- the
 * three roles TOTP enrollment is mandatory for. `UsersPage` uses this to
 * decide which rows get a "Reset TOTP" action at all: resetting TOTP for
 * a role that was never required to enroll in the first place is a
 * meaningless action the backend would still technically accept
 * (`POST /users/{id}/reset-totp` has no role-specific guard of its own),
 * but offering it in the UI for e.g. an `ADMISSIONS_COUNSELOR` would be
 * inviting an action with no real effect on that account's own login
 * flow.
 */
export const MANDATORY_TOTP_ROLES: RoleCode[] = [
  "SUPER_ADMIN",
  "FINANCE_STAFF",
  "FINANCE_MANAGER",
];
