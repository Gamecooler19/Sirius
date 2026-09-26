/** Module 14: role-based dashboard content, replacing the Module 13 intro
 * card with real analytics for any role that has applicant and/or finance
 * visibility. Two independent sections, gated by
 * `DASHBOARD_APPLICANTS_ROLES`/`DASHBOARD_FINANCE_ROLES` (`auth/roles.ts`):
 *
 * - **Applicant summary**: wired to the real `GET /applicants/summary`
 *   (`useApplicantSummary`, Module 14's one new backend endpoint) -- a
 *   per-status count breakdown computed entirely in SQL
 *   (`GROUP BY current_status`), RLS-scoped by the exact same policy
 *   `GET /applicants` already enforces. This page adds no role parameter,
 *   no scope filter, no client-side narrowing of its own to that data --
 *   whatever the endpoint returns for this session is rendered as-is.
 * - **Finance summary**: wired to the real `GET /finance/reconciliation`
 *   via `useReconciliation` -- the exact same hook `ReconciliationPage`
 *   already uses (Module 05/09/10), imported and reused verbatim rather
 *   than duplicated into a second query or a second backend endpoint.
 *   Renders only the `totals` half of that response (the per-cycle
 *   breakdown table stays on the dedicated Reconciliation page).
 *
 * `SUPER_ADMIN`/`AUDITOR` are in both role lists and see both sections;
 * `ADMISSIONS_MANAGER`/`ADMISSIONS_COUNSELOR` see only the applicant
 * section; `FINANCE_STAFF`/`FINANCE_MANAGER` see only the finance
 * section. A role in neither list (none of the current six, but the
 * check below supports it) falls back to the Module 13 intro card, so
 * this page is never blank for an authenticated session.
 *
 * Every visual (`Card`, `SimpleGrid`, spacing, colors) reuses the exact
 * tokens/components Module 13's `DESIGN.md` and `ReconciliationPage`
 * already established -- no new ad hoc styling. The composed `EmptyState`
 * (Module 13's own signature component) covers the genuinely-zero-data
 * case for the applicant summary.
 */

import { Stack, Title, Text, Card, SimpleGrid, Alert, Center, Loader } from "@mantine/core";
import {
  Compass,
  WarningCircle,
  FileText,
  PaperPlaneTilt,
  ClockCounterClockwise as PauseIcon,
  ArrowClockwise,
  Megaphone,
  GraduationCap,
  XCircle,
  ArrowUUpLeft,
  UsersThree,
  CurrencyCircleDollar,
} from "@phosphor-icons/react";
import { ApiError } from "../api/client";
import { useMe } from "../api/useMe";
import type { ApplicationStatus } from "../api/types";
import { useApplicantSummary } from "../applicants/useApplicants";
import { useReconciliation } from "../finance/useReconciliation";
import { DASHBOARD_APPLICANTS_ROLES, DASHBOARD_FINANCE_ROLES, hasRole } from "../auth/roles";
import { EmptyState } from "../components/EmptyState";

// One icon per ApplicationStatus, in pipeline order -- matches the order
// `frontend/src/applicants/statusTransitions.ts::ALL_STATUSES` already
// establishes, so this dashboard's card order matches the filter
// dropdown's own order elsewhere in the app.
const STATUS_ICONS: Record<ApplicationStatus, typeof FileText> = {
  IMPORTED: FileText,
  APPLIED: PaperPlaneTilt,
  IN_PROCESS: ArrowClockwise,
  ON_HOLD: PauseIcon,
  ADMISSION_OFFERED: Megaphone,
  ADMISSION_TAKEN: GraduationCap,
  REJECTED: XCircle,
  WITHDRAWN: ArrowUUpLeft,
};

const STATUS_LABELS: Record<ApplicationStatus, string> = {
  IMPORTED: "Imported",
  APPLIED: "Applied",
  IN_PROCESS: "In process",
  ON_HOLD: "On hold",
  ADMISSION_OFFERED: "Admission offered",
  ADMISSION_TAKEN: "Admission taken",
  REJECTED: "Rejected",
  WITHDRAWN: "Withdrawn",
};

