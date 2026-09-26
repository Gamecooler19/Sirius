import { Stack, Title, Text } from "@mantine/core";

/** Placeholder -- the applicant list, detail, and status-transition UI are
 * later modules' scope. This module only establishes the route and its
 * role-gated nav entry point.
 */
export function ApplicantsPage() {
  return (
    <Stack>
      <Title order={2}>Applicants</Title>
      <Text c="dimmed">
        Applicant list and status transitions arrive in a later module.
      </Text>
    </Stack>
  );
}
