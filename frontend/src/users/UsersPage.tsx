/** Users page (Module 15): `SUPER_ADMIN`-only administration screen --
 * list, create, activate/deactivate, and reset-TOTP, wired to the real
 * `GET /users`/`POST /users`/`PATCH /users/{id}`/
 * `POST /users/{id}/reset-totp` endpoints (`api/app/routers/users.py`).
 *
 * The activate/deactivate and self-lockout-guard UX here is a
 * convenience mirror of the backend's own real guard
 * (`app.routers.users.update_user`), not a substitute for it: the
 * "Deactivate" action is disabled (not hidden) for the signed-in
 * `SUPER_ADMIN`'s own row, with a tooltip explaining why, but the
 * backend's own 422 is what actually enforces the rule -- confirmed live
 * (see `reports/module-15-user-management.md`) by calling the endpoint
 * directly against the signed-in account and observing the real
 * rejection, not merely trusting this UI-level disable.
 *
 * Reuses Module 13's design system throughout: `Table.ScrollContainer`
 * (the real fix Module 13's own follow-up established for narrow-
 * viewport table usability), the `EmptyState` component, `Card`/
 * `SimpleGrid` spacing tokens -- no new ad hoc styling.
 */

import { useState } from "react";
import {
  Alert,
  Badge,
  Button,
  Center,
  Group,
  Loader,
  Modal,
  Pagination,
  Select,
  Stack,
  Table,
  Text,
  TextInput,
  Title,
  Tooltip,
} from "@mantine/core";
import { useForm } from "@mantine/form";
import {
  ArrowClockwise,
  CheckCircle,
  Prohibit,
  UsersThree,
  WarningCircle,
} from "@phosphor-icons/react";
import { ApiError } from "../api/client";
import { useMe } from "../api/useMe";
import type { RoleCode, UserSummary } from "../api/types";
import { MANDATORY_TOTP_ROLES } from "../auth/roles";
import { EmptyState } from "../components/EmptyState";
import { useCreateUser, useResetTotp, useUpdateUser, useUsersList } from "./useUsers";

const PAGE_SIZE = 10;

const ALL_ROLES: RoleCode[] = [
  "SUPER_ADMIN",
  "ADMISSIONS_MANAGER",
  "ADMISSIONS_COUNSELOR",
  "FINANCE_STAFF",
  "FINANCE_MANAGER",
  "AUDITOR",
];

function CreateUserForm({ onDone }: { onDone: () => void }) {
  const createUser = useCreateUser();
  const [error, setError] = useState<string | null>(null);

  const form = useForm({
    initialValues: {
      email: "",
      full_name: "",
      password: "",
      role_code: "" as RoleCode | "",
    },
  });

  async function handleSubmit(values: typeof form.values) {
    if (!values.role_code) return;
    setError(null);
    try {
      await createUser.mutateAsync({
        email: values.email,
        full_name: values.full_name,
        password: values.password,
        role_code: values.role_code,
      });
      form.reset();
      onDone();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "failed to create user");
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
        <TextInput label="Email" required {...form.getInputProps("email")} />
        <TextInput label="Full name" required {...form.getInputProps("full_name")} />
        <TextInput
          label="Initial password"
          required
          type="password"
          {...form.getInputProps("password")}
        />
        <Select
          label="Role"
          required
          placeholder="Select role"
          data={ALL_ROLES.map((r) => ({ value: r, label: r }))}
          {...form.getInputProps("role_code")}
        />
        <Button type="submit" loading={createUser.isPending}>
          Create user
        </Button>
      </Stack>
    </form>
  );
}

