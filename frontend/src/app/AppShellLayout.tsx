/** Authenticated app shell: top-level nav + logout, wired to the real
 * `POST /auth/logout` and `GET /auth/me`. Only ever rendered once
 * `useMe()` has resolved successfully -- `RequireAuth` (in `router.tsx`)
 * is what guards this from rendering with no session at all.
 *
 * Module 13 (DESIGN.md SS5 "Navigation"): NavLink now passes `active`
 * explicitly against the router's own matched path (react-router-dom's
 * `useLocation`) via plain `Link`, not react-router's own `NavLink`. A
 * real bug caught live in the browser: react-router's `NavLink` injects
 * its own literal `"active"` CSS class via prefix-matching whenever the
 * current path starts with its `to` (no `end` prop set), and that
 * generic class name collides with Mantine v9's own `.active` selector
 * for the NavLink component's active-state styling -- so with
 * `RouterNavLink`, both "Finance" (`/finance`) and "Reconciliation"
 * (`/finance/reconciliation`) rendered with the Harbor Cobalt Subtle
 * treatment simultaneously while on the reconciliation page, a direct
 * violation of SS2's One Signal Rule. Switching to plain `Link` (which
 * adds no class of its own) and relying only on this file's own
 * exact-path `active` prop fixes it -- confirmed via live DOM inspection
 * showing only one `data-active="true"` NavLink at a time after the fix.
 * The header wordmark also drops its plain bold-text treatment for a
 * small inline Sirius star mark (matching `public/favicon.svg`), so the
 * brand identity introduced by the new favicon carries into the shell
 * itself, not just the browser tab.
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
  UserCircle,
  GearSix,
} from "@phosphor-icons/react";
import { Link, Outlet, useLocation, useNavigate } from "react-router-dom";
import { useMe } from "../api/useMe";
import { useLogout } from "../api/useAuth";
import {
  APPLICANTS_ROLES,
  FINANCE_ROLES,
  IMPORT_HISTORY_ROLES,
  IMPORT_UPLOAD_ROLES,
  RECONCILIATION_ROLES,
  USERS_ROLES,
  hasRole,
} from "../auth/roles";

function SiriusMark() {
  // The same four-point star used in `public/favicon.svg`, inlined so it
  // can inherit `currentColor` and sit inline with the wordmark text at
  // header scale without a second network request.
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path
        d="M12 1L14.5 9.5L23 12L14.5 14.5L12 23L9.5 14.5L1 12L9.5 9.5L12 1Z"
        fill="#005681"
      />
    </svg>
  );
}

export function AppShellLayout() {
  const [opened, { toggle }] = useDisclosure();
  const navigate = useNavigate();
  const location = useLocation();
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
  const path = location.pathname;

  return (
    <AppShell
      header={{ height: 60 }}
      navbar={{ width: 260, breakpoint: "sm", collapsed: { mobile: !opened } }}
      padding="md"
      styles={{
        // DESIGN.md SS2/SS4: Steel Surface for the persistent nav/header
        // plane, separated from the white content plane by a single
        // hairline border (the "Panel" shadow token) -- not a drop shadow.
        header: { background: "#f3f8fa", borderBottom: "1px solid #d9dfe2" },
        navbar: { background: "#f3f8fa", borderRight: "1px solid #d9dfe2" },
        main: { background: "#ffffff" },
      }}
    >
      <AppShell.Header>
        <Group h="100%" px="md" justify="space-between">
          <Group gap="xs">
            <Burger opened={opened} onClick={toggle} hiddenFrom="sm" size="sm" />
            <SiriusMark />
            <Text fw={700} size="lg">
              Sirius
            </Text>
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
          component={Link}
          to="/"
          label="Home"
          active={path === "/"}
          leftSection={<House size={18} weight="light" />}
        />

        {hasRole(me.role_code, APPLICANTS_ROLES) && (
          <NavLink
            component={Link}
            to="/applicants"
            label="Applicants"
            active={path.startsWith("/applicants")}
            leftSection={<UsersThree size={18} weight="light" />}
          />
        )}

        {hasRole(me.role_code, FINANCE_ROLES) && (
          <NavLink
            component={Link}
            to="/finance"
            label="Finance"
            active={path === "/finance"}
            leftSection={<CurrencyCircleDollar size={18} weight="light" />}
          />
        )}

        {hasRole(me.role_code, RECONCILIATION_ROLES) && (
          <NavLink
            component={Link}
            to="/finance/reconciliation"
            label="Reconciliation"
            active={path === "/finance/reconciliation"}
            leftSection={<ChartLine size={18} weight="light" />}
          />
        )}

        {hasRole(me.role_code, IMPORT_UPLOAD_ROLES) && (
          <NavLink
            component={Link}
            to="/import"
            label="Import applicants"
            active={path === "/import"}
            leftSection={<UploadSimple size={18} weight="light" />}
          />
        )}

        {hasRole(me.role_code, IMPORT_HISTORY_ROLES) && (
          <NavLink
            component={Link}
            to="/import/history"
            label="Import history"
            active={path === "/import/history"}
            leftSection={<ClockCounterClockwise size={18} weight="light" />}
          />
        )}

        {hasRole(me.role_code, USERS_ROLES) && (
          <NavLink
            component={Link}
            to="/users"
            label="Users"
            active={path === "/users"}
            leftSection={<GearSix size={18} weight="light" />}
          />
        )}

        <NavLink
          component={Link}
          to="/profile"
          label="Profile"
          active={path === "/profile"}
          leftSection={<UserCircle size={18} weight="light" />}
        />
      </AppShell.Navbar>

      <AppShell.Main>
        <Outlet />
      </AppShell.Main>
    </AppShell>
  );
}
