/** Applicant detail view: a Mantine `Drawer` opened by clicking a row in
 * `ApplicantsPage`. Shows the applicant's own fields (from the real
 * `GET /applicants/{id}`) plus its status-history timeline in
 * chronological order (from the real `GET /applicants/{id}/status-history`),
 * and -- gated on `APPLICANTS_ROLES`, matching who the backend actually
 * allows to call `POST /applicants/{id}/status`
 * (`app.routers.status.transition_applicant_status`) -- a status
 * transition control.
 */

import { useState } from "react";
import {
  Alert,
  Badge,
  Button,
  Center,
  Divider,
  Drawer,
  Group,
  Loader,
  Select,
  Stack,
  Text,
  Textarea,
  Timeline,
  Title,
} from "@mantine/core";
import { ArrowRight, CheckCircle, WarningCircle, ClockCounterClockwise } from "@phosphor-icons/react";
import { ApiError } from "../api/client";
import type { ApplicationStatus } from "../api/types";
import { useMe } from "../api/useMe";
import { APPLICANTS_ROLES, hasRole } from "../auth/roles";
import { ApplicantFinanceSection } from "../finance/ApplicantFinanceSection";
import { ALL_STATUSES, allowedNextStatuses } from "./statusTransitions";
import {
  useApplicantDetail,
  useApplicantStatusHistory,
  useTransitionApplicantStatus,
} from "./useApplicants";
import { EmptyState } from "../components/EmptyState";

interface Props {
  applicantId: string | null;
  onClose: () => void;
}

export function ApplicantDetailDrawer({ applicantId, onClose }: Props) {
  return (
    <Drawer
      opened={applicantId !== null}
      onClose={onClose}
      title="Applicant detail"
      position="right"
      size="lg"
      transitionProps={{
        // Emil Kowalski: drawers/modals sit in the 200-500ms band, and
        // entering elements use ease-out (starts fast, feels responsive)
        // -- `slide-left` is the direction Mantine already uses for a
        // `position="right"` drawer, so this only tunes duration/easing,
        // not the direction itself.
        duration: 220,
        timingFunction: "cubic-bezier(0.23, 1, 0.32, 1)",
      }}
    >
      {applicantId !== null && <DrawerContent applicantId={applicantId} />}
    </Drawer>
  );
}

