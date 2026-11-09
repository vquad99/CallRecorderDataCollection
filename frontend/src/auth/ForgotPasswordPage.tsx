// Request a password reset link (AUTH-004). The answer is the same for every address.
import { useState, type FormEvent } from "react";
import { Link } from "react-router";

import { forgotPassword } from "../api/auth";
import type { ApiError } from "../api/client";
import { Button } from "../components/form/Button";
import { TextField } from "../components/form/TextField";
import { ErrorNotice, SuccessNotice } from "../components/Notice";
import { toApiError } from "../hooks/useResource";

export function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState<string | null>(null);
  const [error, setError] = useState<ApiError | null>(null);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      setDone((await forgotPassword(email)).status);
    } catch (err) {
      setError(toApiError(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="auth-page">
      <h1>Reset your password</h1>
      <form onSubmit={submit} noValidate>
        <TextField
          label="Email"
          type="email"
          autoComplete="username"
          required
          value={email}
          onChange={(e) => setEmail(e.target.value)}
        />
        <ErrorNotice error={error} />
        <SuccessNotice message={done} />
        <Button type="submit" busy={busy} disabled={Boolean(done)}>
          Send reset link
        </Button>
      </form>
      <p>
        <Link to="/login">Back to sign in</Link>
      </p>
    </div>
  );
}
