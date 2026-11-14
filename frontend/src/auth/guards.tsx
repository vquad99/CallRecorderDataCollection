// Route guards (AUTH-016, ROLE-011). Usability only: every API call is checked again on the server.
import { Navigate, Outlet, useLocation } from "react-router";

import { EmptyState, LoadingState } from "../components/StateViews";
import { useAuth } from "./AuthContext";

const SETUP = "/two-step-setup";

export function RequireAuth() {
  const { status, user } = useAuth();
  const location = useLocation();
  if (status === "loading") return <LoadingState label="Checking your sign-in" />;
  if (status === "anonymous") {
    const next = encodeURIComponent(location.pathname + location.search);
    return <Navigate to={`/login?next=${next}`} replace />;
  }
  // An account whose role needs two-step sign-in sets it up before anything else (D-106).
  if (user?.mfa_setup_required && location.pathname !== SETUP) {
    return <Navigate to={SETUP} replace />;
  }
  return <Outlet />;
}

export function RequirePermission({ permission }: { permission: string }) {
  const { can } = useAuth();
  if (!can(permission)) {
    return (
      <EmptyState
        title="No access"
        message="Your role does not include this page. Ask an administrator if you need it."
      />
    );
  }
  return <Outlet />;
}
