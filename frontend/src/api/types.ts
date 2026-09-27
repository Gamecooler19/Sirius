/** Request/response shapes mirroring `api/app/schemas/auth.py` exactly --
 * the frontend's own contract with the real backend, not a superset or
 * a convenience reshaping of it.
 */

export type RoleCode =
  | "SUPER_ADMIN"
  | "ADMISSIONS_MANAGER"
  | "ADMISSIONS_COUNSELOR"
  | "FINANCE_STAFF"
  | "FINANCE_MANAGER"
  | "AUDITOR";

export interface LoginRequest {
  email: string;
  password: string;
}

export interface LoginResponse {
  user_id: string;
  role_code: RoleCode;
  totp_required: boolean;
  totp_enrollment_required: boolean;
}

export interface TotpEnrollStartResponse {
  provisioning_uri: string;
  backup_codes: string[];
}

export interface TotpEnrollConfirmRequest {
  code: string;
}

export interface TotpVerifyRequest {
  code: string;
}

export interface TotpBackupCodeRequest {
  backup_code: string;
}

export interface MeResponse {
  user_id: string;
  email: string;
  full_name: string;
  role_code: RoleCode;
  totp_enabled: boolean;
}

/** Mirrors `api/app/models/enums.ApplicationStatus` exactly -- the fixed
 * applicant status pipeline. `ENROLLED` is deliberately absent (out of
 * scope, per that enum's own docstring).
 */
export type ApplicationStatus =
  | "IMPORTED"
  | "APPLIED"
  | "IN_PROCESS"
  | "ON_HOLD"
  | "ADMISSION_OFFERED"
  | "ADMISSION_TAKEN"
  | "REJECTED"
  | "WITHDRAWN";

