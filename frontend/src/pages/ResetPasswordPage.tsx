/** Reset-password page (Module 16). Unauthenticated, public route --
 * reads the raw single-use token off its own URL (`?token=...`, the
 * same query param `POST /auth/forgot-password`'s email link embeds --
 * see that route's own docstring) via `useSearchParams`, never from a
 * form field a user would have to copy-paste by hand.
 *
 * Renders the real backend rejection reason verbatim on failure
 * (expired/invalid, already-used) via `ApiError` -- no frontend-
 * authored generic substitute, matching this app's established
 * convention for every other write path.
 */

import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import {
  Alert,
  Anchor,
  Button,
  Card,
  Center,
  PasswordInput,
  Stack,
  Text,
  Title,
} from "@mantine/core";
import { useForm } from "@mantine/form";
import { CheckCircle, WarningCircle } from "@phosphor-icons/react";
import { ApiError } from "../api/client";
import { useResetPassword } from "../api/useAuth";

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

export function ResetPasswordPage() {
  const [searchParams] = useSearchParams();
  const token = searchParams.get("token");

  const resetPassword = useResetPassword();
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);

  const form = useForm({
    initialValues: { new_password: "" },
  });

  async function handleSubmit(values: { new_password: string }) {
    setError(null);
    if (!token) {
      setError("missing reset token");
      return;
    }
    try {
      await resetPassword.mutateAsync({ token, new_password: values.new_password });
      setSuccess(true);
      form.reset();
    } catch (e) {
      // The backend's own real, distinct rejection reason ("invalid or
      // expired reset token" vs "this reset link has already been
      // used") surfaces here verbatim.
      setError(e instanceof ApiError ? e.message : "reset failed");
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
              This reset link is missing its token. Request a new one from the
              forgot-password page.
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
                Password reset successfully. You can now sign in with your new
                password.
              </Alert>
              <Anchor size="sm" component={Link} to="/login">
                Go to login
              </Anchor>
            </Stack>
          ) : (
            <>
              <Text size="sm" c="dimmed" ta="center">
                Choose a new password for your account.
              </Text>
              <form onSubmit={form.onSubmit(handleSubmit)}>
                <Stack gap="sm">
                  <PasswordInput
                    label="New password"
                    required
                    disabled={!token}
                    {...form.getInputProps("new_password")}
                  />
                  <Button
                    type="submit"
                    loading={resetPassword.isPending}
                    disabled={!token}
                    fullWidth
                    mt="sm"
                  >
                    Reset password
                  </Button>
                </Stack>
              </form>
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
