/** Login page: drives the exact flow `POST /auth/login`'s own response
 * shape dictates --
 *
 * 1. Plain success (`totp_required: false`): session is immediately fully
 *    authenticated, straight to the shell.
 * 2. `totp_required: true`, `totp_enrollment_required: true`: this role
 *    requires TOTP but has never enrolled -- drive enrollment
 *    (`/auth/totp/enroll/start` then `/auth/totp/enroll/confirm`) before
 *    the session can reach any protected route.
 * 3. `totp_required: true`, `totp_enrollment_required: false`: already
 *    enrolled -- prompt for a live six-digit code
 *    (`/auth/totp/verify`).
 *
 * All three states share one component so the transition between them
 * (a session that started as case 2 and just finished confirming) can
 * fall straight through to "authenticated" without a page reload.
 */

import { useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  Alert,
  Anchor,
  Button,
  Card,
  Center,
  CopyButton,
  Group,
  List,
  PasswordInput,
  PinInput,
  Stack,
  Text,
  TextInput,
  Title,
} from "@mantine/core";
import { useForm } from "@mantine/form";
import { WarningCircle, CheckCircle, Copy } from "@phosphor-icons/react";
import { QRCodeSVG } from "qrcode.react";
import { ApiError } from "../api/client";
import {
  useLogin,
  useTotpEnrollConfirm,
  useTotpEnrollStart,
  useTotpVerify,
} from "../api/useAuth";

type Stage =
  | { kind: "credentials" }
  | { kind: "enroll" }
  | { kind: "verify" };

export function LoginPage() {
  const navigate = useNavigate();
  const [stage, setStage] = useState<Stage>({ kind: "credentials" });
  const [error, setError] = useState<string | null>(null);

  const login = useLogin();
  const enrollStart = useTotpEnrollStart();
  const enrollConfirm = useTotpEnrollConfirm();
  const totpVerify = useTotpVerify();

  const credentialsForm = useForm({
    initialValues: { email: "", password: "" },
  });

  const [provisioningUri, setProvisioningUri] = useState<string | null>(null);
  const [backupCodes, setBackupCodes] = useState<string[] | null>(null);
  const [enrollCode, setEnrollCode] = useState("");
  const [verifyCode, setVerifyCode] = useState("");

  async function handleCredentialsSubmit(values: { email: string; password: string }) {
    setError(null);
    try {
      const result = await login.mutateAsync(values);
      if (!result.totp_required) {
        navigate("/", { replace: true });
        return;
      }
      if (result.totp_enrollment_required) {
        const enrollment = await enrollStart.mutateAsync();
        setProvisioningUri(enrollment.provisioning_uri);
        setBackupCodes(enrollment.backup_codes);
        setStage({ kind: "enroll" });
      } else {
        setStage({ kind: "verify" });
      }
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "login failed");
    }
  }

  async function handleEnrollConfirm() {
    setError(null);
    try {
      await enrollConfirm.mutateAsync({ code: enrollCode });
      navigate("/", { replace: true });
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "enrollment failed");
    }
  }

  async function handleVerify() {
    setError(null);
    try {
      await totpVerify.mutateAsync({ code: verifyCode });
      navigate("/", { replace: true });
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "verification failed");
    }
  }

  return (
    <Center mih="100vh" bg="gray.0">
      <Card shadow="sm" padding="xl" radius="md" withBorder w={420}>
        <Stack gap="md">
          <Title order={2} ta="center">
            Sirius
          </Title>

          {error && (
            <Alert color="red" icon={<WarningCircle size={20} weight="light" />}>
              {error}
            </Alert>
          )}

          {stage.kind === "credentials" && (
            <form onSubmit={credentialsForm.onSubmit(handleCredentialsSubmit)}>
              <Stack gap="sm">
                <TextInput
                  label="Email"
                  placeholder="you@sirius.app"
                  required
                  {...credentialsForm.getInputProps("email")}
                />
                <PasswordInput
                  label="Password"
                  required
                  {...credentialsForm.getInputProps("password")}
                />
                <Button
                  type="submit"
                  loading={login.isPending || enrollStart.isPending}
                  fullWidth
                  mt="sm"
                >
                  Sign in
                </Button>
              </Stack>
            </form>
          )}

          {stage.kind === "enroll" && (
            <Stack gap="md">
              <Text size="sm" c="dimmed">
                This role requires two-factor authentication. Scan this QR
                code with an authenticator app, then enter the six-digit
                code it shows.
              </Text>

              {provisioningUri && (
                <Center>
                  <QRCodeSVG value={provisioningUri} size={200} />
                </Center>
              )}

              {backupCodes && (
                <Card withBorder padding="sm" radius="sm" bg="yellow.0">
                  <Stack gap="xs">
                    <Text size="sm" fw={600}>
                      Backup codes -- save these now, shown only once
                    </Text>
                    <List size="sm" spacing={2} styles={{ itemWrapper: { fontFamily: "monospace" } }}>
                      {backupCodes.map((code) => (
                        <List.Item key={code}>{code}</List.Item>
                      ))}
                    </List>
                    <CopyButton value={backupCodes.join("\n")}>
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
              )}

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

          {stage.kind === "verify" && (
            <Stack gap="md" align="center">
              <Text size="sm" c="dimmed" ta="center">
                Enter the six-digit code from your authenticator app.
              </Text>
              <PinInput length={6} value={verifyCode} onChange={setVerifyCode} />
              <Button
                onClick={handleVerify}
                loading={totpVerify.isPending}
                disabled={verifyCode.length !== 6}
                fullWidth
              >
                Verify
              </Button>
              <Anchor
                size="sm"
                onClick={() => {
                  setStage({ kind: "credentials" });
                  setError(null);
                  credentialsForm.reset();
                }}
              >
                Back to login
              </Anchor>
            </Stack>
          )}

          {stage.kind === "credentials" && (
            <Group justify="center">
              <Text size="xs" c="dimmed">
                Session cookie based auth -- no password reset here yet.
              </Text>
            </Group>
          )}
        </Stack>
      </Card>
    </Center>
  );
}
