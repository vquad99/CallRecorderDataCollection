// Route guards (AUTH-016, ROLE-011). Usability only: every API call is checked again on the server.
import { useEffect } from "react";
import { Navigate, Outlet, useLocation } from "react-router";

import { EmptyState, ErrorState, LoadingState } from "../components/StateViews";
import { useAuth } from "./AuthContext";

const SETUP = "/two-step-setup";
/** While the server cannot be reached, it is asked again this often. */
const RETRY_MS = 5_000;

export function RequireAuth() {
  const { status, user, refresh } = useAuth();
  const location = useLocation();
  const unreachable = status === "unreachable";
  // Ask again by itself (a restart takes seconds); one request at a time, however slow.
  useEffect(() => {
    if (!unreachable) return;
    let stopped = false;
    let timer = 0;
    const again = () => {
      timer = window.setTimeout(() => {
        void refresh().finally(() => {
          if (!stopped) again();
        });
      }, RETRY_MS);
    };
    again();
    return () => {
      stopped = true;
      window.clearTimeout(timer);
    };
  }, [unreachable, refresh]);

  if (status === "loading") return <LoadingState label="Checking your sign-in" />;
  if (unreachable) {
    return (
      <ErrorState
        title="Cannot reach the server"
        message="You are still signed in. Try again in a moment."
        onRetry={() => void refresh()}
      />
    );
  }
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
