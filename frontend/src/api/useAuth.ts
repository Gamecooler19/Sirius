/** TanStack Query mutations wrapping every `/auth/*` write endpoint. */

import { useMutation } from "@tanstack/react-query";
import { api } from "./client";
import { useInvalidateMe } from "./useMe";
import type {
  LoginRequest,
  LoginResponse,
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
