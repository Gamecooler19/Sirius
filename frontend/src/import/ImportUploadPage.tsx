/** Excel-import upload page: a real file picker wired to
 * `POST /import/applicants` via `useImportApplicants`. Restricted to
 * `IMPORT_UPLOAD_ROLES` (`SUPER_ADMIN`/`ADMISSIONS_MANAGER`) -- narrower
 * than the history list's own roles, matching the backend's real
 * asymmetry exactly (see `auth/roles.ts`'s own docstring). A role outside
 * that set sees no upload control at all here, not a disabled one --
 * this route itself is also not linked from the nav for such a role (see
 * `AppShellLayout`), so reaching this page at all requires a direct URL.
 */

import { useState } from "react";
import {
  Alert,
  Badge,
  Button,
  Card,
  FileInput,
  Group,
  List,
  Stack,
  Table,
  Text,
  Title,
} from "@mantine/core";
import {
  CheckCircle,
  Copy,
  UploadSimple,
  WarningCircle,
} from "@phosphor-icons/react";
import { ApiError } from "../api/client";
import type { ImportBatchResponse } from "../api/types";
import { useMe } from "../api/useMe";
import { IMPORT_UPLOAD_ROLES, hasRole } from "../auth/roles";
import { useImportApplicants } from "./useImport";

export function ImportUploadPage() {
  const meQuery = useMe();
  const [file, setFile] = useState<File | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<ImportBatchResponse | null>(null);
  const importMutation = useImportApplicants();

  const canUpload = meQuery.data ? hasRole(meQuery.data.role_code, IMPORT_UPLOAD_ROLES) : false;

  async function handleSubmit() {
    if (!file) return;
    setError(null);
    setResult(null);
    try {
      const response = await importMutation.mutateAsync(file);
      setResult(response);
    } catch (e) {
      // The backend's own 422 text (e.g. "import rejected: missing
      // expected column(s): Full Name") surfaces here verbatim via
      // ApiError, same convention as every other module's write path.
      setError(e instanceof ApiError ? e.message : "import failed");
    }
  }

  if (!canUpload) {
    return (
      <Stack>
        <Title order={2}>Import applicants</Title>
        <Text c="dimmed">Your role cannot run an applicant import.</Text>
      </Stack>
    );
  }

  return (
    <Stack maw={640}>
      <Title order={2}>Import applicants</Title>
      <Text c="dimmed" size="sm">
        Upload a .xlsx file with columns Full Name, Email, Phone, Program,
        Intake Cycle. Rows are matched against existing applicants by
        phone, then email; unmatched rows create new applicants.
      </Text>

      <FileInput
        label="Excel file"
        placeholder="Choose a .xlsx file"
        accept=".xlsx"
        value={file}
        onChange={(f) => {
          setFile(f);
          setError(null);
          setResult(null);
        }}
        clearable
      />

      <Group>
        <Button
          leftSection={<UploadSimple size={16} weight="light" />}
          onClick={handleSubmit}
          loading={importMutation.isPending}
          disabled={!file}
        >
          Upload
        </Button>
      </Group>

      {error && (
        <Alert color="red" icon={<WarningCircle size={20} weight="light" />}>
          {error}
        </Alert>
      )}

      {result && <ImportResult result={result} />}
    </Stack>
  );
}

function ImportResult({ result }: { result: ImportBatchResponse }) {
  if (result.deduplicated) {
    return (
      <Alert color="blue" icon={<Copy size={20} weight="light" />} title="Already imported">
        This file was already imported as batch <Text span fw={700}>{result.id}</Text>.
        No new rows were created or updated -- the checksum of this file
        matches a completed import already on record.
      </Alert>
    );
  }

  return (
    <Card withBorder padding="md" radius="sm">
      <Stack gap="sm">
        <Group justify="space-between">
          <Text fw={600}>Import complete</Text>
          <Badge color={result.status === "COMPLETED" ? "green" : "red"} variant="light">
            {result.status}
          </Badge>
        </Group>

        <Group gap="xl">
          <Stack gap={0}>
            <Text size="xs" c="dimmed">
              Created
            </Text>
            <Text fw={700}>{result.created_count}</Text>
          </Stack>
          <Stack gap={0}>
            <Text size="xs" c="dimmed">
              Updated
            </Text>
            <Text fw={700}>{result.updated_count}</Text>
          </Stack>
          <Stack gap={0}>
            <Text size="xs" c="dimmed">
              Flagged
            </Text>
            <Text fw={700}>{result.flagged_count}</Text>
          </Stack>
          <Stack gap={0}>
            <Text size="xs" c="dimmed">
              Rejected
            </Text>
            <Text fw={700}>{result.rejected_count}</Text>
          </Stack>
        </Group>

        {result.created_count > 0 || result.updated_count > 0 ? (
          <Alert color="green" icon={<CheckCircle size={18} weight="light" />} variant="light">
            New and updated applicants now appear in the applicant list.
          </Alert>
        ) : null}

        {result.flagged_rows && result.flagged_rows.length > 0 && (
          <Stack gap={4}>
            <Text size="sm" fw={600}>
              Flagged rows (email/phone changed on an existing applicant)
            </Text>
            <Table striped withTableBorder>
              <Table.Thead>
                <Table.Tr>
                  <Table.Th>Row</Table.Th>
                  <Table.Th>Applicant</Table.Th>
                  <Table.Th>Email</Table.Th>
                  <Table.Th>Phone</Table.Th>
                  <Table.Th>Reason</Table.Th>
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {result.flagged_rows.map((row, idx) => (
                  <Table.Tr key={idx}>
                    <Table.Td>{String(row.row_number ?? "?")}</Table.Td>
                    <Table.Td>
                      <Text size="xs" ff="monospace">
                        {String(row.applicant_id ?? "")}
                      </Text>
                    </Table.Td>
                    <Table.Td>
                      {String(row.old_email ?? "")} &rarr; {String(row.new_email ?? "")}
                    </Table.Td>
                    <Table.Td>
                      {String(row.old_phone ?? "")} &rarr; {String(row.new_phone ?? "")}
                    </Table.Td>
                    <Table.Td>{String(row.reason ?? "")}</Table.Td>
                  </Table.Tr>
                ))}
              </Table.Tbody>
            </Table>
          </Stack>
        )}

        {result.rejected_count > 0 && result.error_detail && (
          <Stack gap={4}>
            <Text size="sm" fw={600} c="red">
              Rejected rows
            </Text>
            <List size="sm" spacing={2}>
              {result.error_detail.split("; ").map((line, idx) => (
                <List.Item key={idx}>{line}</List.Item>
              ))}
            </List>
          </Stack>
        )}
      </Stack>
    </Card>
  );
}
