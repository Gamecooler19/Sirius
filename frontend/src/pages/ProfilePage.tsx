/** Profile page (Module 15, extended Modules 17-18): visible to all six
 * roles. Shows the account's own email/full name/role/2FA-enrollment
 * status (all read from the already-established `useMe` hook, no new
 * read endpoint needed), a self-service change-password form wired to
 * the real `POST /auth/change-password`, a self-service email-change
 * form wired to `POST /auth/change-email` (Module 17), a self-service
 * name-change form wired to `POST /auth/change-name` (Module 18), and
 * two distinct TOTP actions (Module 18):
 *
 * - **Not enrolled, non-mandatory role**: a voluntary "Set up two-factor
 *   authentication" action -- reuses the exact same
 *   `POST /auth/totp/enroll/start` + `/confirm` endpoints `LoginPage`
 *   already drives for a mandatory-role account on its first login, not
 *   a new enrollment mechanism. Gated only on `!me.totp_enabled` --
 *   `MANDATORY_TOTP_ROLES` already have their own forced path through
 *   `LoginPage` itself, so offering this button to them too would be a
 *   redundant, confusing second entry point into the same flow.
 * - **Already enrolled, any role**: a "Reset two-factor authentication"
 *   action -- wired to `POST /auth/totp/self-reset`, requiring the
 *   current password and a live current TOTP code before a fresh
 *   QR/backup-code pair is issued (see that endpoint's own backend
 *   docstring for why both are required, not either alone).
 *
 * **The email-change form does not change `me.email` on submit.** It
 * only sends a confirmation link to the new address -- `useMe`'s own
 * `email` field stays the current, still-working login email until a
 * real click on that link in the new inbox succeeds. Confirmed live
 * this stays true (see `reports/module-17-welcome-and-email-change.md`).
 *
 * Reuses Module 13's design system throughout -- `Card`/`Stack`/`Badge`
 * for the identity summary, the same `PasswordInput`/`Button`/`Alert`
 * shapes `LoginPage` already established for a credential form, the
 * same `PinInput`/`QRCodeSVG`/backup-code-list shapes `LoginPage`'s own
 * enrollment stage uses for the two new TOTP flows -- no new ad hoc
 * styling.
 */

import { useState } from "react";
import {
  Alert,
  Badge,
  Button,
  Card,
  Center,
  CopyButton,
  Group,
  List,
  Loader,
  PasswordInput,
  PinInput,
  Stack,
  Text,
  TextInput,
  Title,
} from "@mantine/core";
import { useForm } from "@mantine/form";
import { CheckCircle, Clock, Copy, ShieldCheck, WarningCircle } from "@phosphor-icons/react";
import { QRCodeSVG } from "qrcode.react";
import { ApiError } from "../api/client";
import { useMe } from "../api/useMe";
import {
  useChangeEmail,
  useChangeName,
  useChangePassword,
  useTotpEnrollConfirm,
  useTotpEnrollStart,
  useTotpSelfReset,
} from "../api/useAuth";

type TotpAction =
  | { kind: "idle" }
  | { kind: "voluntary-enroll"; provisioningUri: string; backupCodes: string[] }
  | { kind: "self-reset-form" }
  | { kind: "self-reset-enroll"; provisioningUri: string; backupCodes: string[] };

