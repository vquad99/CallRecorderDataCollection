// Turning on two-step sign-in (AUTH-008, D-106): the password, then the key for the authenticator
// app, then the first code. Used on the account page and on the set-up page that admins must
// pass before anything else.
import { useState } from "react";

import * as authApi from "../api/auth";
import type { ApiError } from "../api/client";
import { Button } from "../components/form/Button";
import { TextField } from "../components/form/TextField";
import { ErrorNotice } from "../components/Notice";
import { toApiError } from "../hooks/useResource";
import "./twostep.css";

/** The key in groups of four, as authenticator apps show it and as it is easiest to type. */
const grouped = (secret: string) => secret.replace(/(.{4})(?=.)/g, "$1 ");

export function TwoStepEnrol({ onDone }: { onDone: () => Promise<void> | void }) {
  const [enrolment, setEnrolment] = useState<{ secret: string; otpauth_uri: string } | null>(null);
  const [password, setPassword] = useState("");
  const [code, setCode] = useState("");
  const [copied, setCopied] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);

  async function run(action: () => Promise<unknown>) {
    setBusy(true);
    setError(null);
    try {
      await action();
    } catch (err) {
      setError(toApiError(err));
    } finally {
      setBusy(false);
    }
  }

  if (!enrolment) {
    return (
      <form
        onSubmit={(e) => {
          e.preventDefault();
          void run(async () => {
            setEnrolment(await authApi.mfaEnroll(password));
            setPassword("");
          });
        }}
      >
        <TextField
          label="Your password"
          hint="Needed to turn on two-step sign-in."
          type="password"
          autoComplete="current-password"
          required
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />
        <Button type="submit" busy={busy} disabled={!password}>
          Turn on two-step sign-in
        </Button>
        <ErrorNotice error={error} />
      </form>
    );
  }
  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        void run(async () => {
          await authApi.mfaConfirm(code);
          setEnrolment(null);
          setCode("");
          await onDone();
        });
      }}
    >
      <ol className="steps">
        <li>
          Open an authenticator app on your phone (Google Authenticator, Microsoft Authenticator or
          another one).
        </li>
        <li>
          Add an account there and type this key:
          <p className="mono twostep__key" aria-label="Key for the authenticator app">
            {grouped(enrolment.secret)}
          </p>
          <span className="actions">
            <Button
              variant="secondary"
              onClick={() =>
                void navigator.clipboard
                  .writeText(enrolment.secret)
                  .then(() => setCopied(true))
                  .catch(() => setCopied(false))
              }
            >
              {copied ? "Key copied" : "Copy key"}
            </Button>
            <a className="button button--secondary" href={enrolment.otpauth_uri}>
              Open in an authenticator app on this device
            </a>
          </span>
        </li>
        <li>Enter the 6-digit code the app now shows.</li>
      </ol>
      <TextField
        label="Authenticator code"
        inputMode="numeric"
        autoComplete="one-time-code"
        required
        value={code}
        onChange={(e) => setCode(e.target.value)}
      />
      <Button type="submit" busy={busy}>
        Confirm
      </Button>
      <ErrorNotice error={error} />
    </form>
  );
}
