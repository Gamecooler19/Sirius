/** Set-initial-password page (Module 17). Unauthenticated, public route
 * -- functionally identical to `ResetPasswordPage` (both redeem the
 * exact same `POST /auth/reset-password` endpoint against the exact
 * same token infrastructure; see that route's own backend docstring
 * for why a welcome token and a forgot-password token are
 * indistinguishable at redemption time), but deliberately a **separate
 * component with its own copy**, not `ResetPasswordPage` reused with a
 * prop flag: the wording throughout ("activate your account", "choose
 * your password") must never imply this account ever had a working
 * password to *reset* -- it never did. Reads the raw single-use token
 * off its own URL (`?token=...`, the same query param the welcome
 * email's link embeds) via `useSearchParams`.
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

export function SetInitialPasswordPage() {
  const [searchParams] = useSearchParams();
  const token = searchParams.get("token");

  const setInitialPassword = useResetPassword();
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);

  const form = useForm({
    initialValues: { new_password: "" },
  });

  async function handleSubmit(values: { new_password: string }) {
    setError(null);
    if (!token) {
      setError("missing activation token");
      return;
    }
    try {
      await setInitialPassword.mutateAsync({ token, new_password: values.new_password });
      setSuccess(true);
      form.reset();
    } catch (e) {
      // The backend's own real, distinct rejection reason ("invalid or
      // expired reset token" vs "this reset link has already been
      // used") surfaces here verbatim.
      setError(e instanceof ApiError ? e.message : "activation failed");
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
              This activation link is missing its token. Contact your
              administrator for a new invitation.
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
                Account activated. You can now sign in with your new password.
              </Alert>
              <Anchor size="sm" component={Link} to="/login">
                Go to login
              </Anchor>
            </Stack>
          ) : (
            <>
              <Text size="sm" c="dimmed" ta="center">
                Welcome to Sirius. Choose a password to activate your account.
              </Text>
              <form onSubmit={form.onSubmit(handleSubmit)}>
                <Stack gap="sm">
                  <PasswordInput
                    label="Password"
                    required
                    disabled={!token}
                    {...form.getInputProps("new_password")}
                  />
                  <Button
                    type="submit"
                    loading={setInitialPassword.isPending}
                    disabled={!token}
                    fullWidth
                    mt="sm"
                  >
                    Activate account
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
