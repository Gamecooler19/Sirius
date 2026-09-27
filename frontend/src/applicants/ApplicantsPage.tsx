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
  Button,
  Group,
  Modal,
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
import { useForm } from "@mantine/form";
import { WarningCircle, UsersThree } from "@phosphor-icons/react";
import { ApiError } from "../api/client";
import { useMe } from "../api/useMe";
import type { ApplicationStatus } from "../api/types";
import { useApplicantsList, useAssignableCounselors, useCreateApplicant } from "./useApplicants";
import { ALL_STATUSES } from "./statusTransitions";
import { ApplicantDetailDrawer } from "./ApplicantDetailDrawer";
import { EmptyState } from "../components/EmptyState";
import { APPLICANTS_ROLES, hasRole } from "../auth/roles";

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

/** `POST /applicants` form (Module 19) -- the manual single-applicant
 * creation path for a counselor taking a walk-in/phone inquiry, or a
 * manager/admin entering one on someone's behalf. Gated on the same
 * `APPLICANTS_ROLES` set the nav link and status-transition workflow
 * already use (`app.routers.applicant_create`'s own `_CREATE_ROLES`
 * mirrors that exact set) -- see `auth/roles.ts`'s own docstring for
 * why this whole page already assumes that role scope.
 *
 * **The "assign to" field only renders for `SUPER_ADMIN`/
 * `ADMISSIONS_MANAGER`** (`useAssignableCounselors`, backed by
 * `GET /applicants/counselors`) -- an `ADMISSIONS_COUNSELOR` caller is
 * always auto-assigned to themselves by the backend regardless of what
 * this form sends (see that router's own docstring), so showing this
 * role a picker it has no effect on would only be confusing, not
 * merely redundant.
 */
function NewApplicantForm({ onDone }: { onDone: () => void }) {
  const meQuery = useMe();
  const role = meQuery.data?.role_code;
  const canAssignOthers = role === "SUPER_ADMIN" || role === "ADMISSIONS_MANAGER";

  const counselorsQuery = useAssignableCounselors(canAssignOthers);
  const createApplicant = useCreateApplicant();
  const [error, setError] = useState<string | null>(null);

  const form = useForm({
    initialValues: {
      full_name: "",
      email: "",
      phone: "",
      program: "",
      intake_cycle: "",
      assigned_counselor_id: "" as string | "",
    },
  });

  async function handleSubmit(values: typeof form.values) {
    setError(null);
    try {
      await createApplicant.mutateAsync({
        full_name: values.full_name,
        email: values.email,
        phone: values.phone.trim() || null,
        program: values.program,
        intake_cycle: values.intake_cycle,
        assigned_counselor_id:
          canAssignOthers && values.assigned_counselor_id
            ? values.assigned_counselor_id
            : undefined,
      });
      form.reset();
      onDone();
    } catch (e) {
      // The backend's own real rejection text surfaces here verbatim --
      // e.g. a 409 naming the conflicting applicant's id on a
      // duplicate phone/email, or a 422 on an invalid
      // assigned_counselor_id -- not a rewritten generic message.
      setError(e instanceof ApiError ? e.message : "failed to create applicant");
    }
  }

  return (
    <form onSubmit={form.onSubmit(handleSubmit)}>
      <Stack gap="sm">
        {error && (
          <Alert color="red" icon={<WarningCircle size={18} weight="light" />}>
            {error}
          </Alert>
        )}
        {!canAssignOthers && (
          <Text size="sm" c="dimmed">
            This applicant will be assigned to you automatically.
          </Text>
        )}
        <TextInput label="Full name" required {...form.getInputProps("full_name")} />
        <TextInput label="Email" type="email" required {...form.getInputProps("email")} />
        <TextInput label="Phone" placeholder="Optional" {...form.getInputProps("phone")} />
        <TextInput label="Program" required {...form.getInputProps("program")} />
        <TextInput
          label="Intake cycle"
          placeholder="e.g. Fall2026"
          required
          {...form.getInputProps("intake_cycle")}
        />
        {canAssignOthers && (
          <Select
            label="Assign to counselor"
            placeholder="Leave unassigned"
            clearable
            data={
              counselorsQuery.data?.map((c) => ({ value: c.id, label: c.full_name })) ?? []
            }
            disabled={counselorsQuery.isLoading}
            {...form.getInputProps("assigned_counselor_id")}
          />
        )}
        <Button type="submit" loading={createApplicant.isPending}>
          Create applicant
        </Button>
      </Stack>
    </form>
  );
}

export function ApplicantsPage() {
  const meQuery = useMe();
  const canCreate = meQuery.data ? hasRole(meQuery.data.role_code, APPLICANTS_ROLES) : false;
  const [createOpen, setCreateOpen] = useState(false);
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
      <Group justify="space-between">
        <Title order={2}>Applicants</Title>
        {canCreate && (
          <Button onClick={() => setCreateOpen(true)}>New applicant</Button>
        )}
      </Group>

      <Modal opened={createOpen} onClose={() => setCreateOpen(false)} title="New applicant">
        <NewApplicantForm onDone={() => setCreateOpen(false)} />
      </Modal>

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
          <Table.ScrollContainer minWidth={700}>
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

      <ApplicantDetailDrawer
        applicantId={selectedId}
        onClose={() => setSelectedId(null)}
      />
    </Stack>
  );
}
