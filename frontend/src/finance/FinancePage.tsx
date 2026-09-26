/** Finance review queue: a real Mantine `Table` driven by
 * `usePaymentClaimsList`, against the live `GET /finance/payment-claims`
 * endpoint. Paginated and status-filterable using the same table/
 * pagination shape `ApplicantsPage` (Module 07) and `ImportHistoryPage`
 * (Module 08) already established. Each `PENDING` row shows Confirm/
 * Reject buttons only when the logged-in user is in
 * `PAYMENT_RESOLVE_ROLES` -- a role outside that set (most visibly
 * `FINANCE_STAFF`, who can submit claims but never resolve any) sees no
 * buttons on that row at all, not disabled ones that would imply
 * near-access.
 */

import { useState } from "react";
import {
  Alert,
  Badge,
  Button,
  Center,
  Group,
  Loader,
  Pagination,
  Select,
  Stack,
  Table,
  Text,
  Title,
} from "@mantine/core";
import { Check, WarningCircle, X, CurrencyCircleDollar } from "@phosphor-icons/react";
import { ApiError } from "../api/client";
import type { PaymentClaimStatus } from "../api/types";
import { useMe } from "../api/useMe";
import { PAYMENT_RESOLVE_ROLES, hasRole } from "../auth/roles";
import { usePaymentClaimsList, useResolvePaymentClaim } from "./useFinance";
import { EmptyState } from "../components/EmptyState";

const PAGE_SIZE = 10;

const STATUS_OPTIONS: PaymentClaimStatus[] = ["PENDING", "CONFIRMED", "REJECTED"];

const STATUS_COLORS: Record<PaymentClaimStatus, string> = {
  PENDING: "yellow",
  CONFIRMED: "green",
  REJECTED: "red",
};

export function FinancePage() {
  const meQuery = useMe();
  const [page, setPage] = useState(1);
  const [statusFilter, setStatusFilter] = useState<PaymentClaimStatus | null>(null);
  const [rowError, setRowError] = useState<{ claimId: string; message: string } | null>(null);

  const offset = (page - 1) * PAGE_SIZE;
  const query = usePaymentClaimsList({ limit: PAGE_SIZE, offset, status: statusFilter });
  const resolveMutation = useResolvePaymentClaim();

  const totalPages = query.data ? Math.max(1, Math.ceil(query.data.total / PAGE_SIZE)) : 1;
  const canResolve = meQuery.data ? hasRole(meQuery.data.role_code, PAYMENT_RESOLVE_ROLES) : false;

  function resetToFirstPage() {
    setPage(1);
  }

  async function handleResolve(claimId: string, action: "confirm" | "reject") {
    setRowError(null);
    try {
      await resolveMutation.mutateAsync({ claimId, action, body: {} });
    } catch (e) {
      // The backend's own maker-checker 422
      // ("cannot confirm or reject a payment claim you submitted
      // yourself") and "not PENDING" 422 both surface here verbatim --
      // this row-level alert is not a rewritten message.
      setRowError({
        claimId,
        message: e instanceof ApiError ? e.message : "failed to resolve claim",
      });
    }
  }

  return (
    <Stack>
      <Title order={2}>Finance</Title>

      <Group align="flex-end">
        <Select
          label="Status"
          placeholder="All statuses"
          clearable
          data={STATUS_OPTIONS.map((s) => ({ value: s, label: s }))}
          value={statusFilter}
          onChange={(value) => {
            setStatusFilter(value as PaymentClaimStatus | null);
            resetToFirstPage();
          }}
          w={200}
        />
      </Group>

      {query.isError && (
        <Alert color="red" icon={<WarningCircle size={20} weight="light" />}>
          {query.error instanceof ApiError ? query.error.message : "failed to load payment claims"}
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
                <Table.Th>Submitted</Table.Th>
                <Table.Th>Amount</Table.Th>
                <Table.Th>Mode</Table.Th>
                <Table.Th>Reference</Table.Th>
                <Table.Th>Status</Table.Th>
                <Table.Th>Submitted by</Table.Th>
                <Table.Th>Resolved by</Table.Th>
                {canResolve && <Table.Th>Actions</Table.Th>}
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {query.data.items.map((claim) => (
                <Table.Tr key={claim.id}>
                  <Table.Td>
                    <Text size="xs" c="dimmed">
                      {new Date(claim.created_at).toLocaleString()}
                    </Text>
                  </Table.Td>
                  <Table.Td>{claim.amount}</Table.Td>
                  <Table.Td>{claim.payment_mode}</Table.Td>
                  <Table.Td>{claim.reference_number ?? "\u2014"}</Table.Td>
                  <Table.Td>
                    <Badge color={STATUS_COLORS[claim.status]} variant="light">
                      {claim.status}
                    </Badge>
                  </Table.Td>
                  <Table.Td>
                    <Text size="xs" ff="monospace">
                      {claim.submitted_by}
                    </Text>
                  </Table.Td>
                  <Table.Td>
                    <Text size="xs" ff="monospace" c="dimmed">
                      {claim.confirmed_by ?? "\u2014"}
                    </Text>
                  </Table.Td>
                  {canResolve && (
                    <Table.Td>
                      {claim.status === "PENDING" ? (
                        <Group gap="xs" wrap="nowrap">
                          <Button
                            size="xs"
                            color="green"
                            variant="light"
                            leftSection={<Check size={14} weight="light" />}
                            loading={resolveMutation.isPending}
                            onClick={() => handleResolve(claim.id, "confirm")}
                          >
                            Confirm
                          </Button>
                          <Button
                            size="xs"
                            color="red"
                            variant="light"
                            leftSection={<X size={14} weight="light" />}
                            loading={resolveMutation.isPending}
                            onClick={() => handleResolve(claim.id, "reject")}
                          >
                            Reject
                          </Button>
                        </Group>
                      ) : (
                        <Text size="xs" c="dimmed">
                          {"\u2014"}
                        </Text>
                      )}
                    </Table.Td>
                  )}
                </Table.Tr>
              ))}
              {query.data.items.map(
                (claim) =>
                  rowError &&
                  rowError.claimId === claim.id && (
                    <Table.Tr key={`${claim.id}-error`}>
                      <Table.Td colSpan={canResolve ? 8 : 7}>
                        <Alert color="red" icon={<WarningCircle size={16} weight="light" />} py="xs">
                          {rowError.message}
                        </Alert>
                      </Table.Td>
                    </Table.Tr>
                  ),
              )}
              {query.data.items.length === 0 && (
                <Table.Tr>
                  <Table.Td colSpan={canResolve ? 8 : 7}>
                    <EmptyState
                      icon={CurrencyCircleDollar}
                      title="No payment claims match this filter"
                      body="Try clearing the status filter, or check back once a claim has been submitted."
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
    </Stack>
  );
}
