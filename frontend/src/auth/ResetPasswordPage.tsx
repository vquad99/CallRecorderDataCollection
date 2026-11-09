// Set a new password from an emailed link (reset or invitation) (AUTH-004).
import { useState, type FormEvent } from "react";
import { Link, useSearchParams } from "react-router";

import { resetPassword } from "../api/auth";
import { ApiError } from "../api/client";
import { Button } from "../components/form/Button";
import { TextField } from "../components/form/TextField";
import { ErrorNotice, SuccessNotice } from "../components/Notice";
import { toApiError } from "../hooks/useResource";

export function ResetPasswordPage() {
  const [params] = useSearchParams();
  const token = params.get("token") ?? "";
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const mismatch = confirm.length > 0 && confirm !== password;

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (mismatch) return;
    setBusy(true);
    setError(null);
    try {
      await resetPassword(token, password);
      setDone(true);
    } catch (err) {
      setError(toApiError(err));
    } finally {
      setBusy(false);
    }
  }

  if (!token) {
    return (
      <div className="auth-page">
        <h1>Set a new password</h1>
        <ErrorNotice
          error={
            new ApiError({
              status: 400,
              code: "INVALID_TOKEN",
              message: "This link is incomplete.",
            })
          }
        />
        <Link to="/forgot-password">Request a new link</Link>
      </div>
    );
  }

  return (
    <div className="auth-page">
      <h1>Set a new password</h1>
      {done ? (
        <>
          <SuccessNotice message="Your password is set. You can sign in now." />
          <Link to="/login">Go to sign in</Link>
        </>
      ) : (
        <form onSubmit={submit} noValidate>
          <TextField
            label="New password"
            hint="At least 12 characters."
            type="password"
            autoComplete="new-password"
            required
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
          <TextField
            label="Repeat new password"
            type="password"
            autoComplete="new-password"
            required
            value={confirm}
            onChange={(e) => setConfirm(e.target.value)}
            {...(mismatch ? { error: "The two passwords do not match." } : {})}
          />
          <ErrorNotice error={error} />
          <Button type="submit" busy={busy} disabled={mismatch || !password}>
            Set password
          </Button>
        </form>
      )}
    </div>
  );
}
