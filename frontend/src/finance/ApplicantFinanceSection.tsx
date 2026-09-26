/** Finance section of `ApplicantDetailDrawer`: shows the applicant's own
 * `finance_record` (if one exists) via the real `GET /applicants/{id}/finance`,
 * a read-only list of its claims (no confirm/reject controls here -- that
 * action lives only on `FinancePage`, matching the review-queue design),
 * and a submit-new-claim form visible only to `PAYMENT_SUBMIT_ROLES`.
 *
 * A 404 is the documented, expected empty state for "most applicants,
 * anyone who never reached ADMISSION_TAKEN" -- rendered as plain
 * explanatory text, not an error `Alert`.
 */

import { useState } from "react";
import {
  Alert,
  Badge,
  Button,
  Center,
  Divider,
  Group,
  Loader,
  NumberInput,
  Select,
  Stack,
  Table,
  Text,
  TextInput,
} from "@mantine/core";
import { CheckCircle, WarningCircle } from "@phosphor-icons/react";
import { ApiError } from "../api/client";
import type { PaymentMode } from "../api/types";
import { useMe } from "../api/useMe";
import { PAYMENT_SUBMIT_ROLES, hasRole } from "../auth/roles";
import { useApplicantFinance, useSubmitPaymentClaim } from "./useFinance";

const PAYMENT_MODES: PaymentMode[] = ["CASH", "CHEQUE", "BANK_TRANSFER", "UPI", "CARD", "OTHER"];

const CLAIM_STATUS_COLORS: Record<string, string> = {
  PENDING: "yellow",
  CONFIRMED: "green",
  REJECTED: "red",
};

export function ApplicantFinanceSection({ applicantId }: { applicantId: string }) {
  const meQuery = useMe();
  const financeQuery = useApplicantFinance(applicantId);
  const submitMutation = useSubmitPaymentClaim(applicantId);

  const [amount, setAmount] = useState<number | string>("");
  const [paymentMode, setPaymentMode] = useState<PaymentMode | null>(null);
  const [referenceNumber, setReferenceNumber] = useState("");
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [submitSuccess, setSubmitSuccess] = useState(false);

  const canSubmit = meQuery.data ? hasRole(meQuery.data.role_code, PAYMENT_SUBMIT_ROLES) : false;

  if (financeQuery.isLoading) {
    return (
      <Center py="md">
        <Loader size="sm" />
      </Center>
    );
  }

  if (financeQuery.notFound) {
    return (
      <Text size="sm" c="dimmed">
        No finance record yet -- created automatically once this applicant
        reaches Admission Taken.
      </Text>
    );
  }

  if (financeQuery.isError) {
    return (
      <Alert color="red" icon={<WarningCircle size={18} weight="light" />}>
        {financeQuery.error instanceof ApiError
          ? financeQuery.error.message
          : "failed to load finance record"}
      </Alert>
    );
  }

  const finance = financeQuery.data;
  if (!finance) return null;

  const outstanding = (Number(finance.total_fee_due) - Number(finance.total_paid)).toFixed(2);

  async function handleSubmit() {
    if (!finance || !paymentMode || amount === "") return;
    setSubmitError(null);
    setSubmitSuccess(false);
    try {
      await submitMutation.mutateAsync({
        finance_record_id: finance.finance_record_id,
        amount: String(amount),
        payment_mode: paymentMode,
        reference_number: referenceNumber.trim() || null,
      });
      setSubmitSuccess(true);
      setAmount("");
      setPaymentMode(null);
      setReferenceNumber("");
    } catch (e) {
      setSubmitError(e instanceof ApiError ? e.message : "failed to submit claim");
    }
  }

  return (
    <Stack gap="sm">
      <Group gap="xl">
        <Stack gap={0}>
          <Text size="xs" c="dimmed">
            Fee due
          </Text>
          <Text fw={700}>{finance.total_fee_due}</Text>
        </Stack>
        <Stack gap={0}>
          <Text size="xs" c="dimmed">
            Paid
          </Text>
          <Text fw={700}>{finance.total_paid}</Text>
        </Stack>
        <Stack gap={0}>
          <Text size="xs" c="dimmed">
            Outstanding
          </Text>
          <Text fw={700}>{outstanding}</Text>
        </Stack>
      </Group>

      {finance.payment_claims.length === 0 ? (
        <Text size="sm" c="dimmed">
          No payment claims submitted yet.
        </Text>
      ) : (
        <Table striped withTableBorder>
          <Table.Thead>
            <Table.Tr>
              <Table.Th>Amount</Table.Th>
              <Table.Th>Mode</Table.Th>
              <Table.Th>Reference</Table.Th>
              <Table.Th>Status</Table.Th>
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {finance.payment_claims.map((claim) => (
              <Table.Tr key={claim.id}>
                <Table.Td>{claim.amount}</Table.Td>
                <Table.Td>{claim.payment_mode}</Table.Td>
                <Table.Td>{claim.reference_number ?? "\u2014"}</Table.Td>
                <Table.Td>
                  <Badge color={CLAIM_STATUS_COLORS[claim.status] ?? "gray"} variant="light">
                    {claim.status}
                  </Badge>
                </Table.Td>
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
      )}

      {canSubmit && (
        <>
          <Divider label="Submit a new claim" />

          {submitError && (
            <Alert color="red" icon={<WarningCircle size={16} weight="light" />}>
              {submitError}
            </Alert>
          )}
          {submitSuccess && (
            <Alert color="green" icon={<CheckCircle size={16} weight="light" />}>
              Claim submitted.
            </Alert>
          )}

          <Group align="flex-end" gap="xs">
            <NumberInput
              label="Amount"
              placeholder="0.00"
              value={amount}
              onChange={setAmount}
              min={0}
              decimalScale={2}
              w={140}
            />
            <Select
              label="Payment mode"
              placeholder="Select mode"
              data={PAYMENT_MODES.map((m) => ({ value: m, label: m }))}
              value={paymentMode}
              onChange={(value) => setPaymentMode(value as PaymentMode | null)}
              w={160}
            />
            <TextInput
              label="Reference (optional)"
              value={referenceNumber}
              onChange={(e) => setReferenceNumber(e.currentTarget.value)}
              w={160}
            />
          </Group>
          <Button
            onClick={handleSubmit}
            loading={submitMutation.isPending}
            disabled={!paymentMode || amount === ""}
          >
            Submit claim
          </Button>
        </>
      )}
    </Stack>
  );
}
