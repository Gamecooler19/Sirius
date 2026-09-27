/** TanStack Query hooks wrapping the real `/users*` administration
 * endpoints (`api/app/routers/users.py`, Module 15). No mocked data --
 * every hook calls the live backend through `api/client.ts`. Every write
 * mutation invalidates the shared `["users"]` query key on success so the
 * list re-fetches with the fresh row, the same
 * invalidate-the-whole-namespace pattern `applicants/useApplicants.ts`'s
 * `useTransitionApplicantStatus` already established.
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../api/client";
import type {
  UserCreateRequest,
  UserListResponse,
  UserSummary,
  UserUpdateRequest,
} from "../api/types";

export interface UserListParams {
  limit: number;
  offset: number;
}

export const usersKeys = {
  all: ["users"] as const,
  list: (params: UserListParams) => ["users", "list", params] as const,
};

export function useUsersList(params: UserListParams) {
  return useQuery({
    queryKey: usersKeys.list(params),
    queryFn: () => api.get<UserListResponse>(`/users?limit=${params.limit}&offset=${params.offset}`),
    placeholderData: (previousData) => previousData,
  });
}

export function useCreateUser() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: UserCreateRequest) => api.post<UserSummary>("/users", body),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: usersKeys.all });
    },
  });
}

/** `PATCH /users/{id}` -- role and/or active-status changes. The
 * backend's own self-lockout guard (`app.routers.users.update_user`)
 * rejects a `SUPER_ADMIN` demoting/deactivating their own account with a
 * real 422; this hook does not pre-empt or special-case that response --
 * it surfaces via the same `ApiError` path every other rejected mutation
 * in this app already uses, and `UsersPage`'s own UI-level guard (a
 * disabled action, not a duplicated check) exists only to avoid inviting
 * the user to try an action the backend will refuse anyway.
 */
export function useUpdateUser() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: UserUpdateRequest }) =>
      api.patch<UserSummary>(`/users/${id}`, body),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: usersKeys.all });
    },
  });
}

export function useResetTotp() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.post<UserSummary>(`/users/${id}/reset-totp`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: usersKeys.all });
    },
  });
}
