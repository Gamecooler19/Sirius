/** TanStack Query hooks wrapping the real Excel-import endpoints:
 * `POST /import/applicants` (`api/app/routers/import_.py`) and
 * `GET /import-batches` (`api/app/routers/import_batches_read.py`). No
 * mocked responses -- every hook calls the live backend through
 * `api/client.ts`.
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../api/client";
import type { ImportBatchListResponse, ImportBatchResponse } from "../api/types";
import { applicantsKeys } from "../applicants/useApplicants";

export const importBatchesKeys = {
  list: (params: ImportBatchListParams) => ["importBatches", "list", params] as const,
};

export interface ImportBatchListParams {
  limit: number;
  offset: number;
}

export function useImportBatchesList(params: ImportBatchListParams) {
  return useQuery({
    queryKey: importBatchesKeys.list(params),
    queryFn: () =>
      api.get<ImportBatchListResponse>(
        `/import-batches?limit=${params.limit}&offset=${params.offset}`,
      ),
    placeholderData: (previousData) => previousData,
  });
}

/** `POST /import/applicants`. `multipart/form-data`, hence
 * `api.postFormData` rather than `api.post` -- see that method's own
 * comment for why a manually-set `Content-Type` would silently corrupt
 * this exact call.
 *
 * On a genuinely new (non-deduplicated) import, invalidates the
 * applicant-list query cache so any newly created or updated applicants
 * show up in `ApplicantsPage` without a manual reload, and the
 * import-batches history list so the new batch appears there too. A
 * `deduplicated: true` response touched nothing server-side (the backend
 * short-circuits before any applicant read or write), so no cache
 * invalidation happens for that case -- there is genuinely nothing new to
 * reflect.
 */
export function useImportApplicants() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (file: File) => {
      const formData = new FormData();
      formData.append("file", file);
      return api.postFormData<ImportBatchResponse>("/import/applicants", formData);
    },
    onSuccess: (result) => {
      if (!result.deduplicated) {
        queryClient.invalidateQueries({ queryKey: applicantsKeys.all });
        queryClient.invalidateQueries({ queryKey: ["importBatches"] });
      }
    },
  });
}
