import { Stack, Title, Text } from "@mantine/core";

/** Placeholder -- the payment-claim workflow and reconciliation view are
 * later modules' scope. This module only establishes the route and its
 * role-gated nav entry point.
 */
export function FinancePage() {
  return (
    <Stack>
      <Title order={2}>Finance</Title>
      <Text c="dimmed">
        Payment claims and reconciliation arrive in a later module.
      </Text>
    </Stack>
  );
}
