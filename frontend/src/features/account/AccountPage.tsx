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
import { Icon } from "../../components/Icon";
import { ErrorNotice, SuccessNotice } from "../../components/Notice";
import { PageHeader } from "../../components/PageHeader";
import { SavedPassword } from "../../components/SavedPassword";
import { ErrorState, LoadingState } from "../../components/StateViews";
import { StatusBadge } from "../../components/StatusBadge";
import { useAction } from "../../hooks/useAction";
import { useFirstRows } from "../../hooks/useFirstRows";
import { useResource } from "../../hooks/useResource";
import { when } from "../../lib/format";
import { describeUserAgent } from "../../lib/userAgent";
import { InstallCard } from "../../pwa/InstallCard";
import "./account.css";

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

/** The account's sessions: this device first, then the others, newest first. A long list shows
 * its first rows, the rest on request (the button on the section's title bar, as on the
 * dashboard, D-158). */
function Sessions() {
  const { state, reload } = useResource(authApi.listSessions, []);
  const { busy, error, run } = useAction(reload);
  const sessions =
    state.status === "loaded"
      ? [...state.data].sort((a, b) => Number(b.current) - Number(a.current))
      : [];
  const { shown, more } = useFirstRows(sessions);
  return (
    <section className="card account-sessions" aria-labelledby="sessions-title">
      <div className="card__head">
        <h2 id="sessions-title">Signed-in devices</h2>
        {more}
      </div>
      {/* Under the title, in sight however long the list. */}
      <ErrorNotice error={error} />
      {state.status === "loading" ? <LoadingState /> : null}
      {state.status === "failed" ? <ErrorState error={state.error} onRetry={reload} /> : null}
      {state.status === "loaded" ? (
        <DataTable>
          <thead>
            <tr>
              <th scope="col">Device</th>
              <th scope="col" className="account-sessions__wide">
                Last active
              </th>
              <th scope="col">Action</th>
            </tr>
          </thead>
          <tbody>
            {shown.map((s) => (
              <tr key={s.id}>
                <td>
                  {describeUserAgent(s.user_agent)}
                  {s.ip ? <span className="muted"> · {s.ip}</span> : null}
                  {/* On a phone the time goes under the device, so Sign out stays in view. */}
                  <div className="muted account-sessions__narrow">{when(s.last_seen_at)}</div>
                </td>
                <td className="account-sessions__wide">{when(s.last_seen_at)}</td>
                <td className="actions">
                  {s.current ? (
                    // Drawn like the Sign out buttons under it, so both line up (D-158).
                    <span className="session-here">
                      <Icon name="ok" size={16} />
                      This device
                    </span>
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
      {/* Its state on the title bar, as the Server's on System status (D-158). */}
      <div className="card__head">
        <h2 id="mfa-title">Two-step sign-in</h2>
        <StatusBadge tone={enabled ? "success" : "neutral"} label={enabled ? "On" : "Off"} />
      </div>
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
      <PageHeader
        id="account-title"
        title="My account"
        lead={`${user?.display_name ?? ""} (${user?.email ?? ""})`}
      />
      {user?.telephony_agent_id ? (
        <PhoneSeat
          seat={user.telephony_agent_id}
          hasPassword={user.telephony_has_password ?? false}
        />
      ) : null}
      {/* Two short forms side by side on a wide screen (D-154), as tall as each other with their
          buttons on one line (D-158). */}
      <div className="section-pair account-pair">
        <ChangePassword />
        <TwoStep />
      </div>
      <Sessions />
      <InstallCard />
    </section>
  );
}
