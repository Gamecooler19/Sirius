import { createBrowserRouter, RouterProvider } from "react-router-dom";
import { RequireAuth } from "../auth/RequireAuth";
import { AppShellLayout } from "./AppShellLayout";
import { LoginPage } from "../pages/LoginPage";
import { HomePage } from "../pages/HomePage";
import { ApplicantsPage } from "../applicants/ApplicantsPage";
import { FinancePage } from "../finance/FinancePage";
import { ImportUploadPage } from "../import/ImportUploadPage";
import { ImportHistoryPage } from "../import/ImportHistoryPage";
import { ReconciliationPage } from "../finance/ReconciliationPage";

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
      { path: "applicants", element: <ApplicantsPage /> },
      { path: "finance", element: <FinancePage /> },
      { path: "finance/reconciliation", element: <ReconciliationPage /> },
      { path: "import", element: <ImportUploadPage /> },
      { path: "import/history", element: <ImportHistoryPage /> },
    ],
  },
]);

export function AppRouter() {
  return <RouterProvider router={router} />;
}
