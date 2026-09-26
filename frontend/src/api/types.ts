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