function DrawerContent({ applicantId }: { applicantId: string }) {
  const meQuery = useMe();
  const detailQuery = useApplicantDetail(applicantId);
  const historyQuery = useApplicantStatusHistory(applicantId);
  const transitionMutation = useTransitionApplicantStatus(applicantId);

  const [nextStatus, setNextStatus] = useState<ApplicationStatus | null>(null);
  const [note, setNote] = useState("");
  const [transitionError, setTransitionError] = useState<string | null>(null);
  const [transitionSuccess, setTransitionSuccess] = useState(false);

  if (detailQuery.isLoading || historyQuery.isLoading) {
    return (
      <Center py="xl">
        <Loader />
      </Center>
    );
  }

  if (detailQuery.isError) {
    return (
      <Alert color="red" icon={<WarningCircle size={20} weight="light" />}>
        {detailQuery.error instanceof ApiError
          ? detailQuery.error.message
          : "failed to load applicant"}
      </Alert>
    );
  }

  const applicant = detailQuery.data;
  const history = historyQuery.data?.items ?? [];
  const canTransition = meQuery.data ? hasRole(meQuery.data.role_code, APPLICANTS_ROLES) : false;
  const options = applicant ? allowedNextStatuses(applicant.current_status) : [];

  async function handleTransition() {
    if (!nextStatus) return;
    setTransitionError(null);
    setTransitionSuccess(false);
    try {
      await transitionMutation.mutateAsync({ to_status: nextStatus, note: note.trim() || null });
      setTransitionSuccess(true);
      setNextStatus(null);
      setNote("");
    } catch (e) {
      // The backend's own 422 text on an invalid transition (or any other
      // rejection) surfaces here verbatim via ApiError -- this frontend
      // table only decided which options were *offered*; it never
      // substitutes for the real enforcement or its real error text.
      setTransitionError(e instanceof ApiError ? e.message : "status transition failed");
    }
  }

  return (
    <Stack>
      {applicant && (
        <>
          <Stack gap={4}>
            <Title order={3}>{applicant.full_name}</Title>
            <Text size="sm" c="dimmed">
              {applicant.email}
              {applicant.phone ? ` · ${applicant.phone}` : ""}
            </Text>
          </Stack>

          <Group gap="xl">
            <Stack gap={0}>
              <Text size="xs" c="dimmed">
                Program
              </Text>
              <Text>{applicant.program}</Text>
            </Stack>
            <Stack gap={0}>
              <Text size="xs" c="dimmed">
                Intake cycle
              </Text>
              <Text>{applicant.intake_cycle}</Text>
            </Stack>
            <Stack gap={0}>
              <Text size="xs" c="dimmed">
                Current status
              </Text>
              <Badge variant="light">{applicant.current_status}</Badge>
            </Stack>
          </Group>

          <Divider label="Status transition" />

          {!canTransition && (
            <Text size="sm" c="dimmed">
              Your role cannot transition applicant status.
            </Text>
          )}

          {canTransition && options.length === 0 && (
            <Text size="sm" c="dimmed">
              {applicant.current_status} is a terminal status -- no further
              transitions are possible.
            </Text>
          )}

          {canTransition && options.length > 0 && (
            <Stack gap="xs">
              {transitionError && (
                <Alert color="red" icon={<WarningCircle size={18} weight="light" />}>
                  {transitionError}
                </Alert>
              )}
              {transitionSuccess && (
                <Alert color="green" icon={<CheckCircle size={18} weight="light" />}>
                  Status updated.
                </Alert>
              )}
              <Select
                label="Move to"
                placeholder="Select next status"
                data={ALL_STATUSES.map((s) => ({
                  value: s,
                  label: s,
                  disabled: !options.includes(s),
                }))}
                value={nextStatus}
                onChange={(value) => setNextStatus(value as ApplicationStatus | null)}
              />
              <Textarea
                label="Note (optional)"
                value={note}
                onChange={(e) => setNote(e.currentTarget.value)}
                autosize
                minRows={2}
              />
              <Button
                leftSection={<ArrowRight size={16} weight="light" />}
                onClick={handleTransition}
                loading={transitionMutation.isPending}
                disabled={!nextStatus}
              >
                Apply transition
              </Button>
            </Stack>
          )}

          <Divider label="Status history" />

          {historyQuery.isError && (
            <Alert color="red" icon={<WarningCircle size={18} weight="light" />}>
              {historyQuery.error instanceof ApiError
                ? historyQuery.error.message
                : "failed to load status history"}
            </Alert>
          )}

          {history.length === 0 && !historyQuery.isError && (
            <EmptyState
              icon={ClockCounterClockwise}
              title="No status changes recorded yet"
              body="This applicant's status history will appear here as soon as the first transition is made."
            />
          )}

          {history.length > 0 && (
            <Timeline active={history.length} bulletSize={20}>
              {history.map((event) => (
                <Timeline.Item
                  key={event.id}
                  title={
                    event.from_status
                      ? `${event.from_status} \u2192 ${event.to_status}`
                      : event.to_status
                  }
                >
                  <Text size="xs" c="dimmed">
                    {new Date(event.created_at).toLocaleString()}
                  </Text>
                  {event.note && <Text size="sm">{event.note}</Text>}
                </Timeline.Item>
              ))}
            </Timeline>
          )}

          <Divider label="Finance" />
          <ApplicantFinanceSection applicantId={applicantId} />
        </>
      )}
    </Stack>
  );
}
