/** The exact applicant status transition table, copied field-for-field
 * from `api/app/services/status_transitions.py::ALLOWED_TRANSITIONS` --
 * the same "copy the backend's own source, don't invent new logic"
 * pattern Module 06 used for `APPLICANTS_ROLES`/`FINANCE_ROLES`.
 *
 * This is UX convenience only: it decides which next-states the frontend
 * *offers* as selectable so a user isn't invited to try something that
 * will obviously 422. It is not the enforcement point. The backend's own
 * `is_transition_allowed` (same file) is what actually rejects an invalid
 * transition with a 422, and that 422's real text is what the UI surfaces
 * via the existing `ApiError` path if this table ever drifts from the
 * backend's (e.g. a future backend change lands here late) or if a
 * request is forced through some other path (curl, a stale tab).
 *
 * Transition table (mirrors the backend docstring exactly):
 *
 *     IMPORTED -> APPLIED
 *     APPLIED -> IN_PROCESS
 *     IN_PROCESS -> ON_HOLD
 *     ON_HOLD -> IN_PROCESS
 *     IN_PROCESS -> ADMISSION_OFFERED
 *     ADMISSION_OFFERED -> ADMISSION_TAKEN
 *     {APPLIED, IN_PROCESS, ON_HOLD, ADMISSION_OFFERED} -> REJECTED
 *     {APPLIED, IN_PROCESS, ON_HOLD, ADMISSION_OFFERED} -> WITHDRAWN
 *
 * `ADMISSION_TAKEN`, `REJECTED`, `WITHDRAWN` are terminal -- deliberately
 * absent as keys below, exactly as the backend's own dict omits them.
 */

import type { ApplicationStatus } from "../api/types";

export const ALLOWED_TRANSITIONS: Record<ApplicationStatus, ApplicationStatus[]> = {
  IMPORTED: ["APPLIED"],
  APPLIED: ["IN_PROCESS", "REJECTED", "WITHDRAWN"],
  IN_PROCESS: ["ON_HOLD", "ADMISSION_OFFERED", "REJECTED", "WITHDRAWN"],
  ON_HOLD: ["IN_PROCESS", "REJECTED", "WITHDRAWN"],
  ADMISSION_OFFERED: ["ADMISSION_TAKEN", "REJECTED", "WITHDRAWN"],
  ADMISSION_TAKEN: [],
  REJECTED: [],
  WITHDRAWN: [],
};

export function allowedNextStatuses(from: ApplicationStatus): ApplicationStatus[] {
  return ALLOWED_TRANSITIONS[from] ?? [];
}

/** Every status value, in pipeline order -- for filter dropdowns and the
 * status-transition select's full option list (with invalid destinations
 * disabled rather than omitted, so the user can see the whole pipeline).
 */
export const ALL_STATUSES: ApplicationStatus[] = [
  "IMPORTED",
  "APPLIED",
  "IN_PROCESS",
  "ON_HOLD",
  "ADMISSION_OFFERED",
  "ADMISSION_TAKEN",
  "REJECTED",
  "WITHDRAWN",
];
