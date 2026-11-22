// Sign-in state for the whole app (AUTH-016). The backend decides access; this only drives the UI.
// Only the server's 401 means "signed out": a server that cannot be reached for a moment (a
// restart, a lost connection, a 503 or 429) leaves the person signed in ("unreachable" at start).
// Signing in or out in one tab tells the other tabs of the same browser (BroadcastChannel).
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import type { ReactNode } from "react";

import * as authApi from "../api/auth";
import { ApiError, MFA_SETUP_EVENT, UNAUTHENTICATED_EVENT } from "../api/client";

type Status = "loading" | "anonymous" | "authenticated" | "unreachable";

export interface AuthValue {
  status: Status;
  user: authApi.Me | null;
  sessionExpired: boolean;
  can: (permission: string) => boolean;
  signIn: (email: string, password: string, totpCode?: string) => Promise<void>;
  /** Ends the session. Rejects, and the person stays signed in, when the server was not reached. */
  signOut: () => Promise<void>;
  refresh: () => Promise<void>;
  /** Super Admin: see the app as another user, read-only (D-100). */
  viewAs: (userId: string) => Promise<void>;
  stopViewing: () => Promise<void>;
}

export const AuthContext = createContext<AuthValue | null>(null);

/** The tabs of one browser share the session cookie, so they share these two messages. */
const CHANNEL = "ccp-auth";
type TabMessage = "signed-in" | "signed-out";

const isSignedOut = (error: unknown) => error instanceof ApiError && error.status === 401;

export function AuthProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<Status>("loading");
  const [user, setUser] = useState<authApi.Me | null>(null);
  const [sessionExpired, setSessionExpired] = useState(false);
  const channel = useRef<BroadcastChannel | null>(null);

  const refresh = useCallback(async () => {
    try {
      await authApi.ensureCsrf();
      const me = await authApi.getMe();
      setUser(me);
      setStatus("authenticated");
    } catch (error) {
      if (isSignedOut(error)) {
        if ((error as ApiError).code === "SESSION_EXPIRED") setSessionExpired(true);
        setUser(null);
        setStatus("anonymous");
      } else {
        // Not an answer about the session: whoever is signed in stays signed in.
        setStatus((s) => (s === "authenticated" ? s : "unreachable"));
      }
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
        if (!isSignedOut(error)) {
          setStatus("unreachable");
          return;
        }
        if ((error as ApiError).code === "SESSION_EXPIRED") setSessionExpired(true);
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

  // Another tab signed out: so is this one (its phone line goes offline with it). Another tab
  // signed in: ask the server who that is.
  useEffect(() => {
    if (typeof BroadcastChannel === "undefined") return;
    const tabs = new BroadcastChannel(CHANNEL);
    tabs.onmessage = (event: MessageEvent) => {
      if (event.data === "signed-out") {
        setSessionExpired(false);
        setUser(null);
        setStatus("anonymous");
      } else if (event.data === "signed-in") {
        void refresh();
      }
    };
    channel.current = tabs;
    return () => {
      tabs.close();
      channel.current = null;
    };
  }, [refresh]);

  const signIn = useCallback(async (email: string, password: string, totpCode?: string) => {
    await authApi.ensureCsrf();
    const me = await authApi.login(email, password, totpCode);
    setSessionExpired(false);
    setUser(me);
    setStatus("authenticated");
    channel.current?.postMessage("signed-in" satisfies TabMessage);
  }, []);

  const signOut = useCallback(async () => {
    try {
      await authApi.logout();
    } catch (error) {
      // A 401 means the session had already ended. Anything else: the session may still be
      // live, so the person stays signed in and is told (a shared computer).
      if (!isSignedOut(error)) throw error;
    }
    setUser(null);
    setStatus("anonymous");
    channel.current?.postMessage("signed-out" satisfies TabMessage);
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
