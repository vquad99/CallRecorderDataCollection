// Sign-in page (AUTH-001, AUTH-002, AUTH-008, AUTH-016). Empty fields and an address without "@"
// are pointed out at the field before anything is sent.
import { useState, type FormEvent } from "react";
import { Link, Navigate, useSearchParams } from "react-router";

import type { ApiError } from "../api/client";
import { Button } from "../components/form/Button";
import { TextField } from "../components/form/TextField";
import { ErrorNotice } from "../components/Notice";
import { toApiError } from "../hooks/useResource";
import { useAuth } from "./AuthContext";

function safeNext(raw: string | null): string {
  // Only same-site paths, so a crafted link cannot send the user elsewhere after sign-in.
  // Browsers read a backslash as "/", so "/\\evil.example" is refused too (review 2026-11-10).
  if (!raw || !raw.startsWith("/") || raw.includes("\\")) return "/";
  try {
    const url = new URL(raw, window.location.origin);
    return url.origin === window.location.origin ? `${url.pathname}${url.search}${url.hash}` : "/";
  } catch {
    return "/";
  }
}

interface Problems {
  email?: string | undefined;
  password?: string | undefined;
}

/** What is wrong with a typed email address, or undefined (shared with the reset request). */
export function emailProblem(email: string): string | undefined {
  const typed = email.trim();
  if (!typed) return "Enter your email address.";
  if (!typed.includes("@")) return "Enter your full email address, for example name@example.org.";
  return undefined;
}

/** A field's problem as TextField's `error`, or nothing. */
export const fieldError = (problem: string | undefined) => (problem ? { error: problem } : {});

export function LoginPage() {
  const { status, signIn, sessionExpired } = useAuth();
  const [params] = useSearchParams();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [code, setCode] = useState("");
  const [needsCode, setNeedsCode] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const [problems, setProblems] = useState<Problems>({});

  if (status === "authenticated") return <Navigate to={safeNext(params.get("next"))} replace />;

  async function submit(event: FormEvent) {
    event.preventDefault();
    const found: Problems = {
      email: emailProblem(email),
      password: password ? undefined : "Enter your password.",
    };
    setProblems(found);
    if (found.email || found.password) return;
    setBusy(true);
    setError(null);
    try {
      await signIn(email.trim(), password, needsCode ? code : undefined);
    } catch (err) {
      const apiError = toApiError(err);
      if (apiError.code === "MFA_REQUIRED") {
        setNeedsCode(true);
      } else {
        setError(apiError);
      }
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="auth-page">
      <h1>Sign in</h1>
      {sessionExpired ? (
        <p className="notice notice--info" role="status">
          Your session has expired. Sign in again to continue.
        </p>
      ) : null}
      <form onSubmit={submit} noValidate>
        <TextField
          label="Email"
          type="email"
          autoComplete="username"
          required
          value={email}
          {...fieldError(problems.email)}
          onChange={(e) => {
            setEmail(e.target.value);
            setProblems((p) => ({ ...p, email: undefined }));
          }}
        />
        <TextField
          label="Password"
          type="password"
          autoComplete="current-password"
          required
          value={password}
          {...fieldError(problems.password)}
          onChange={(e) => {
            setPassword(e.target.value);
            setProblems((p) => ({ ...p, password: undefined }));
          }}
        />
        {needsCode ? (
          <TextField
            label="Authenticator code"
            hint="Enter the 6-digit code from your authenticator app."
            inputMode="numeric"
            autoComplete="one-time-code"
            required
            value={code}
            onChange={(e) => setCode(e.target.value)}
          />
        ) : null}
        <ErrorNotice error={error} />
        <Button type="submit" busy={busy}>
          Sign in
        </Button>
      </form>
      <p>
        <Link to="/forgot-password">Forgot your password?</Link>
      </p>
    </div>
  );
}
