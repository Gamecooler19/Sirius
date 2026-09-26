import { MantineProvider } from "@mantine/core";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { AppRouter } from "./app/router";
import { ApiError } from "./api/client";

/** 401s are handled explicitly by `RequireAuth`/mutation error branches,
 * not by a global retry loop -- retrying a request that failed because
 * there's no valid session just repeats the same 401 three times before
 * giving up.
 */
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: (failureCount, error) => {
        if (error instanceof ApiError && error.status === 401) return false;
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
