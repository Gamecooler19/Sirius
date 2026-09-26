/** TanStack Query hook wrapping `GET /auth/me` -- the single source of
 * truth for "who is the current session, and is it fully authenticated"
 * that the app shell and route guard both depend on.
 *
 * A 401 here (no session cookie, expired session, or backend restart that
 * dropped Valkey state) is not an error state to retry -- it means "there
 * is no session," so `retry: false` and the resulting `isError` is what
 * route guarding checks to redirect to `/login`.
 */

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "./client";
import type { MeResponse } from "./types";

export const ME_QUERY_KEY = ["auth", "me"] as const;

export function useMe() {
  return useQuery({
    queryKey: ME_QUERY_KEY,
    queryFn: () => api.get<MeResponse>("/auth/me"),
    retry: false,
    staleTime: 60_000,
  });
}

/** Call after login/TOTP-verify/logout succeeds so the shell re-fetches
 * `/auth/me` against the now-changed session rather than showing stale
 * cached identity.
 */
export function useInvalidateMe() {
  const queryClient = useQueryClient();
  return () => queryClient.invalidateQueries({ queryKey: ME_QUERY_KEY });
}
