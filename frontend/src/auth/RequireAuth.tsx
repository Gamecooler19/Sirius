/** Route guard: renders its children only once `GET /auth/me` has
 * resolved successfully. A 401 (no session, expired session) redirects to
 * `/login` -- this is the one place the frontend reacts to the backend's
 * own authentication decision; no client-side session state is trusted
 * independent of this query.
 */

import { Center, Loader } from "@mantine/core";
import { Navigate, useLocation } from "react-router-dom";
import { useMe } from "../api/useMe";

export function RequireAuth({ children }: { children: React.ReactNode }) {
  const location = useLocation();
  const meQuery = useMe();

  if (meQuery.isLoading) {
    return (
      <Center mih="100vh">
        <Loader />
      </Center>
    );
  }

  if (meQuery.isError) {
    return <Navigate to="/login" replace state={{ from: location }} />;
  }

  return <>{children}</>;
}
