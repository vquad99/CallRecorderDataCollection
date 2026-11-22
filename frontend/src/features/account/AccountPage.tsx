// The signed-in user's own account: password, devices, two-step sign-in (AUTH-008, AUTH-010),
// and a moderator's phone seat for the Chirp app (D-130).
import { useState } from "react";

import * as authApi from "../../api/auth";
import { showOwnSeatPassword } from "../../api/telephony";
import { useAuth } from "../../auth/AuthContext";
import { TwoStepEnrol } from "../../auth/TwoStepEnrol";
import { DataTable } from "../../components/DataTable";
import { Button } from "../../components/form/Button";
import { TextField } from "../../components/form/TextField";
import { ErrorNotice, SuccessNotice } from "../../components/Notice";
import { SavedPassword } from "../../components/SavedPassword";
import { ErrorState, LoadingState } from "../../components/StateViews";
import { useAction } from "../../hooks/useAction";
import { useResource } from "../../hooks/useResource";
import { when } from "../../lib/format";
import { describeUserAgent } from "../../lib/userAgent";
import { InstallCard } from "../../pwa/InstallCard";

function ChangePassword() {
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const { busy, error, message, run } = useAction();
  return (
    <section className="card" aria-labelledby="pw-title">
      <h2 id="pw-title">Change password</h2>
      <form
        noValidate
        onSubmit={(e) => {
          e.preventDefault();
          void run(async () => {
            await authApi.changePassword(current, next);
            setCurrent("");
            setNext("");
            return "Password changed. Other devices have been signed out.";
          });
        }}
      >
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
        <SuccessNotice message={message} />
        <Button type="submit" icon="key" busy={busy !== null}>
          Change password
        </Button>
      </form>
    </section>
  );
}

function Sessions() {
  const { state, reload } = useResource(authApi.listSessions, []);
  const { busy, error, run } = useAction(reload);
  return (
    <section className="card" aria-labelledby="sessions-title">
      <h2 id="sessions-title">Signed-in devices</h2>
      {state.status === "loading" ? <LoadingState /> : null}
      {state.status === "failed" ? <ErrorState error={state.error} onRetry={reload} /> : null}
      {state.status === "loaded" ? (
        <DataTable>
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
                  {describeUserAgent(s.user_agent)}
                  {s.ip ? <span className="muted"> · {s.ip}</span> : null}
                </td>
                <td>{when(s.last_seen_at)}</td>
                <td className="actions">
                  {s.current ? (
                    <span className="muted">This device</span>
                  ) : (
                    <Button
                      variant="secondary"
                      icon="logout"
                      busy={busy === s.id}
                      disabled={busy !== null}
                      onClick={() => void run(() => authApi.revokeSession(s.id), s.id)}
                    >
                      Sign out
                    </Button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </DataTable>
      ) : null}
      <ErrorNotice error={error} />
    </section>
  );
}

function TwoStep() {
  const { user, refresh } = useAuth();
  const [code, setCode] = useState("");
  const [password, setPassword] = useState("");
  const { busy, error, run } = useAction();
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
          <Button type="submit" variant="secondary" icon="lock" busy={busy !== null}>
            Turn off two-step sign-in
          </Button>
        </form>
      ) : null}
      <ErrorNotice error={error} />
    </section>
  );
}

/** The moderator's TxContact seat, set by a Super Admin. The portal signs it in by itself
 * (D-133); the Chirp app needs it only when that is switched off. */
function PhoneSeat({ seat, hasPassword }: { seat: string; hasPassword: boolean }) {
  return (
    <section className="card" aria-labelledby="seat-title">
      <h2 id="seat-title">Phone seat</h2>
      <p>
        The portal signs your phone line in with these by itself. You need them only if your admin
        asks you to use TxContact's Chirp app.
      </p>
      <p>
        Seat number: <strong>{seat}</strong>
      </p>
      {hasPassword ? (
        <SavedPassword label="Seat password" load={showOwnSeatPassword} />
      ) : (
        <p className="muted">No seat password is saved yet. Ask your Super Admin.</p>
      )}
    </section>
  );
}

export function AccountPage() {
  const { user } = useAuth();
  return (
    <section aria-labelledby="account-title" className="stack">
      <h1 id="account-title">My account</h1>
      <p>
        {user?.display_name} ({user?.email})
      </p>
      {user?.telephony_agent_id ? (
        <PhoneSeat
          seat={user.telephony_agent_id}
          hasPassword={user.telephony_has_password ?? false}
        />
      ) : null}
      {/* Two short forms side by side on a wide screen (D-154). */}
      <div className="section-pair">
        <ChangePassword />
        <TwoStep />
      </div>
      <Sessions />
      <InstallCard />
    </section>
  );
}
