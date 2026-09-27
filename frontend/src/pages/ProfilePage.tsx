/** Profile page (Module 15): visible to all six roles. Shows the
 * account's own email/role/2FA-enrollment status (all read from the
 * already-established `useMe` hook, no new read endpoint needed) and a
 * self-service change-password form wired to the real
 * `POST /auth/change-password`.
 *
 * Reuses Module 13's design system throughout -- `Card`/`Stack`/`Badge`
 * for the identity summary, the same `PasswordInput`/`Button`/`Alert`
 * shapes `LoginPage` already established for a credential form, no new
 * ad hoc styling.
 */

import { useState } from "react";
import {
  Alert,
  Badge,
  Button,
  Card,
  Center,
  Group,
  Loader,
  PasswordInput,
  Stack,
  Text,
  Title,
} from "@mantine/core";
import { useForm } from "@mantine/form";
import { CheckCircle, WarningCircle } from "@phosphor-icons/react";
import { ApiError } from "../api/client";
import { useMe } from "../api/useMe";
import { useChangePassword } from "../api/useAuth";

export function ProfilePage() {
  const meQuery = useMe();
  const changePassword = useChangePassword();
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);

  const form = useForm({
    initialValues: { current_password: "", new_password: "" },
  });

  async function handleSubmit(values: { current_password: string; new_password: string }) {
    setError(null);
    setSuccess(false);
    try {
      await changePassword.mutateAsync(values);
      setSuccess(true);
      form.reset();
    } catch (e) {
      // The backend's own real error text ("current password is
      // incorrect") surfaces here verbatim via ApiError -- never a
      // generic frontend-authored message, matching the module's own
      // requirement and this app's established convention for every
      // other write path.
      setError(e instanceof ApiError ? e.message : "failed to change password");
    }
  }

  if (meQuery.isLoading || !meQuery.data) {
    return (
      <Center py="xl">
        <Loader />
      </Center>
    );
  }

  const me = meQuery.data;

  return (
    <Stack gap="xl" maw={520}>
      <Title order={2}>Profile</Title>

      <Card withBorder padding="lg" radius="lg">
        <Stack gap="sm">
          <Stack gap={0}>
            <Text size="xs" c="dimmed">
              Email
            </Text>
            <Text>{me.email}</Text>
          </Stack>
          <Stack gap={0}>
            <Text size="xs" c="dimmed">
              Full name
            </Text>
            <Text>{me.full_name}</Text>
          </Stack>
          <Group gap="xl">
            <Stack gap={0}>
              <Text size="xs" c="dimmed">
                Role
              </Text>
              <Badge variant="light">{me.role_code}</Badge>
            </Stack>
            <Stack gap={0}>
              <Text size="xs" c="dimmed">
                Two-factor authentication
              </Text>
              <Badge color={me.totp_enabled ? "green" : "gray"} variant="light">
                {me.totp_enabled ? "Enrolled" : "Not enrolled"}
              </Badge>
            </Stack>
          </Group>
        </Stack>
      </Card>

      <Stack gap="sm">
        <Title order={4}>Change password</Title>

        {error && (
          <Alert color="red" icon={<WarningCircle size={20} weight="light" />}>
            {error}
          </Alert>
        )}
        {success && (
          <Alert color="green" icon={<CheckCircle size={20} weight="light" />}>
            Password changed successfully.
          </Alert>
        )}

        <form onSubmit={form.onSubmit(handleSubmit)}>
          <Stack gap="sm">
            <PasswordInput
              label="Current password"
              required
              {...form.getInputProps("current_password")}
            />
            <PasswordInput
              label="New password"
              required
              {...form.getInputProps("new_password")}
            />
            <Button type="submit" loading={changePassword.isPending} w={200}>
              Change password
            </Button>
          </Stack>
        </form>
      </Stack>
    </Stack>
  );
}
