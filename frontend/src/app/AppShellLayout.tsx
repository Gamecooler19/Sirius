/** Authenticated app shell: top-level nav + logout, wired to the real
 * `POST /auth/logout` and `GET /auth/me`. Only ever rendered once
 * `useMe()` has resolved successfully -- `RequireAuth` (in `router.tsx`)
 * is what guards this from rendering with no session at all.
 */

import { AppShell, Burger, Group, NavLink, Text, Button, Loader, Center } from "@mantine/core";
import { useDisclosure } from "@mantine/hooks";
import {
  SignOut,
  UsersThree,
  CurrencyCircleDollar,
  House,
  UploadSimple,
  ClockCounterClockwise,
  ChartLine,
} from "@phosphor-icons/react";
import { NavLink as RouterNavLink, Outlet, useNavigate } from "react-router-dom";
import { useMe } from "../api/useMe";
import { useLogout } from "../api/useAuth";
import {
  APPLICANTS_ROLES,
  FINANCE_ROLES,
  IMPORT_HISTORY_ROLES,
  IMPORT_UPLOAD_ROLES,
  RECONCILIATION_ROLES,
  hasRole,
} from "../auth/roles";

export function AppShellLayout() {
  const [opened, { toggle }] = useDisclosure();
  const navigate = useNavigate();
  const meQuery = useMe();
  const logout = useLogout();

  async function handleLogout() {
    await logout.mutateAsync();
    navigate("/login", { replace: true });
  }

  // RequireAuth already ensures meQuery.data exists before this renders,
  // but guard defensively in case of a race during a background refetch.
  if (meQuery.isLoading || !meQuery.data) {
    return (
      <Center mih="100vh">
        <Loader />
      </Center>
    );
  }

  const me = meQuery.data;

  return (
    <AppShell
      header={{ height: 60 }}
      navbar={{ width: 260, breakpoint: "sm", collapsed: { mobile: !opened } }}
      padding="md"
    >
      <AppShell.Header>
        <Group h="100%" px="md" justify="space-between">
          <Group>
            <Burger opened={opened} onClick={toggle} hiddenFrom="sm" size="sm" />
            <Text fw={700}>UnivAdmissions</Text>
          </Group>
          <Group>
            <Text size="sm" c="dimmed">
              {me.full_name} &middot; {me.role_code}
            </Text>
            <Button
              variant="light"
              color="red"
              size="xs"
              leftSection={<SignOut size={16} weight="light" />}
              loading={logout.isPending}
              onClick={handleLogout}
            >
              Logout
            </Button>
          </Group>
        </Group>
      </AppShell.Header>

      <AppShell.Navbar p="md">
        <NavLink
          component={RouterNavLink}
          to="/"
          end
          label="Home"
          leftSection={<House size={18} weight="light" />}
        />

        {hasRole(me.role_code, APPLICANTS_ROLES) && (
          <NavLink
            component={RouterNavLink}
            to="/applicants"
            label="Applicants"
            leftSection={<UsersThree size={18} weight="light" />}
          />
        )}

        {hasRole(me.role_code, FINANCE_ROLES) && (
          <NavLink
            component={RouterNavLink}
            to="/finance"
            label="Finance"
            leftSection={<CurrencyCircleDollar size={18} weight="light" />}
          />
        )}

        {hasRole(me.role_code, RECONCILIATION_ROLES) && (
          <NavLink
            component={RouterNavLink}
            to="/finance/reconciliation"
            label="Reconciliation"
            leftSection={<ChartLine size={18} weight="light" />}
          />
        )}

        {hasRole(me.role_code, IMPORT_UPLOAD_ROLES) && (
          <NavLink
            component={RouterNavLink}
            to="/import"
            label="Import applicants"
            leftSection={<UploadSimple size={18} weight="light" />}
          />
        )}

        {hasRole(me.role_code, IMPORT_HISTORY_ROLES) && (
          <NavLink
            component={RouterNavLink}
            to="/import/history"
            label="Import history"
            leftSection={<ClockCounterClockwise size={18} weight="light" />}
          />
        )}
      </AppShell.Navbar>

      <AppShell.Main>
        <Outlet />
      </AppShell.Main>
    </AppShell>
  );
}