export function ProfilePage() {
  const meQuery = useMe();
  const changePassword = useChangePassword();
  const changeEmail = useChangeEmail();
  const changeName = useChangeName();
  const enrollStart = useTotpEnrollStart();
  const enrollConfirm = useTotpEnrollConfirm();
  const totpSelfReset = useTotpSelfReset();

  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);
  const [emailError, setEmailError] = useState<string | null>(null);
  const [emailSuccess, setEmailSuccess] = useState<string | null>(null);
  const [nameError, setNameError] = useState<string | null>(null);
  const [nameSuccess, setNameSuccess] = useState(false);

  const [totpAction, setTotpAction] = useState<TotpAction>({ kind: "idle" });
  const [totpError, setTotpError] = useState<string | null>(null);
  const [enrollCode, setEnrollCode] = useState("");

  const form = useForm({
    initialValues: { current_password: "", new_password: "" },
  });

  const emailForm = useForm({
    initialValues: { new_email: "" },
  });

  const nameForm = useForm({
    initialValues: { full_name: "" },
  });

  const selfResetForm = useForm({
    initialValues: { current_password: "", current_totp_code: "" },
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

  async function handleEmailSubmit(values: { new_email: string }) {
    setEmailError(null);
    setEmailSuccess(null);
    try {
      const result = await changeEmail.mutateAsync(values);
      // The backend's own fixed message, rendered verbatim.
      setEmailSuccess(result.message);
      emailForm.reset();
    } catch (e) {
      setEmailError(e instanceof ApiError ? e.message : "failed to request email change");
    }
  }

  async function handleNameSubmit(values: { full_name: string }) {
    setNameError(null);
    setNameSuccess(false);
    try {
      await changeName.mutateAsync(values);
      setNameSuccess(true);
      nameForm.reset();
    } catch (e) {
      setNameError(e instanceof ApiError ? e.message : "failed to change name");
    }
  }

  async function handleVoluntaryEnrollStart() {
    setTotpError(null);
    try {
      const enrollment = await enrollStart.mutateAsync();
      setTotpAction({
        kind: "voluntary-enroll",
        provisioningUri: enrollment.provisioning_uri,
        backupCodes: enrollment.backup_codes,
      });
      setEnrollCode("");
    } catch (e) {
      setTotpError(e instanceof ApiError ? e.message : "failed to start enrollment");
    }
  }

  async function handleSelfResetSubmit(values: {
    current_password: string;
    current_totp_code: string;
  }) {
    setTotpError(null);
    try {
      const result = await totpSelfReset.mutateAsync(values);
      setTotpAction({
        kind: "self-reset-enroll",
        provisioningUri: result.provisioning_uri,
        backupCodes: result.backup_codes,
      });
      setEnrollCode("");
      selfResetForm.reset();
    } catch (e) {
      // The backend's own real, distinct rejection text ("current
      // password is incorrect" / "invalid or expired TOTP code")
      // surfaces here verbatim -- see that endpoint's own docstring for
      // why the two are checked, and reported, separately.
      setTotpError(e instanceof ApiError ? e.message : "failed to reset two-factor authentication");
    }
  }

  async function handleEnrollConfirm() {
    setTotpError(null);
    try {
      await enrollConfirm.mutateAsync({ code: enrollCode });
      setTotpAction({ kind: "idle" });
      setEnrollCode("");
    } catch (e) {
      setTotpError(e instanceof ApiError ? e.message : "enrollment failed");
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
  const enrollmentInProgress =
    totpAction.kind === "voluntary-enroll" || totpAction.kind === "self-reset-enroll";

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
            {me.pending_email && (
              <Badge
                color="yellow"
                variant="light"
                mt={4}
                leftSection={<Clock size={12} weight="light" />}
                style={{ width: "fit-content" }}
              >
                Pending change to {me.pending_email}
              </Badge>
            )}
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
        <Title order={4}>Change name</Title>

        {nameError && (
          <Alert color="red" icon={<WarningCircle size={20} weight="light" />}>
            {nameError}
          </Alert>
        )}
        {nameSuccess && (
          <Alert color="green" icon={<CheckCircle size={20} weight="light" />}>
            Name changed successfully.
          </Alert>
        )}

        <form onSubmit={nameForm.onSubmit(handleNameSubmit)}>
          <Stack gap="sm">
            <TextInput
              label="Full name"
              placeholder={me.full_name}
              required
              {...nameForm.getInputProps("full_name")}
            />
            <Button type="submit" loading={changeName.isPending} w={200}>
              Save name
            </Button>
          </Stack>
        </form>
      </Stack>

      <Stack gap="sm">
        <Title order={4}>Change email</Title>

        {emailError && (
          <Alert color="red" icon={<WarningCircle size={20} weight="light" />}>
            {emailError}
          </Alert>
        )}
        {emailSuccess && (
          <Alert color="green" icon={<CheckCircle size={20} weight="light" />}>
            {emailSuccess}
          </Alert>
        )}

        <form onSubmit={emailForm.onSubmit(handleEmailSubmit)}>
          <Stack gap="sm">
            <TextInput
              label="New email"
              placeholder="you@sirius.app"
              required
              {...emailForm.getInputProps("new_email")}
            />
            <Button type="submit" loading={changeEmail.isPending} w={200}>
              Send confirmation
            </Button>
          </Stack>
        </form>
      </Stack>

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

      <Stack gap="sm">
        <Title order={4}>Two-factor authentication</Title>

        {totpError && (
          <Alert color="red" icon={<WarningCircle size={20} weight="light" />}>
            {totpError}
          </Alert>
        )}

        {totpAction.kind === "idle" && !me.totp_enabled && (
          <Stack gap="sm">
            <Text size="sm" c="dimmed">
              Your role does not require two-factor authentication, but you
              can voluntarily set it up for extra protection on this
              account.
            </Text>
            <Button
              leftSection={<ShieldCheck size={16} weight="light" />}
              loading={enrollStart.isPending}
              onClick={handleVoluntaryEnrollStart}
              w={280}
            >
              Set up two-factor authentication
            </Button>
          </Stack>
        )}

        {totpAction.kind === "idle" && me.totp_enabled && (
          <Stack gap="sm">
            <Text size="sm" c="dimmed">
              Two-factor authentication is currently enrolled on this
              account. Resetting it issues a fresh secret and backup
              codes -- your current authenticator app will stop working
              once you complete the new enrollment.
            </Text>
            <Button
              variant="light"
              onClick={() => {
                setTotpError(null);
                setTotpAction({ kind: "self-reset-form" });
              }}
              w={280}
            >
              Reset two-factor authentication
            </Button>
          </Stack>
        )}

        {totpAction.kind === "self-reset-form" && (
          <form onSubmit={selfResetForm.onSubmit(handleSelfResetSubmit)}>
            <Stack gap="sm">
              <Text size="sm" c="dimmed">
                Confirm your current password and a live code from your
                current authenticator app to continue.
              </Text>
              <PasswordInput
                label="Current password"
                required
                {...selfResetForm.getInputProps("current_password")}
              />
              <TextInput
                label="Current 6-digit code"
                placeholder="123456"
                required
                {...selfResetForm.getInputProps("current_totp_code")}
              />
              <Group gap="sm">
                <Button type="submit" loading={totpSelfReset.isPending}>
                  Continue
                </Button>
                <Button
                  variant="subtle"
                  color="gray"
                  onClick={() => {
                    setTotpAction({ kind: "idle" });
                    setTotpError(null);
                    selfResetForm.reset();
                  }}
                >
                  Cancel
                </Button>
              </Group>
            </Stack>
          </form>
        )}

        {enrollmentInProgress && (
          <Stack gap="md">
            <Text size="sm" c="dimmed">
              Scan this QR code with an authenticator app, then enter the
              six-digit code it shows to finish enrollment.
            </Text>

            <Center>
              <QRCodeSVG value={totpAction.provisioningUri} size={200} />
            </Center>

            <Card withBorder padding="sm" radius="sm" bg="yellow.0">
              <Stack gap="xs">
                <Text size="sm" fw={600}>
                  Backup codes -- save these now, shown only once
                </Text>
                <List size="sm" spacing={2} styles={{ itemWrapper: { fontFamily: "monospace" } }}>
                  {totpAction.backupCodes.map((code) => (
                    <List.Item key={code}>{code}</List.Item>
                  ))}
                </List>
                <CopyButton value={totpAction.backupCodes.join("\n")}>
                  {({ copied, copy }) => (
                    <Button
                      size="xs"
                      variant="light"
                      leftSection={
                        copied ? (
                          <CheckCircle size={14} weight="light" />
                        ) : (
                          <Copy size={14} weight="light" />
                        )
                      }
                      onClick={copy}
                    >
                      {copied ? "Copied" : "Copy all"}
                    </Button>
                  )}
                </CopyButton>
              </Stack>
            </Card>

            <Stack gap={4} align="center">
              <Text size="sm">Enter the code from your authenticator app</Text>
              <PinInput length={6} value={enrollCode} onChange={setEnrollCode} />
            </Stack>

            <Button
              onClick={handleEnrollConfirm}
              loading={enrollConfirm.isPending}
              disabled={enrollCode.length !== 6}
              fullWidth
            >
              Confirm enrollment
            </Button>
          </Stack>
        )}
      </Stack>
    </Stack>
  );
}
