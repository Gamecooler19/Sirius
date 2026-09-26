import { MantineProvider } from "@mantine/core";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { AppRouter } from "./app/router";
import { ApiError } from "./api/client";

/** No 4xx status is worth retrying -- a 401 (no session), 403 (wrong
 * role), 404 (not found/RLS-invisible), or 422 (validation) all mean the
 * exact same request will fail again identically; retrying only delays
 * the real error reaching the UI (and, combined with the default
 * exponential backoff, can leave a query sitting in a `pending` state for
 * seconds with neither a loader nor the actual error visible -- a real
 * defect this project's own Module 08 live verification caught: an
 * `ImportHistoryPage` query for a role outside `_LIST_ROLES` returned a
 * real 403 immediately, but the page showed neither the loading spinner
 * nor the red error `Alert` for several seconds because the query was
 * still retrying a request that could never succeed). Only a genuine
 * transient failure (network error, 5xx) is worth the two extra
 * attempts.
 */
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: (failureCount, error) => {
        if (error instanceof ApiError && error.status >= 400 && error.status < 500) return false;
        return failureCount < 2;
      },
    },
  },
});

export default function App() {
  return (
    <MantineProvider>
      <QueryClientProvider client={queryClient}>
        <AppRouter />
      </QueryClientProvider>
    </MantineProvider>
  );
}
