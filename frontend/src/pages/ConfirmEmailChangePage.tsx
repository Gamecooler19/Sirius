/** Confirm-email-change page (Module 17). Unauthenticated, public route
 * -- reads the raw single-use token off its own URL (`?token=...`, the
 * same query param `POST /auth/change-email`'s confirmation email
 * embeds) via `useSearchParams`. No form: the token alone is the whole
 * request, so this page just presents a single confirm action (never
 * auto-confirms on page load, so a link accidentally opened twice, or
 * pre-fetched by an email client's own link-scanning, does not silently
 * burn the single-use token before the real account holder clicks
 * anything themselves).
 */

import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { Alert, Anchor, Button, Card, Center, Stack, Text, Title } from "@mantine/core";
import { CheckCircle, WarningCircle } from "@phosphor-icons/react";
import { ApiError } from "../api/client";
import { useConfirmEmailChange } from "../api/useAuth";

function SiriusMark() {
  return (
    <svg width="32" height="32" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path
        d="M12 1L14.5 9.5L23 12L14.5 14.5L12 23L9.5 14.5L1 12L9.5 9.5L12 1Z"
        fill="#005681"
      />
    </svg>
  );
}

export function ConfirmEmailChangePage() {
  const [searchParams] = useSearchParams();
  const token = searchParams.get("token");

  const confirmEmailChange = useConfirmEmailChange();
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);

  async function handleConfirm() {
    setError(null);
    if (!token) {
      setError("missing confirmation token");
      return;
    }
    try {
      await confirmEmailChange.mutateAsync({ token });
      setSuccess(true);
    } catch (e) {
      // The backend's own real, distinct rejection reason ("invalid or
      // expired confirmation token", "this confirmation link has
      // already been used", or a real 409 if the address was taken by
      // someone else in the interim) surfaces here verbatim.
      setError(e instanceof ApiError ? e.message : "confirmation failed");
    }
  }

  return (
    <Center mih="100vh" bg="#f3f8fa">
      <Card shadow="sm" padding="xl" radius="lg" withBorder w={420}>
        <Stack gap="md">
          <Stack gap={4} align="center">
            <SiriusMark />
            <Title order={2} ta="center">
              Sirius
            </Title>
          </Stack>

          {!token && (
            <Alert color="red" icon={<WarningCircle size={20} weight="light" />}>
              This confirmation link is missing its token. Request a new
              email change from your profile page.
            </Alert>
          )}

          {error && (
            <Alert color="red" icon={<WarningCircle size={20} weight="light" />}>
              {error}
            </Alert>
          )}

          {success ? (
            <Stack gap="sm" align="center">
              <Alert
                color="green"
                icon={<CheckCircle size={20} weight="light" />}
                w="100%"
              >
                Email address confirmed. Sign in using your new email from
                now on.
              </Alert>
              <Anchor size="sm" component={Link} to="/login">
                Go to login
              </Anchor>
            </Stack>
          ) : (
            <>
              <Text size="sm" c="dimmed" ta="center">
                Confirm this email address to complete the change on your
                Sirius account.
              </Text>
              <Button
                onClick={handleConfirm}
                loading={confirmEmailChange.isPending}
                disabled={!token}
                fullWidth
                mt="sm"
              >
                Confirm email address
              </Button>
              <Anchor size="sm" component={Link} to="/login" ta="center">
                Back to login
              </Anchor>
            </>
          )}
        </Stack>
      </Card>
    </Center>
  );
}
