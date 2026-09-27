import { createBrowserRouter, RouterProvider } from "react-router-dom";
import { RequireAuth } from "../auth/RequireAuth";
import { AppShellLayout } from "./AppShellLayout";
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

const router = createBrowserRouter([
  {
    path: "/login",
    element: <LoginPage />,
  },
  {
    path: "/forgot-password",
    element: <ForgotPasswordPage />,
  },
  {
    path: "/reset-password",
    element: <ResetPasswordPage />,
  },
  {
    path: "/set-initial-password",
    element: <SetInitialPasswordPage />,
  },
  {
    path: "/confirm-email-change",
    element: <ConfirmEmailChangePage />,
  },
  {
    path: "/",
    element: (
      <RequireAuth>
        <AppShellLayout />
      </RequireAuth>
    ),
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
