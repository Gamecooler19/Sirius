/** TanStack Query hooks wrapping the real payment-claim endpoints
 * (`api/app/routers/payment_claim.py`) and the applicant finance-detail
 * read (`api/app/routers/applicants_read.py::get_applicant_finance`). No
 * mocked data -- every hook calls the live backend through
 * `api/client.ts`.
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, ApiError } from "../api/client";
import type {
  ApplicantFinanceResponse,
  PaymentClaimListResponse,
  PaymentClaimResolveRequest,
  PaymentClaimResponse,
  PaymentClaimStatus,
  PaymentClaimSubmitRequest,
} from "../api/types";

export const financeKeys = {
  claimsList: (params: PaymentClaimListParams) => ["financeClaims", "list", params] as const,
  applicantFinance: (applicantId: string) => ["applicants", "finance", applicantId] as const,
};

/** Matches `GET /finance/payment-claims`'s own query params exactly
 * (`app.routers.payment_claim.list_payment_claims`) -- `limit`/`offset`
 * for pagination, `status` as the only filter the backend accepts.
 */
export interface PaymentClaimListParams {
  limit: number;
  offset: number;
  status?: PaymentClaimStatus | null;
}

export function usePaymentClaimsList(params: PaymentClaimListParams) {
  return useQuery({
    queryKey: financeKeys.claimsList(params),
    queryFn: () => {
      const search = new URLSearchParams();
      search.set("limit", String(params.limit));
      search.set("offset", String(params.offset));
      if (params.status) search.set("status", params.status);
      return api.get<PaymentClaimListResponse>(`/finance/payment-claims?${search.toString()}`);
    },
    placeholderData: (previousData) => previousData,
  });
}

/** `GET /applicants/{id}/finance`. A 404 here is the documented, expected
 * "no finance record exists yet" state (most applicants -- anyone who
 * never reached `ADMISSION_TAKEN` -- have none), not a genuine error, so
 * this hook exposes a distinct `notFound` flag rather than leaving the
 * caller to inspect `error.status` itself, and disables TanStack Query's
 * own retry for exactly this one expected case (retrying a 404 three
 * times before rendering the empty state would only slow it down).
 */
export function useApplicantFinance(applicantId: string | null) {
  const query = useQuery({
    queryKey: financeKeys.applicantFinance(applicantId ?? ""),
    queryFn: () => api.get<ApplicantFinanceResponse>(`/applicants/${applicantId}/finance`),
    enabled: applicantId !== null,
    retry: false,
  });
  const notFound = query.error instanceof ApiError && query.error.status === 404;
  return { ...query, notFound };
}

/** `POST /finance/payment-claims`. `finance_record_id` comes from the
 * already-loaded finance record (never client-typed), `submitted_by` is
 * never sent at all -- the backend takes it from the session. On
 * success, invalidates this applicant's own finance-detail query (the
 * new claim now belongs in its `payment_claims` list) and the standalone
 * claims-list query root, so the new claim appears in `FinancePage`'s
 * queue without a reload.
 */
export function useSubmitPaymentClaim(applicantId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: PaymentClaimSubmitRequest) =>
      api.post<PaymentClaimResponse>("/finance/payment-claims", body),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: financeKeys.applicantFinance(applicantId) });
      queryClient.invalidateQueries({ queryKey: ["financeClaims"] });
    },
  });
}

/** `POST /finance/payment-claims/{id}/confirm` and `/reject`. The
 * backend's own maker-checker rejection (resolving your own submission)
 * and "not PENDING" rejection both surface here verbatim via `ApiError`
 * -- this hook does not pre-check either condition or substitute its own
 * message.
 *
 * On success, invalidates the standalone claims-list query root and
 * every applicant finance-detail query (`["applicants", "finance"]` as a
 * key *prefix*, matching every applicant's own finance query rather than
 * one specific id) -- `PaymentClaimDetail` itself carries no
 * `applicant_id`, only `finance_record_id`, so `FinancePage`'s queue
 * (where confirm/reject actually live) has no single applicant id to
 * target-invalidate. Invalidating the whole finance-detail prefix is
 * cheap (React Query only refetches queries that are actually mounted)
 * and correctly reaches an already-open `ApplicantDetailDrawer` showing
 * the resolved claim's own applicant without a manual refresh.
 */
export function useResolvePaymentClaim() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      claimId,
      action,
      body,
    }: {
      claimId: string;
      action: "confirm" | "reject";
      body: PaymentClaimResolveRequest;
    }) => api.post<PaymentClaimResponse>(`/finance/payment-claims/${claimId}/${action}`, body),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["financeClaims"] });
      queryClient.invalidateQueries({ queryKey: ["applicants", "finance"] });
    },
  });
}