function ApplicantSummarySection() {
  const query = useApplicantSummary();

  if (query.isLoading) {
    return (
      <Center py="xl">
        <Loader />
      </Center>
    );
  }

  if (query.isError) {
    return (
      <Alert color="red" icon={<WarningCircle size={20} weight="light" />}>
        {query.error instanceof ApiError ? query.error.message : "failed to load applicant summary"}
      </Alert>
    );
  }

  const data = query.data;
  if (!data) return null;

  if (data.total === 0) {
    return (
      <EmptyState
        icon={UsersThree}
        title="No applicants in your view yet"
        body="Per-status counts will populate here once applicants exist that your role can see."
      />
    );
  }

  return (
    <SimpleGrid cols={{ base: 2, sm: 4 }} spacing="md">
      {data.by_status.map((bucket) => {
        const Icon = STATUS_ICONS[bucket.status];
        return (
          <Card withBorder padding="lg" radius="lg" key={bucket.status}>
            <Icon size={20} weight="light" color="#58666d" />
            <Text size="xs" c="dimmed" mt="xs">
              {STATUS_LABELS[bucket.status]}
            </Text>
            <Text size="xl" fw={700}>
              {bucket.count}
            </Text>
          </Card>
        );
      })}
    </SimpleGrid>
  );
}

function FinanceSummarySection() {
  const query = useReconciliation();

  if (query.isLoading) {
    return (
      <Center py="xl">
        <Loader />
      </Center>
    );
  }

  if (query.isError) {
    return (
      <Alert color="red" icon={<WarningCircle size={20} weight="light" />}>
        {query.error instanceof ApiError ? query.error.message : "failed to load finance summary"}
      </Alert>
    );
  }

  const totals = query.data?.totals;
  if (!totals) return null;

  if (totals.finance_record_count === 0) {
    return (
      <EmptyState
        icon={CurrencyCircleDollar}
        title="No finance records exist yet"
        body="Finance totals will populate here once applicants have finance records to summarize."
      />
    );
  }

  return (
    <SimpleGrid cols={{ base: 2, sm: 4 }} spacing="md">
      <Card withBorder padding="lg" radius="lg">
        <Text size="xs" c="dimmed">
          Finance records
        </Text>
        <Text size="xl" fw={700}>
          {totals.finance_record_count}
        </Text>
      </Card>
      <Card withBorder padding="lg" radius="lg">
        <Text size="xs" c="dimmed">
          Fee due
        </Text>
        <Text size="xl" fw={700}>
          {totals.total_fee_due}
        </Text>
      </Card>
      <Card withBorder padding="lg" radius="lg">
        <Text size="xs" c="dimmed">
          Paid
        </Text>
        <Text size="xl" fw={700}>
          {totals.total_paid}
        </Text>
      </Card>
      <Card withBorder padding="lg" radius="lg">
        <Text size="xs" c="dimmed">
          Outstanding
        </Text>
        <Text size="xl" fw={700}>
          {totals.outstanding}
        </Text>
      </Card>
    </SimpleGrid>
  );
}

function WelcomeIntro() {
  return (
    <Stack
      align="center"
      gap="xs"
      py={64}
      px="xl"
      style={{
        background: "#f3f8fa",
        borderRadius: "12px",
        textAlign: "center",
        maxWidth: 480,
        margin: "0 auto",
      }}
    >
      <Compass size={32} weight="light" color="#58666d" />
      <Title order={3} style={{ letterSpacing: "-0.01em" }}>
        Welcome to Sirius
      </Title>
      <Text size="sm" c="#58666d" maw="42ch">
        Pick a section from the nav on the left to get started.
      </Text>
    </Stack>
  );
}

export function HomePage() {
  const meQuery = useMe();

  if (meQuery.isLoading || !meQuery.data) {
    return (
      <Center py="xl">
        <Loader />
      </Center>
    );
  }

  const role = meQuery.data.role_code;
  const showApplicants = hasRole(role, DASHBOARD_APPLICANTS_ROLES);
  const showFinance = hasRole(role, DASHBOARD_FINANCE_ROLES);

  if (!showApplicants && !showFinance) {
    return <WelcomeIntro />;
  }

  return (
    <Stack gap="xl">
      <Title order={2}>Home</Title>

      {showApplicants && (
        <Stack gap="sm">
          <Title order={4}>Applicants by status</Title>
          <ApplicantSummarySection />
        </Stack>
      )}

      {showFinance && (
        <Stack gap="sm">
          <Title order={4}>Finance totals</Title>
          <FinanceSummarySection />
        </Stack>
      )}
    </Stack>
  );
}
