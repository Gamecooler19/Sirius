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
