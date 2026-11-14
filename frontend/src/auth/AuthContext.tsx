// Sign-in state for the whole app (AUTH-016). The backend decides access; this only drives the UI.
import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";

import * as authApi from "../api/auth";
import { ApiError, MFA_SETUP_EVENT, UNAUTHENTICATED_EVENT } from "../api/client";

type Status = "loading" | "anonymous" | "authenticated";

export interface AuthValue {
  status: Status;
  user: authApi.Me | null;
  sessionExpired: boolean;
  can: (permission: string) => boolean;
  signIn: (email: string, password: string, totpCode?: string) => Promise<void>;
  signOut: () => Promise<void>;
  refresh: () => Promise<void>;
  /** Super Admin: see the app as another user, read-only (D-100). */
  viewAs: (userId: string) => Promise<void>;
  stopViewing: () => Promise<void>;
}

export const AuthContext = createContext<AuthValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<Status>("loading");
  const [user, setUser] = useState<authApi.Me | null>(null);
  const [sessionExpired, setSessionExpired] = useState(false);

  const refresh = useCallback(async () => {
    try {
      await authApi.ensureCsrf();
      const me = await authApi.getMe();
      setUser(me);
      setStatus("authenticated");
    } catch (error) {
      if (error instanceof ApiError && error.code === "SESSION_EXPIRED") setSessionExpired(true);
      setUser(null);
      setStatus("anonymous");
    }
  }, []);

  useEffect(() => {
    let active = true;
    authApi
      .ensureCsrf()
      .then(() => authApi.getMe())
      .then((me) => {
        if (!active) return;
        setUser(me);
        setStatus("authenticated");
      })
      .catch((error: unknown) => {
        if (!active) return;
        if (error instanceof ApiError && error.code === "SESSION_EXPIRED") setSessionExpired(true);
        setStatus("anonymous");
      });
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    const onUnauthenticated = (event: Event) => {
      const code = (event as CustomEvent<{ code: string }>).detail.code;
      setSessionExpired(code === "SESSION_EXPIRED");
      setUser(null);
      setStatus("anonymous");
    };
    // The server says this account must set up two-step sign-in first: go there (D-106).
    const onSetup = () => setUser((u) => (u ? { ...u, mfa_setup_required: true } : u));
    window.addEventListener(UNAUTHENTICATED_EVENT, onUnauthenticated);
    window.addEventListener(MFA_SETUP_EVENT, onSetup);
    return () => {
      window.removeEventListener(UNAUTHENTICATED_EVENT, onUnauthenticated);
      window.removeEventListener(MFA_SETUP_EVENT, onSetup);
    };
  }, []);

  const signIn = useCallback(async (email: string, password: string, totpCode?: string) => {
    await authApi.ensureCsrf();
    const me = await authApi.login(email, password, totpCode);
    setSessionExpired(false);
    setUser(me);
    setStatus("authenticated");
  }, []);

  const signOut = useCallback(async () => {
    try {
      await authApi.logout();
    } finally {
      setUser(null);
      setStatus("anonymous");
    }
  }, []);

  const viewAs = useCallback(async (userId: string) => {
    setUser(await authApi.startViewAs(userId));
  }, []);

  const stopViewing = useCallback(async () => {
    setUser(await authApi.stopViewAs());
  }, []);

  const value = useMemo<AuthValue>(
    () => ({
      status,
      user,
      sessionExpired,
      can: (permission) => user?.permissions.includes(permission) ?? false,
      signIn,
      signOut,
      refresh,
      viewAs,
      stopViewing,
    }),
    [status, user, sessionExpired, signIn, signOut, refresh, viewAs, stopViewing],
  );
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthValue {
  const value = useContext(AuthContext);
  if (!value) throw new Error("useAuth must be used inside AuthProvider");
  return value;
}
