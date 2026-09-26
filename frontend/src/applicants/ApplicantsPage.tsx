/** Applicant list: a real Mantine `Table` driven by `useApplicantsList`,
 * against the live `GET /applicants` endpoint. Paginated using the API's
 * own `limit`/`offset` shape (not a client-side page abstraction layered
 * on top), filterable by exactly the three params
 * `app.routers.applicants_read.list_applicants` accepts --
 * `current_status`/`program`/`intake_cycle` -- no invented filter the
 * backend doesn't support. Clicking a row opens `ApplicantDetailDrawer`.
 */

import { useState } from "react";
import {
  Alert,
  Badge,
  Group,
  Pagination,
  Select,
  Stack,
  Table,
  Text,
  TextInput,
  Title,
  Loader,
  Center,
} from "@mantine/core";
import { WarningCircle, UsersThree } from "@phosphor-icons/react";
import { ApiError } from "../api/client";
import type { ApplicationStatus } from "../api/types";
import { useApplicantsList } from "./useApplicants";
import { ALL_STATUSES } from "./statusTransitions";
import { ApplicantDetailDrawer } from "./ApplicantDetailDrawer";
import { EmptyState } from "../components/EmptyState";

const PAGE_SIZE = 10;

const STATUS_COLORS: Record<ApplicationStatus, string> = {
  IMPORTED: "gray",
  APPLIED: "blue",
  IN_PROCESS: "yellow",
  ON_HOLD: "orange",
  ADMISSION_OFFERED: "grape",
  ADMISSION_TAKEN: "green",
  REJECTED: "red",
  WITHDRAWN: "dark",
};

export function ApplicantsPage() {
  const [page, setPage] = useState(1);
  const [statusFilter, setStatusFilter] = useState<ApplicationStatus | null>(null);
  const [programFilter, setProgramFilter] = useState("");
  const [intakeCycleFilter, setIntakeCycleFilter] = useState("");
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const offset = (page - 1) * PAGE_SIZE;

  const query = useApplicantsList({
    limit: PAGE_SIZE,
    offset,
    current_status: statusFilter,
    program: programFilter.trim() || null,
    intake_cycle: intakeCycleFilter.trim() || null,
  });

  const totalPages = query.data ? Math.max(1, Math.ceil(query.data.total / PAGE_SIZE)) : 1;

  function resetToFirstPage() {
    setPage(1);
  }

  return (
    <Stack>
      <Title order={2}>Applicants</Title>

      <Group align="flex-end">
        <Select
          label="Status"
          placeholder="All statuses"
          clearable
          data={ALL_STATUSES.map((s) => ({ value: s, label: s }))}
          value={statusFilter}
          onChange={(value) => {
            setStatusFilter(value as ApplicationStatus | null);
            resetToFirstPage();
          }}
          w={200}
        />
        <TextInput
          label="Program"
          placeholder="e.g. CS"
          value={programFilter}
          onChange={(e) => {
            setProgramFilter(e.currentTarget.value);
            resetToFirstPage();
          }}
          w={160}
        />
        <TextInput
          label="Intake cycle"
          placeholder="e.g. Fall2026"
          value={intakeCycleFilter}
          onChange={(e) => {
            setIntakeCycleFilter(e.currentTarget.value);
            resetToFirstPage();
          }}
          w={180}
        />
      </Group>

      {query.isError && (
        <Alert color="red" icon={<WarningCircle size={20} weight="light" />}>
          {query.error instanceof ApiError ? query.error.message : "failed to load applicants"}
        </Alert>
      )}

      {query.isLoading && (
        <Center py="xl">
          <Loader />
        </Center>
      )}

      {query.data && (
        <>
          <Table striped highlightOnHover withTableBorder>
            <Table.Thead>
              <Table.Tr>
                <Table.Th>Name</Table.Th>
                <Table.Th>Email</Table.Th>
                <Table.Th>Program</Table.Th>
                <Table.Th>Intake cycle</Table.Th>
                <Table.Th>Status</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {query.data.items.map((applicant) => (
                <Table.Tr
                  key={applicant.id}
                  onClick={() => setSelectedId(applicant.id)}
                  style={{ cursor: "pointer" }}
                >
                  <Table.Td>{applicant.full_name}</Table.Td>
                  <Table.Td>{applicant.email}</Table.Td>
                  <Table.Td>{applicant.program}</Table.Td>
                  <Table.Td>{applicant.intake_cycle}</Table.Td>
                  <Table.Td>
                    <Badge color={STATUS_COLORS[applicant.current_status]} variant="light">
                      {applicant.current_status}
                    </Badge>
                  </Table.Td>
                </Table.Tr>
              ))}
              {query.data.items.length === 0 && (
                <Table.Tr>
                  <Table.Td colSpan={5} style={{ cursor: "default" }}>
                    <EmptyState
                      icon={UsersThree}
                      title="No applicants match these filters"
                      body="Try clearing a filter, or check back once the next import batch has run."
                    />
                  </Table.Td>
                </Table.Tr>
              )}
            </Table.Tbody>
          </Table>

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

      <ApplicantDetailDrawer
        applicantId={selectedId}
        onClose={() => setSelectedId(null)}
      />
    </Stack>
  );
}
