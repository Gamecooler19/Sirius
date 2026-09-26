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

export function hasRole(role: RoleCode, allowed: RoleCode[]): boolean {
  return allowed.includes(role);
}
