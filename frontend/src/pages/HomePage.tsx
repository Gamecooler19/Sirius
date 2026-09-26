/** Module 13: the one screen every authenticated user lands on regardless
 * of role, redesigned as a composed intro state (icon + headline + one
 * line of body) using the same visual language as `EmptyState` (DESIGN.md
 * SS5) rather than left as plain unstyled `<Title>`/`<Text>` -- this page
 * has always been legitimately "empty" of any real data, and treating it
 * as an oversight rather than a first-class state is exactly what
 * DESIGN.md's empty-state principle exists to fix.
 */

import { Stack, Title, Text } from "@mantine/core";
import { Compass } from "@phosphor-icons/react";

export function HomePage() {
  return (
    <Stack
      align="center"
      gap="xs"
      py={64}
      px="xl"
      style={{
        background: "#f3f8fa",
        borderRadius: "12px",
        textAlign: "center",
        maxWidth: 480,
        margin: "0 auto",
      }}
    >
      <Compass size={32} weight="light" color="#58666d" />
      <Title order={3} style={{ letterSpacing: "-0.01em" }}>
        Welcome to Sirius
      </Title>
      <Text size="sm" c="#58666d" maw="42ch">
        Pick a section from the nav on the left to get started.
      </Text>
    </Stack>
  );
}
