// The signed-in user's own account: password, devices, two-step sign-in (AUTH-008, AUTH-010).
import { useState, type FormEvent } from "react";

import * as authApi from "../../api/auth";
import type { ApiError } from "../../api/client";
import { useAuth } from "../../auth/AuthContext";
import { TwoStepEnrol } from "../../auth/TwoStepEnrol";
import { InstallCard } from "../../pwa/InstallCard";
import { Button } from "../../components/form/Button";
import { TextField } from "../../components/form/TextField";
import { ErrorNotice, SuccessNotice } from "../../components/Notice";
import { ErrorState, LoadingState } from "../../components/StateViews";
import { toApiError, useResource } from "../../hooks/useResource";
import { IconTile } from "../../components/Icon";

function ChangePassword() {
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [busy, setBusy] = useState(false);
  const [ok, setOk] = useState<string | null>(null);
  const [error, setError] = useState<ApiError | null>(null);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    setOk(null);
    try {
      await authApi.changePassword(current, next);
      setOk("Password changed. Other devices have been signed out.");
      setCurrent("");
      setNext("");
    } catch (err) {
      setError(toApiError(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="card" aria-labelledby="pw-title">
      <h2 id="pw-title">Change password</h2>
      <form onSubmit={submit} noValidate>
        <TextField
          label="Current password"
          type="password"
          autoComplete="current-password"
          required
          value={current}
          onChange={(e) => setCurrent(e.target.value)}
        />
        <TextField
          label="New password"
          hint="At least 12 characters."
          type="password"
          autoComplete="new-password"
          required
          value={next}
          onChange={(e) => setNext(e.target.value)}
        />
        <ErrorNotice error={error} />
        <SuccessNotice message={ok} />
        <Button type="submit" busy={busy}>
          Change password
        </Button>
      </form>
    </section>
  );
}

function Sessions() {
  const { state, reload } = useResource(authApi.listSessions, []);
  const [error, setError] = useState<ApiError | null>(null);

  async function revoke(id: string) {
    setError(null);
    try {
      await authApi.revokeSession(id);
      reload();
    } catch (err) {
      setError(toApiError(err));
    }
  }

  return (
    <section className="card" aria-labelledby="sessions-title">
      <h2 id="sessions-title">Signed-in devices</h2>
      {state.status === "loading" ? <LoadingState /> : null}
      {state.status === "failed" ? <ErrorState error={state.error} onRetry={reload} /> : null}
      {state.status === "loaded" ? (
        <table className="table">
          <thead>
            <tr>
              <th scope="col">Device</th>
              <th scope="col">Last active</th>
              <th scope="col">Action</th>
            </tr>
          </thead>
          <tbody>
            {state.data.map((s) => (
              <tr key={s.id}>
                <td>
                  {s.user_agent ?? "Unknown browser"} {s.ip ? `(${s.ip})` : ""}
                </td>
                <td>{new Date(s.last_seen_at).toLocaleString()}</td>
                <td>
                  {s.current ? (
                    "This device"
                  ) : (
                    <Button variant="secondary" onClick={() => void revoke(s.id)}>
                      Sign out
                    </Button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : null}
      <ErrorNotice error={error} />
    </section>
  );
}

function TwoStep() {
  const { user, refresh } = useAuth();
  const [code, setCode] = useState("");
  const [password, setPassword] = useState("");
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

  const enabled = user?.mfa_enabled ?? false;
  return (
    <section className="card" aria-labelledby="mfa-title">
      <h2 id="mfa-title">Two-step sign-in</h2>
      <p>Status: {enabled ? "On" : "Off"}</p>
      {!enabled ? <TwoStepEnrol onDone={refresh} /> : null}
      {enabled ? (
        <form
          onSubmit={(e) => {
            e.preventDefault();
            void run(async () => {
              await authApi.mfaDisable(password, code);
              setPassword("");
              setCode("");
              await refresh();
            });
          }}
        >
          <TextField
            label="Password"
            type="password"
            autoComplete="current-password"
            required
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
          <TextField
            label="Authenticator code"
            inputMode="numeric"
            autoComplete="one-time-code"
            required
            value={code}
            onChange={(e) => setCode(e.target.value)}
          />
          <Button type="submit" variant="secondary" busy={busy}>
            Turn off two-step sign-in
          </Button>
        </form>
      ) : null}
      <ErrorNotice error={error} />
    </section>
  );
}

export function AccountPage() {
  const { user } = useAuth();
  return (
    <section aria-labelledby="account-title" className="stack">
      <h1 id="account-title">
        <IconTile name="user" tone="blue" />
        My account
      </h1>
      <p>
        {user?.display_name} ({user?.email})
      </p>
      <ChangePassword />
      <TwoStep />
      <Sessions />
      <InstallCard />
    </section>
  );
}