/** Mirrors `api/app/schemas/reads.py` exactly. */
export interface ApplicantSummary {
  id: string;
  full_name: string;
  email: string;
  phone: string | null;
  program: string;
  intake_cycle: string;
  current_status: ApplicationStatus;
  assigned_counselor_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface ApplicantListResponse {
  items: ApplicantSummary[];
  total: number;
  limit: number;
  offset: number;
}

export interface ApplicantDetail extends ApplicantSummary {
  import_batch_id: string | null;
}

/** Mirrors `api/app/schemas/reads.py::ApplicantStatusBreakdown`/
 * `ApplicantSummaryTotals` exactly -- the real `GET /applicants/summary`
 * response (Module 14). `by_status` is always present for all 8
 * `ApplicationStatus` values, even at `count: 0`, the same always-present
 * bucket convention `PaymentClaimStatusBreakdown` already established.
 * Carries no role/scope field of its own -- the counts it returns are
 * already narrowed to the caller's own RLS-scoped view, entirely by
 * `applicant`'s own existing RLS policy, not by anything in this response
 * shape.
 */
export interface ApplicantStatusBreakdown {
  status: ApplicationStatus;
  count: number;
}

export interface ApplicantSummaryTotals {
  total: number;
  by_status: ApplicantStatusBreakdown[];
}

export interface StatusHistoryEvent {
  id: string;
  applicant_id: string;
  from_status: ApplicationStatus | null;
  to_status: ApplicationStatus;
  changed_by: string | null;
  note: string | null;
  created_at: string;
}

export interface StatusHistoryResponse {
  items: StatusHistoryEvent[];
}

/** Mirrors `api/app/schemas/status.py` exactly. */
export interface StatusTransitionRequest {
  to_status: ApplicationStatus;
  note?: string | null;
}

export interface StatusTransitionResponse {
  applicant_id: string;
  from_status: ApplicationStatus;
  to_status: ApplicationStatus;
  changed_by: string;
  created_at: string;
}

/** Mirrors `api/app/models/enums.ImportBatchStatus` exactly. */
export type ImportBatchStatus = "PENDING" | "PROCESSING" | "COMPLETED" | "FAILED";

/** Mirrors `api/app/schemas/import_batch.py::ImportBatchResponse` exactly.
 * `flagged_rows` is left as `Record<string, unknown>[] | null` rather than
 * a narrower shape -- the backend itself declares it as a plain
 * `list[dict] | None` (JSONB), not a typed schema, since it's built ad
 * hoc per-row in `app.routers.import_.import_applicants` (row_number,
 * applicant_id, old/new email, old/new phone, reason). The upload page
 * reads known keys off each entry defensively rather than assuming a
 * fixed shape.
 */
export interface ImportBatchResponse {
  id: string;
  status: ImportBatchStatus;
  row_count: number;
  created_count: number;
  updated_count: number;
  flagged_count: number;
  rejected_count: number;
  flagged_rows: Record<string, unknown>[] | null;
  error_detail: string | null;
  completed_at: string | null;
  deduplicated: boolean;
}

/** Mirrors `api/app/schemas/reads.py::ImportBatchSummary`/`ImportBatchListResponse`
 * exactly -- the `GET /import-batches` history list.
 */
export interface ImportBatchSummary {
  id: string;
  source_filename: string;
  status: string;
  row_count: number | null;
  checksum: string | null;
  created_count: number;
  updated_count: number;
  flagged_count: number;
  rejected_count: number;
  error_detail: string | null;
  imported_by: string;
  created_at: string;
  completed_at: string | null;
}

export interface ImportBatchListResponse {
  items: ImportBatchSummary[];
  total: number;
  limit: number;
  offset: number;
}

/** Mirrors `api/app/models/enums.PaymentClaimStatus` and `PaymentMode`
 * exactly.
 */
export type PaymentClaimStatus = "PENDING" | "CONFIRMED" | "REJECTED";

export type PaymentMode = "CASH" | "CHEQUE" | "BANK_TRANSFER" | "UPI" | "CARD" | "OTHER";

/** Mirrors `api/app/schemas/payment_claim.py::PaymentClaimSubmitRequest`
 * exactly -- deliberately has no `submitted_by` field, since the backend
 * takes that from the authenticated session identity, never from the
 * request body (that schema's own docstring: "trusting a client-supplied
 * identity for an audit-relevant field... defeats the entire point of
 * recording it"). This frontend type mirrors that omission rather than
 * inventing a field the backend would ignore.
 */
export interface PaymentClaimSubmitRequest {
  finance_record_id: string;
  amount: string;
  payment_mode: PaymentMode;
  reference_number?: string | null;
}

/** Mirrors `PaymentClaimResolveRequest` exactly -- the only input either
 * `/confirm` or `/reject` takes.
 */
export interface PaymentClaimResolveRequest {
  note?: string | null;
}

/** Mirrors `PaymentClaimResponse` (submit/confirm/reject) exactly. */
export interface PaymentClaimResponse {
  id: string;
  finance_record_id: string;
  amount: string;
  status: PaymentClaimStatus;
  payment_mode: PaymentMode;
  reference_number: string | null;
  submitted_by: string;
  confirmed_by: string | null;
  confirmed_at: string | null;
  note: string | null;
}

/** Mirrors `api/app/schemas/reads.py::PaymentClaimDetail` exactly --
 * the shape `GET /finance/payment-claims` and `GET /applicants/{id}/finance`
 * both return for each claim. Same fields as `PaymentClaimResponse` plus
 * `created_at`.
 */
export interface PaymentClaimDetail {
  id: string;
  finance_record_id: string;
  amount: string;
  status: PaymentClaimStatus;
  payment_mode: PaymentMode;
  reference_number: string | null;
  submitted_by: string;
  confirmed_by: string | null;
  confirmed_at: string | null;
  note: string | null;
  created_at: string;
}

export interface PaymentClaimListResponse {
  items: PaymentClaimDetail[];
  total: number;
  limit: number;
  offset: number;
}

/** Mirrors `api/app/schemas/reads.py::ApplicantFinanceResponse` exactly
 * -- the real `GET /applicants/{id}/finance` response.
 */
export interface ApplicantFinanceResponse {
  finance_record_id: string;
  applicant_id: string;
  total_fee_due: string;
  total_paid: string;
  payment_claims: PaymentClaimDetail[];
}

/** Mirrors `api/app/schemas/reads.py::PaymentClaimStatusBreakdown` exactly
 * -- one status bucket within a reconciliation row. Always present for
 * all three `PaymentClaimStatus` values in a given row's
 * `claims_by_status`, even when a status has zero claims in that scope
 * (`count: 0, amount: "0"` rather than the status being omitted) -- see
 * that schema's own docstring.
 */
export interface PaymentClaimStatusBreakdown {
  status: PaymentClaimStatus;
  count: number;
  amount: string;
}

/** Mirrors `api/app/schemas/reads.py::ReconciliationCycle` exactly --
 * one `GET /finance/reconciliation` row: every `finance_record` whose
 * parent `applicant.intake_cycle` equals this cycle, summed, plus the
 * same `claims_by_status` breakdown for every `payment_claim` against
 * one of those `finance_record`s.
 */
export interface ReconciliationCycle {
  intake_cycle: string;
  finance_record_count: number;
  total_fee_due: string;
  total_paid: string;
  outstanding: string;
  claims_by_status: PaymentClaimStatusBreakdown[];
}

/** Mirrors `api/app/schemas/reads.py::ReconciliationTotals` exactly --
 * same shape as `ReconciliationCycle` minus `intake_cycle`, the sum of
 * every cycle row combined (computed by the backend from the `cycles`
 * array itself, not a separate SQL aggregate -- see that route's own
 * docstring).
 */
export interface ReconciliationTotals {
  finance_record_count: number;
  total_fee_due: string;
  total_paid: string;
  outstanding: string;
  claims_by_status: PaymentClaimStatusBreakdown[];
}

/** Mirrors `api/app/schemas/reads.py::ReconciliationResponse` exactly --
 * the real `GET /finance/reconciliation` response. No pagination, no
 * filters -- this endpoint has neither, matching the router's own
 * signature (`app.routers.reconciliation.get_reconciliation` takes no
 * query params).
 */
export interface ReconciliationResponse {
  cycles: ReconciliationCycle[];
  totals: ReconciliationTotals;
}

/** Mirrors `api/app/schemas/auth.py::ChangePasswordRequest` exactly
 * (Module 15) -- deliberately has no user-id field, since
 * `POST /auth/change-password` sources the target account solely from
 * the session cookie.
 */
export interface ChangePasswordRequest {
  current_password: string;
  new_password: string;
}

/** Mirrors `api/app/schemas/users.py::UserSummary` exactly (Module 15)
 * -- one row of `GET /users`, and the shape `POST /users`/
 * `PATCH /users/{id}`/`POST /users/{id}/reset-totp` all return.
 * Deliberately has no `password_hash`/`totp_secret_encrypted` field --
 * the backend response never carries either.
 */
export interface UserSummary {
  id: string;
  email: string;
  full_name: string;
  role_code: RoleCode;
  is_active: boolean;
  totp_enabled: boolean;
  last_login_at: string | null;
  created_at: string;
}

export interface UserListResponse {
  items: UserSummary[];
  total: number;
  limit: number;
  offset: number;
}

/** Mirrors `api/app/schemas/users.py::UserCreateRequest` exactly. */
export interface UserCreateRequest {
  email: string;
  full_name: string;
  password: string;
  role_code: RoleCode;
}

/** Mirrors `api/app/schemas/users.py::UserUpdateRequest` exactly -- both
 * fields optional, `undefined`/omitted means "leave alone" on the wire
 * the same way the backend's own `None`-default does.
 */
export interface UserUpdateRequest {
  role_code?: RoleCode;
  is_active?: boolean;
}
