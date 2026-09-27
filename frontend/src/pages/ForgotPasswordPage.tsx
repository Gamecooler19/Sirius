/** Forgot-password request page (Module 16). Unauthenticated, public
 * route -- reuses `LoginPage`'s own visual shell (Sirius mark, `Card`,
 * `Alert` pattern) rather than a new layout.
 *
 * **Deliberately shows the exact same success message regardless of
 * whether the email exists** -- the frontend's own reflection of the
 * backend's anti-enumeration guarantee (`ForgotPasswordResponse`'s own
 * docstring). There is no code path here that could ever render a
 * different message for "no such account" vs "email sent"; the backend
 * response itself never carries that distinction, so the frontend
 * structurally cannot leak it even by accident.
 */

import { useState } from "react";
import { Link } from "react-router-dom";
import {
  Alert,
  Anchor,
  Button,
  Card,
  Center,
  Stack,
  Text,
  TextInput,
  Title,
} from "@mantine/core";
import { useForm } from "@mantine/form";
import { CheckCircle, WarningCircle } from "@phosphor-icons/react";
import { ApiError } from "../api/client";
import { useForgotPassword } from "../api/useAuth";

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

export function ForgotPasswordPage() {
  const forgotPassword = useForgotPassword();
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const form = useForm({
    initialValues: { email: "" },
  });

  async function handleSubmit(values: { email: string }) {
    setError(null);
    setMessage(null);
    try {
      const result = await forgotPassword.mutateAsync(values);
      // The backend's own fixed message, rendered verbatim -- never a
      // frontend-authored substitute that might accidentally vary by
      // outcome.
      setMessage(result.message);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "request failed");
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

          <Text size="sm" c="dimmed" ta="center">
            Enter your account email and we'll send a password reset link.
          </Text>

          {error && (
            <Alert color="red" icon={<WarningCircle size={20} weight="light" />}>
              {error}
            </Alert>
          )}
          {message && (
            <Alert color="green" icon={<CheckCircle size={20} weight="light" />}>
              {message}
            </Alert>
          )}

          <form onSubmit={form.onSubmit(handleSubmit)}>
            <Stack gap="sm">
              <TextInput
                label="Email"
                placeholder="you@sirius.app"
                required
                {...form.getInputProps("email")}
              />
              <Button type="submit" loading={forgotPassword.isPending} fullWidth mt="sm">
                Send reset link
              </Button>
            </Stack>
          </form>

          <Anchor size="sm" component={Link} to="/login" ta="center">
            Back to login
          </Anchor>
        </Stack>
      </Card>
    </Center>
  );
}
