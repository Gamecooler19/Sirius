/** Import-batch history: a real Mantine `Table` driven by
 * `useImportBatchesList`, against the live `GET /import-batches`
 * endpoint. Paginated using the same `limit`/`offset` + `Pagination`
 * pattern Module 07's `ApplicantsPage` already established. Visible to
 * `IMPORT_HISTORY_ROLES` (`SUPER_ADMIN`/`ADMISSIONS_MANAGER`/`AUDITOR`) --
 * a strictly wider set than who may actually upload
 * (`IMPORT_UPLOAD_ROLES`), so an `AUDITOR` reaches this page and its nav
 * link but never sees any upload control (enforced by `ImportUploadPage`
 * itself, not duplicated here).
 */

import { useState } from "react";
import {
  Alert,
  Badge,
  Center,
  Group,
  Loader,
  Pagination,
  Stack,
  Table,
  Text,
  Title,
} from "@mantine/core";
import { WarningCircle, ClockCounterClockwise } from "@phosphor-icons/react";
import { ApiError } from "../api/client";
import { useImportBatchesList } from "./useImport";
import { EmptyState } from "../components/EmptyState";

const PAGE_SIZE = 10;

const STATUS_COLORS: Record<string, string> = {
  PENDING: "gray",
  PROCESSING: "yellow",
  COMPLETED: "green",
  FAILED: "red",
};

export function ImportHistoryPage() {
  const [page, setPage] = useState(1);
  const offset = (page - 1) * PAGE_SIZE;

  const query = useImportBatchesList({ limit: PAGE_SIZE, offset });
  const totalPages = query.data ? Math.max(1, Math.ceil(query.data.total / PAGE_SIZE)) : 1;

  return (
    <Stack>
      <Title order={2}>Import history</Title>

      {query.isError && (
        <Alert color="red" icon={<WarningCircle size={20} weight="light" />}>
          {query.error instanceof ApiError ? query.error.message : "failed to load import history"}
        </Alert>
      )}

      {query.isLoading && (
        <Center py="xl">
          <Loader />
        </Center>
      )}

      {query.data && (
        <>
          <Table.ScrollContainer minWidth={700}>
            <Table striped highlightOnHover withTableBorder>
            <Table.Thead>
              <Table.Tr>
                <Table.Th>Filename</Table.Th>
                <Table.Th>Uploaded</Table.Th>
                <Table.Th>Status</Table.Th>
                <Table.Th>Created</Table.Th>
                <Table.Th>Updated</Table.Th>
                <Table.Th>Flagged</Table.Th>
                <Table.Th>Rejected</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {query.data.items.map((batch) => (
                <Table.Tr key={batch.id}>
                  <Table.Td>{batch.source_filename}</Table.Td>
                  <Table.Td>
                    <Text size="xs" c="dimmed">
                      {new Date(batch.created_at).toLocaleString()}
                    </Text>
                    <Text size="xs" ff="monospace" c="dimmed">
                      {batch.imported_by}
                    </Text>
                  </Table.Td>
                  <Table.Td>
                    <Badge color={STATUS_COLORS[batch.status] ?? "gray"} variant="light">
                      {batch.status}
                    </Badge>
                  </Table.Td>
                  <Table.Td>{batch.created_count}</Table.Td>
                  <Table.Td>{batch.updated_count}</Table.Td>
                  <Table.Td>{batch.flagged_count}</Table.Td>
                  <Table.Td>{batch.rejected_count}</Table.Td>
                </Table.Tr>
              ))}
              {query.data.items.length === 0 && (
                <Table.Tr>
                  <Table.Td colSpan={7}>
                    <EmptyState
                      icon={ClockCounterClockwise}
                      title="No imports have been run yet"
                      body="Once an admissions manager uploads an Excel file, the batch will appear here with its create/update/flag counts."
                    />
                  </Table.Td>
                </Table.Tr>
              )}
            </Table.Tbody>
            </Table>
          </Table.ScrollContainer>

          <Group justify="space-between">
            <Text size="sm" c="dimmed">
              {query.data.total === 0
                ? "0 results"
                : `Showing ${offset + 1}-${Math.min(offset + PAGE_SIZE, query.data.total)} of ${query.data.total}`}
            </Text>
            <Pagination value={page} onChange={setPage} total={totalPages} />
          </Group>
        </>
      )}
    </Stack>
  );
}
