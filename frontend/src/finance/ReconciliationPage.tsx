/** Finance reconciliation dashboard: the real `GET /finance/reconciliation`
 * (Module 05) rendered as a totals summary followed by a per-cycle
 * breakdown table. This endpoint has no pagination and no filters at all
 * (see `useReconciliation`'s own docstring) -- no page controls, no
 * status/cycle filter inputs are built here, since there is nothing on
 * the backend for them to drive.
 *
 * Money fields are rendered as the raw decimal string the backend
 * already returns (e.g. `"800000.00"`), matching the only formatting
 * convention this app's existing finance UI established
 * (`ApplicantFinanceSection`/`FinancePage` from Module 09 both render
 * `total_fee_due`/`total_paid`/`amount` as-is, with no `Intl.NumberFormat`
 * or currency symbol anywhere) -- reused here rather than inventing a
 * second convention for the same kind of field in the same app.
 *
 * Per-cycle rows are sorted alphabetically by `intake_cycle` on the
 * frontend explicitly (not merely relying on the backend's own sort,
 * even though `app.routers.reconciliation.get_reconciliation` does
 * already sort this way) -- a stable, sensible, and self-documenting
 * order regardless of what the backend happens to return.
 */

import { Alert, Card, Center, Loader, SimpleGrid, Stack, Table, Text, Title } from "@mantine/core";
import { WarningCircle, ChartLine } from "@phosphor-icons/react";
import { ApiError } from "../api/client";
import type { PaymentClaimStatus, ReconciliationCycle, ReconciliationTotals } from "../api/types";
import { useReconciliation } from "./useReconciliation";
import { EmptyState } from "../components/EmptyState";

const STATUS_ORDER: PaymentClaimStatus[] = ["PENDING", "CONFIRMED", "REJECTED"];

function amountFor(row: ReconciliationCycle | ReconciliationTotals, status: PaymentClaimStatus) {
  return row.claims_by_status.find((b) => b.status === status) ?? { count: 0, amount: "0" };
}

function TotalsCards({ totals }: { totals: ReconciliationTotals }) {
  return (
    <Stack gap="md">
      <SimpleGrid cols={{ base: 2, sm: 4 }} spacing="md">
        <Card withBorder padding="lg">
          <Text size="xs" c="dimmed">
            Finance records
          </Text>
          <Text size="xl" fw={700}>
            {totals.finance_record_count}
          </Text>
        </Card>
        <Card withBorder padding="lg">
          <Text size="xs" c="dimmed">
            Fee due
          </Text>
          <Text size="xl" fw={700}>
            {totals.total_fee_due}
          </Text>
        </Card>
        <Card withBorder padding="lg">
          <Text size="xs" c="dimmed">
            Paid
          </Text>
          <Text size="xl" fw={700}>
            {totals.total_paid}
          </Text>
        </Card>
        <Card withBorder padding="lg">
          <Text size="xs" c="dimmed">
            Outstanding
          </Text>
          <Text size="xl" fw={700}>
            {totals.outstanding}
          </Text>
        </Card>
      </SimpleGrid>

      <SimpleGrid cols={{ base: 1, sm: 3 }} spacing="md">
        {STATUS_ORDER.map((status) => {
          const bucket = amountFor(totals, status);
          return (
            <Card withBorder padding="lg" key={status}>
              <Text size="xs" c="dimmed">
                {status}
              </Text>
              <Text size="lg" fw={700}>
                {bucket.count} claim{bucket.count === 1 ? "" : "s"}
              </Text>
              <Text size="sm" c="dimmed">
                {bucket.amount}
              </Text>
            </Card>
          );
        })}
      </SimpleGrid>
    </Stack>
  );
}

export function ReconciliationPage() {
  const query = useReconciliation();

  const sortedCycles = query.data
    ? [...query.data.cycles].sort((a, b) => a.intake_cycle.localeCompare(b.intake_cycle))
    : [];

  return (
    <Stack>
      <Title order={2}>Reconciliation</Title>

      {query.isError && (
        <Alert color="red" icon={<WarningCircle size={20} weight="light" />}>
          {query.error instanceof ApiError ? query.error.message : "failed to load reconciliation"}
        </Alert>
      )}

      {query.isLoading && (
        <Center py="xl">
          <Loader />
        </Center>
      )}

      {query.data && (
        <>
          <TotalsCards totals={query.data.totals} />

          <Title order={4} mt="md">
            By intake cycle
          </Title>

          <Table.ScrollContainer minWidth={800}>
            <Table striped highlightOnHover withTableBorder>
            <Table.Thead>
              <Table.Tr>
                <Table.Th>Intake cycle</Table.Th>
                <Table.Th>Finance records</Table.Th>
                <Table.Th>Fee due</Table.Th>
                <Table.Th>Paid</Table.Th>
                <Table.Th>Outstanding</Table.Th>
                <Table.Th>Pending</Table.Th>
                <Table.Th>Confirmed</Table.Th>
                <Table.Th>Rejected</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {sortedCycles.map((cycle) => (
                <Table.Tr key={cycle.intake_cycle}>
                  <Table.Td fw={600}>{cycle.intake_cycle}</Table.Td>
                  <Table.Td>{cycle.finance_record_count}</Table.Td>
                  <Table.Td>{cycle.total_fee_due}</Table.Td>
                  <Table.Td>{cycle.total_paid}</Table.Td>
                  <Table.Td>{cycle.outstanding}</Table.Td>
                  {STATUS_ORDER.map((status) => {
                    const bucket = amountFor(cycle, status);
                    return (
                      <Table.Td key={status}>
                        <Text size="sm">{bucket.count}</Text>
                        <Text size="xs" c="dimmed">
                          {bucket.amount}
                        </Text>
                      </Table.Td>
                    );
                  })}
                </Table.Tr>
              ))}
              {sortedCycles.length === 0 && (
                <Table.Tr>
                  <Table.Td colSpan={8}>
                    <EmptyState
                      icon={ChartLine}
                      title="No finance records exist yet"
                      body="Reconciliation totals will populate here once applicants have finance records to summarize."
                    />
                  </Table.Td>
                </Table.Tr>
              )}
            </Table.Tbody>
            </Table>
          </Table.ScrollContainer>
        </>
      )}
    </Stack>
  );
}
