/**
 * Module 13 signature component (DESIGN.md SS5 "Empty States"): a composed
 * icon + headline + one line of body text inside a Steel Surface card,
 * replacing the bare "No X match these filters" text row every list page
 * shipped in Module 12 (v1) and earlier. This is the concrete fix DESIGN.md
 * SS1 calls out by name as what v1 got wrong.
 *
 * Used inside a `<Table.Tr><Table.Td colSpan={N}>` on every table screen
 * that can be legitimately empty, so it renders inline with the table
 * rather than replacing the whole page (filters/controls stay visible and
 * usable while the table body shows this instead of rows).
 */

import type { Icon } from "@phosphor-icons/react";
import { Stack, Text } from "@mantine/core";

interface EmptyStateProps {
  icon: Icon;
  title: string;
  body: string;
}

export function EmptyState({ icon: IconComponent, title, body }: EmptyStateProps) {
  return (
    <Stack
      align="center"
      gap="xs"
      py={40}
      px="xl"
      style={{
        background: "#f3f8fa",
        borderRadius: "12px",
        textAlign: "center",
      }}
    >
      <IconComponent size={32} weight="light" color="#58666d" />
      <Text fw={600} size="lg" c="#0c181d" style={{ letterSpacing: "-0.01em" }}>
        {title}
      </Text>
      <Text size="sm" c="#58666d" maw="42ch">
        {body}
      </Text>
    </Stack>
  );
}
