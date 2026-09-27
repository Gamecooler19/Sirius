/** TanStack Query hooks wrapping the real `/applicants*` read endpoints
 * (`api/app/routers/applicants_read.py`) and the status-transition write
 * endpoint (`api/app/routers/status.py`). No mocked data anywhere here --
 * every hook calls the live backend through `api/client.ts`.
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../api/client";
import type {
  ApplicantCreateRequest,
  ApplicantDetail,
  ApplicantListResponse,
  ApplicantSummaryTotals,
  ApplicationStatus,
  CounselorOption,
  StatusHistoryResponse,
  StatusTransitionRequest,
  StatusTransitionResponse,
} from "../api/types";

/** Matches `GET /applicants`'s own query params exactly
 * (`app.routers.applicants_read.list_applicants`) -- `limit`/`offset` for
 * pagination, `current_status`/`program`/`intake_cycle` as the only three
 * filters the backend actually supports. No filter is invented here that
 * the backend doesn't accept.
 */
export interface ApplicantListParams {
  limit: number;
  offset: number;
  current_status?: ApplicationStatus | null;
  program?: string | null;
  intake_cycle?: string | null;
}

function buildQueryString(params: ApplicantListParams): string {
  const search = new URLSearchParams();
  search.set("limit", String(params.limit));
  search.set("offset", String(params.offset));
  if (params.current_status) search.set("current_status", params.current_status);
  if (params.program) search.set("program", params.program);
  if (params.intake_cycle) search.set("intake_cycle", params.intake_cycle);
  return search.toString();
}

export const applicantsKeys = {
  all: ["applicants"] as const,
  list: (params: ApplicantListParams) => ["applicants", "list", params] as const,
  detail: (id: string) => ["applicants", "detail", id] as const,
  statusHistory: (id: string) => ["applicants", "statusHistory", id] as const,
  summary: ["applicants", "summary"] as const,
};

export function useApplicantsList(params: ApplicantListParams) {
  return useQuery({
    queryKey: applicantsKeys.list(params),
    queryFn: () => api.get<ApplicantListResponse>(`/applicants?${buildQueryString(params)}`),
    placeholderData: (previousData) => previousData,
  });
}

/** TanStack Query hook wrapping the real `GET /applicants/summary`
 * (Module 14, `app.routers.applicants_read.get_applicant_summary`). Same
 * RLS-scoped-by-the-backend contract as `useApplicantsList` -- this hook
 * passes no role or scope parameter of its own; the counts it receives
 * are already narrowed to the caller's own session by the backend's reuse
 * of `applicant`'s existing RLS policy.
 */
export function useApplicantSummary() {
  return useQuery({
    queryKey: applicantsKeys.summary,
    queryFn: () => api.get<ApplicantSummaryTotals>("/applicants/summary"),
  });
}

export function useApplicantDetail(id: string | null) {
  return useQuery({
    queryKey: applicantsKeys.detail(id ?? ""),
    queryFn: () => api.get<ApplicantDetail>(`/applicants/${id}`),
    enabled: id !== null,
  });
}

export function useApplicantStatusHistory(id: string | null) {
  return useQuery({
    queryKey: applicantsKeys.statusHistory(id ?? ""),
    queryFn: () => api.get<StatusHistoryResponse>(`/applicants/${id}/status-history`),
    enabled: id !== null,
  });
}

/** `POST /applicants/{id}/status` -- the real transition endpoint. The
 * frontend's own `ALLOWED_TRANSITIONS` table (`statusTransitions.ts`)
 * only decides which options the UI *offers*; this call always goes to
 * the real backend, whose 422 on a genuinely invalid transition is the
 * actual enforcement (surfaced via `ApiError`, not swallowed here).
 *
 * On success, invalidates the list, this applicant's detail, and its
 * status-history -- the three query caches whose data the transition just
 * changed -- so the UI reflects the new state without a manual reload.
 */
export function useTransitionApplicantStatus(applicantId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: StatusTransitionRequest) =>
      api.post<StatusTransitionResponse>(`/applicants/${applicantId}/status`, body),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: applicantsKeys.all });
    },
  });
}

/** `POST /applicants` -- manual single-applicant creation (Module 19,
 * `api/app/routers/applicant_create.py`). On success, invalidates the
 * exact same `applicantsKeys.all` query key
 * `useTransitionApplicantStatus` already invalidates above -- the same
 * "the list/summary caches whose data this write just changed" rule,
 * so the newly-created applicant appears in `ApplicantsPage`'s own list
 * (and the Home dashboard's status-breakdown widget) immediately,
 * without a manual reload, exactly like a status transition already
 * does.
 */
export function useCreateApplicant() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: ApplicantCreateRequest) => api.post<ApplicantDetail>("/applicants", body),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: applicantsKeys.all });
    },
  });
}

/** `GET /applicants/counselors` -- the assign-to picker's own data
 * source (Module 19, `SUPER_ADMIN`/`ADMISSIONS_MANAGER` only on the
 * backend). `enabled` lets the caller skip this fetch entirely for an
 * `ADMISSIONS_COUNSELOR` session, which has no use for it (always
 * auto-assigned to themselves) and would otherwise get a real,
 * expected 403 from the backend's own role gate.
 */
export function useAssignableCounselors(enabled: boolean) {
  return useQuery({
    queryKey: ["applicants", "counselors"] as const,
    queryFn: () => api.get<CounselorOption[]>("/applicants/counselors"),
    enabled,
  });
}
