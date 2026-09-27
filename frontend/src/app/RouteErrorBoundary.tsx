/** Module 21 audit finding, fixed here: react-router's own default
 * `errorElement` -- the fallback that renders when any route's element
 * throws a genuine unhandled exception during render -- was never
 * overridden anywhere in `router.tsx`. Confirmed live: forcing a real
 * `TypeError` inside `HomePage`'s own render (a malformed
 * `GET /applicants/summary` response shape, the same class of failure
 * a real backend/frontend contract drift would cause) did not produce
 * a blank white screen (the literal premise this audit set out to
 * check), but produced something almost as unusable for a real end
 * user: react-router's raw built-in fallback -- a full-page, top-to-
 * bottom JavaScript stack trace with zero app chrome (no header, no
 * nav, no logo) and, per that fallback's own on-screen text, an
 * explicit "Hey developer... you can provide a way better UX than
 * this" -- and **no interactable element of any kind** (confirmed via
 * a real accessibility-tree query returning zero results): a genuine
 * dead end, not a screen a non-technical user could recover from
 * without knowing to manually edit the URL bar.
 *
 * This component is that "way better UX" react-router's own fallback
 * is asking for, wired as every route's `errorElement` in
 * `router.tsx`. It deliberately does **not** try to recover render
 * state or retry the failed query automatically -- a render-time
 * exception means something is genuinely wrong with either the data
 * shape or the component itself, and silently retrying the exact same
 * render is likely to throw again; "reload the page" (a real, full
 * navigation, not a soft state reset) is the one recovery action that
 * is actually likely to work, since it re-runs the whole app from a
 * clean slate. `useRouteError` (react-router's own hook, not a
 * from-scratch parsing of the thrown value) is what actually captures
 * the error react-router already caught -- this component augments
 * react-router's own error boundary machinery with real UI, it does
 * not reimplement error catching from scratch.
 */

import { Alert, Button, Center, Stack, Text, Title } from "@mantine/core";
import { ArrowClockwise, WarningCircle } from "@phosphor-icons/react";
import { isRouteErrorResponse, useRouteError } from "react-router-dom";

export function RouteErrorBoundary() {
  const error = useRouteError();

  let message = "An unexpected error occurred.";
  if (isRouteErrorResponse(error)) {
    message = `${error.status} ${error.statusText}`;
  } else if (error instanceof Error) {
    message = error.message;
  }

  return (
    <Center mih="100vh" p="xl">
      <Stack align="center" gap="md" maw={480}>
        <WarningCircle size={48} weight="light" color="#b42318" />
        <Title order={3} ta="center">
          Something went wrong
        </Title>
        <Text c="dimmed" ta="center">
          This page ran into an unexpected error and could not finish loading.
          Your data is safe -- nothing was changed by this error.
        </Text>
        <Alert color="red" variant="light" w="100%">
          {message}
        </Alert>
        <Button
          leftSection={<ArrowClockwise size={16} weight="light" />}
          onClick={() => window.location.assign("/")}
        >
          Back to home
        </Button>
      </Stack>
    </Center>
  );
}
