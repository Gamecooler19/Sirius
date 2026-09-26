import { createBrowserRouter, RouterProvider } from "react-router-dom";
import { RequireAuth } from "../auth/RequireAuth";
import { AppShellLayout } from "./AppShellLayout";
import { LoginPage } from "../pages/LoginPage";
import { HomePage } from "../pages/HomePage";
import { ApplicantsPage } from "../applicants/ApplicantsPage";
import { FinancePage } from "../pages/FinancePage";

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
    ],
  },
]);

export function AppRouter() {
  return <RouterProvider router={router} />;
}
