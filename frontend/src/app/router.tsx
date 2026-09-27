import { createBrowserRouter, RouterProvider } from "react-router-dom";
import { RequireAuth } from "../auth/RequireAuth";
import { AppShellLayout } from "./AppShellLayout";
import { LoginPage } from "../pages/LoginPage";
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
