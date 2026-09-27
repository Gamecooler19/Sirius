/** TanStack Query mutations wrapping every `/auth/*` write endpoint. */

import { useMutation } from "@tanstack/react-query";
import { api } from "./client";
import { useInvalidateMe } from "./useMe";
import type {
  ChangeEmailRequest,
  ChangeEmailResponse,
  ChangeNameRequest,
  ChangePasswordRequest,
  ConfirmEmailChangeRequest,
  ForgotPasswordRequest,
  ForgotPasswordResponse,
  LoginRequest,
  LoginResponse,
  ResetPasswordRequest,
  SelfTotpResetRequest,
  TotpBackupCodeRequest,
  TotpEnrollConfirmRequest,
  TotpEnrollStartResponse,
  TotpVerifyRequest,
} from "./types";

export function useLogin() {
  return useMutation({
    mutationFn: (body: LoginRequest) => api.post<LoginResponse>("/auth/login", body),
  });
}

export function useLogout() {
  const invalidateMe = useInvalidateMe();
  return useMutation({
    mutationFn: () => api.post<void>("/auth/logout"),
    onSettled: () => invalidateMe(),
  });
}

export function useTotpEnrollStart() {
  return useMutation({
    mutationFn: () => api.post<TotpEnrollStartResponse>("/auth/totp/enroll/start"),
  });
}

export function useTotpEnrollConfirm() {
  const invalidateMe = useInvalidateMe();
  return useMutation({
    mutationFn: (body: TotpEnrollConfirmRequest) => api.post<void>("/auth/totp/enroll/confirm", body),
    onSuccess: () => invalidateMe(),
  });
}

export function useTotpVerify() {
  const invalidateMe = useInvalidateMe();
  return useMutation({
    mutationFn: (body: TotpVerifyRequest) => api.post<void>("/auth/totp/verify", body),
    onSuccess: () => invalidateMe(),
  });
}

export function useTotpVerifyBackupCode() {
  const invalidateMe = useInvalidateMe();
  return useMutation({
    mutationFn: (body: TotpBackupCodeRequest) => api.post<void>("/auth/totp/verify-backup-code", body),
    onSuccess: () => invalidateMe(),
  });
}

/** `POST /auth/change-password` (Module 15). No `onSuccess`
 * invalidation of `/auth/me` needed -- a password change does not
 * change anything `/auth/me` itself reports (email, role, TOTP status
 * are all unaffected), and the session cookie stays valid; the caller
 * simply keeps using the same authenticated session with the new
 * credential now live.
 */
export function useChangePassword() {
  return useMutation({
    mutationFn: (body: ChangePasswordRequest) => api.post<void>("/auth/change-password", body),
  });
}

/** `POST /auth/change-name` (Module 18). Invalidates `/auth/me` on
 * success so `ProfilePage`'s own summary card and `UsersPage`'s
 * "Full name" column both reflect the new value immediately, unlike
 * `useChangePassword` above (which changes nothing `/auth/me` reports).
 */
export function useChangeName() {
  const invalidateMe = useInvalidateMe();
  return useMutation({
    mutationFn: (body: ChangeNameRequest) => api.post<void>("/auth/change-name", body),
    onSuccess: () => invalidateMe(),
  });
}

/** `POST /auth/totp/self-reset` (Module 18). Returns the same
 * `TotpEnrollStartResponse` shape `useTotpEnrollStart` does -- a fresh
 * QR/backup-code pair the caller must still confirm via
 * `useTotpEnrollConfirm`. No `/auth/me` invalidation here: `totp_enabled`
 * does not flip back to `true` until that confirm step succeeds, the
 * same two-step shape ordinary enrollment already follows.
 */
export function useTotpSelfReset() {
  return useMutation({
    mutationFn: (body: SelfTotpResetRequest) =>
      api.post<TotpEnrollStartResponse>("/auth/totp/self-reset", body),
  });
}

/** `POST /auth/forgot-password` (Module 16). Unauthenticated -- no
 * `useInvalidateMe` needed, since there is no session to invalidate at
 * this point in the flow.
 */
export function useForgotPassword() {
  return useMutation({
    mutationFn: (body: ForgotPasswordRequest) =>
      api.post<ForgotPasswordResponse>("/auth/forgot-password", body),
  });
}

/** `POST /auth/reset-password` (Module 16). Unauthenticated -- the raw
 * token from the email link is the entire request; no session exists
 * yet for this to invalidate.
 */
export function useResetPassword() {
  return useMutation({
    mutationFn: (body: ResetPasswordRequest) => api.post<void>("/auth/reset-password", body),
  });
}

/** `POST /auth/change-email` (Module 17). Authenticated -- invalidates
 * `/auth/me` on success so `ProfilePage` immediately shows the new
 * `pending_email` (the account's own *current* `email` does not change
 * yet; only the pending-state indicator does).
 */
export function useChangeEmail() {
  const invalidateMe = useInvalidateMe();
  return useMutation({
    mutationFn: (body: ChangeEmailRequest) =>
      api.post<ChangeEmailResponse>("/auth/change-email", body),
    onSuccess: () => invalidateMe(),
  });
}

/** `POST /auth/confirm-email-change` (Module 17). Unauthenticated --
 * the raw token from the confirmation email (sent to the new address)
 * is the entire request.
 */
export function useConfirmEmailChange() {
  return useMutation({
    mutationFn: (body: ConfirmEmailChangeRequest) =>
      api.post<void>("/auth/confirm-email-change", body),
  });
}
