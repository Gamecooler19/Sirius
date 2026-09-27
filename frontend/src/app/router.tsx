import { createBrowserRouter, RouterProvider } from "react-router-dom";
import { RequireAuth } from "../auth/RequireAuth";
import { AppShellLayout } from "./AppShellLayout";
import { RouteErrorBoundary } from "./RouteErrorBoundary";
import { LoginPage } from "../pages/LoginPage";
import { ForgotPasswordPage } from "../pages/ForgotPasswordPage";
import { ResetPasswordPage } from "../pages/ResetPasswordPage";
import { SetInitialPasswordPage } from "../pages/SetInitialPasswordPage";
import { ConfirmEmailChangePage } from "../pages/ConfirmEmailChangePage";
import { HomePage } from "../pages/HomePage";
import { ProfilePage } from "../pages/ProfilePage";
import { ApplicantsPage } from "../applicants/ApplicantsPage";
import { FinancePage } from "../finance/FinancePage";
import { ImportUploadPage } from "../import/ImportUploadPage";
import { ImportHistoryPage } from "../import/ImportHistoryPage";
import { ReconciliationPage } from "../finance/ReconciliationPage";
import { UsersPage } from "../users/UsersPage";

/** Module 21 audit finding, fixed here: `errorElement` on every
 * top-level route (not only the authenticated `/` subtree) -- see
 * `RouteErrorBoundary`'s own docstring for the full account of the
 * real, live-confirmed defect this closes (react-router's raw default
 * fallback: a full-page stack trace, zero app chrome, zero recovery
 * path). react-router's own `errorElement` inheritance means a child
 * route (e.g. `/applicants`) that throws during render is caught by
 * the *nearest* ancestor route that declares one; since every
 * authenticated page lives under the single `/` route below, one
 * `errorElement` there covers all of them -- but each standalone
 * unauthenticated route (`/login`, `/forgot-password`, etc.) is its
 * own top-level route with no shared ancestor, so each needs its own
 * `errorElement` to get the same coverage rather than falling through
 * to react-router's own default for those specific pages.
 */
const router = createBrowserRouter([
  {
    path: "/login",
    element: <LoginPage />,
    errorElement: <RouteErrorBoundary />,
  },
  {
    path: "/forgot-password",
    element: <ForgotPasswordPage />,
    errorElement: <RouteErrorBoundary />,
  },
  {
    path: "/reset-password",
    element: <ResetPasswordPage />,
    errorElement: <RouteErrorBoundary />,
  },
  {
    path: "/set-initial-password",
    element: <SetInitialPasswordPage />,
    errorElement: <RouteErrorBoundary />,
  },
  {
    path: "/confirm-email-change",
    element: <ConfirmEmailChangePage />,
    errorElement: <RouteErrorBoundary />,
  },
  {
    path: "/",
    element: (
      <RequireAuth>
        <AppShellLayout />
      </RequireAuth>
    ),
    errorElement: <RouteErrorBoundary />,
    children: [
      { index: true, element: <HomePage /> },
      { path: "profile", element: <ProfilePage /> },
      { path: "applicants", element: <ApplicantsPage /> },
      { path: "finance", element: <FinancePage /> },
      { path: "finance/reconciliation", element: <ReconciliationPage /> },
      { path: "import", element: <ImportUploadPage /> },
      { path: "import/history", element: <ImportHistoryPage /> },
      { path: "users", element: <UsersPage /> },
    ],
  },
]);

export function AppRouter() {
  return <RouterProvider router={router} />;
}
