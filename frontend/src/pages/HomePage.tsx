import { Stack, Title, Text } from "@mantine/core";

export function HomePage() {
  return (
    <Stack>
      <Title order={2}>Welcome</Title>
      <Text c="dimmed">
        Pick a section from the nav on the left. Data pages (applicant list,
        status transitions, payment workflow, reconciliation) arrive in
        later modules -- this module is auth and shell only.
      </Text>
    </Stack>
  );
}