export function UsersPage() {
  const meQuery = useMe();
  const [page, setPage] = useState(1);
  const [createOpen, setCreateOpen] = useState(false);
  const [rowError, setRowError] = useState<{ userId: string; message: string } | null>(null);

  const offset = (page - 1) * PAGE_SIZE;
  const query = useUsersList({ limit: PAGE_SIZE, offset });
  const updateUser = useUpdateUser();
  const resetTotp = useResetTotp();

  const totalPages = query.data ? Math.max(1, Math.ceil(query.data.total / PAGE_SIZE)) : 1;
  const selfId = meQuery.data?.user_id;

  async function handleToggleActive(user: UserSummary) {
    setRowError(null);
    try {
      await updateUser.mutateAsync({ id: user.id, body: { is_active: !user.is_active } });
    } catch (e) {
      // The backend's own self-lockout-guard 422 ("cannot deactivate
      // your own account through this endpoint") surfaces here verbatim
      // if this action is somehow reached despite the disabled-button
      // UI guard below -- this row-level alert is not a rewritten
      // message.
      setRowError({
        userId: user.id,
        message: e instanceof ApiError ? e.message : "failed to update user",
      });
    }
  }

  async function handleResetTotp(user: UserSummary) {
    setRowError(null);
    try {
      await resetTotp.mutateAsync(user.id);
    } catch (e) {
      setRowError({
        userId: user.id,
        message: e instanceof ApiError ? e.message : "failed to reset TOTP",
      });
    }
  }

  return (
    <Stack>
      <Group justify="space-between">
        <Title order={2}>Users</Title>
        <Button onClick={() => setCreateOpen(true)}>Create user</Button>
      </Group>

      <Modal opened={createOpen} onClose={() => setCreateOpen(false)} title="Create user">
        <CreateUserForm onDone={() => setCreateOpen(false)} />
      </Modal>

      {query.isError && (
        <Alert color="red" icon={<WarningCircle size={20} weight="light" />}>
          {query.error instanceof ApiError ? query.error.message : "failed to load users"}
        </Alert>
      )}

      {query.isLoading && (
        <Center py="xl">
          <Loader />
        </Center>
      )}

      {query.data && (
        <>
          <Table.ScrollContainer minWidth={820}>
            <Table striped highlightOnHover withTableBorder>
              <Table.Thead>
                <Table.Tr>
                  <Table.Th>Email</Table.Th>
                  <Table.Th>Full name</Table.Th>
                  <Table.Th>Role</Table.Th>
                  <Table.Th>Status</Table.Th>
                  <Table.Th>2FA</Table.Th>
                  <Table.Th>Actions</Table.Th>
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {query.data.items.map((user) => {
                  const isSelf = user.id === selfId;
                  const mandatoryTotp = MANDATORY_TOTP_ROLES.includes(user.role_code);
                  return (
                    <Table.Tr key={user.id}>
                      <Table.Td>{user.email}</Table.Td>
                      <Table.Td>{user.full_name}</Table.Td>
                      <Table.Td>
                        <Badge variant="light">{user.role_code}</Badge>
                      </Table.Td>
                      <Table.Td>
                        <Badge color={user.is_active ? "green" : "red"} variant="light">
                          {user.is_active ? "Active" : "Inactive"}
                        </Badge>
                      </Table.Td>
                      <Table.Td>
                        <Badge color={user.totp_enabled ? "green" : "gray"} variant="light">
                          {user.totp_enabled ? "Enrolled" : "Not enrolled"}
                        </Badge>
                      </Table.Td>
                      <Table.Td>
                        <Group gap="xs" wrap="nowrap">
                          <Tooltip
                            label={
                              isSelf
                                ? "You cannot deactivate your own account"
                                : user.is_active
                                  ? "Deactivate this account"
                                  : "Reactivate this account"
                            }
                          >
                            <Button
                              size="xs"
                              variant="light"
                              color={user.is_active ? "red" : "green"}
                              disabled={isSelf && user.is_active}
                              leftSection={
                                user.is_active ? (
                                  <Prohibit size={14} weight="light" />
                                ) : (
                                  <CheckCircle size={14} weight="light" />
                                )
                              }
                              loading={updateUser.isPending}
                              onClick={() => handleToggleActive(user)}
                            >
                              {user.is_active ? "Deactivate" : "Activate"}
                            </Button>
                          </Tooltip>
                          {mandatoryTotp && (
                            <Button
                              size="xs"
                              variant="light"
                              leftSection={<ArrowClockwise size={14} weight="light" />}
                              loading={resetTotp.isPending}
                              onClick={() => handleResetTotp(user)}
                            >
                              Reset TOTP
                            </Button>
                          )}
                        </Group>
                      </Table.Td>
                    </Table.Tr>
                  );
                })}
                {query.data.items.map(
                  (user) =>
                    rowError &&
                    rowError.userId === user.id && (
                      <Table.Tr key={`${user.id}-error`}>
                        <Table.Td colSpan={6}>
                          <Alert color="red" icon={<WarningCircle size={16} weight="light" />} py="xs">
                            {rowError.message}
                          </Alert>
                        </Table.Td>
                      </Table.Tr>
                    ),
                )}
                {query.data.items.length === 0 && (
                  <Table.Tr>
                    <Table.Td colSpan={6}>
                      <EmptyState
                        icon={UsersThree}
                        title="No users found"
                        body="Create the first account using the button above."
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
