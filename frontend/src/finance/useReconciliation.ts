/** TanStack Query hook wrapping the real reconciliation read
 * (`api/app/routers/reconciliation.py::get_reconciliation`). No mocked
 * data -- calls the live backend through `api/client.ts`. This endpoint
 * takes no query parameters at all (no pagination, no filters -- see
 * that router's own signature), so unlike every other list hook in this
 * app, there is nothing to parameterize the query key or the request
 * URL with.
 */

import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import type { ReconciliationResponse } from "../api/types";

export const reconciliationKeys = {
  all: ["reconciliation"] as const,
};

export function useReconciliation() {
  return useQuery({
    queryKey: reconciliationKeys.all,
    queryFn: () => api.get<ReconciliationResponse>("/finance/reconciliation"),
  });
}
