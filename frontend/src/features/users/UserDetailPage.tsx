// Edit one user: name, email, roles, status, password link, sessions (USER-001..003, USER-008).
import { useState, type FormEvent } from "react";
import { useParams } from "react-router";

import * as admin from "../../api/admin";
import type { ApiError } from "../../api/client";
import { setAgentSeat } from "../../api/telephony";
import { Button } from "../../components/form/Button";
import { TextField } from "../../components/form/TextField";
import { ErrorNotice, SuccessNotice } from "../../components/Notice";
import { ErrorState, LoadingState } from "../../components/StateViews";
import { toApiError, useResource } from "../../hooks/useResource";
import { RoleCheckboxes } from "./RoleCheckboxes";

function Editor({ user, onSaved }: { user: admin.User; onSaved: (u: admin.User) => void }) {
  const [name, setName] = useState(user.display_name);
  const [email, setEmail] = useState(user.email);
  const [roles, setRoles] = useState(user.roles);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  async function run(action: () => Promise<admin.User | string>) {
    setBusy(true);
    setError(null);
    setMessage(null);
    try {
      const result = await action();
      if (typeof result === "string") {
        setMessage(result);
      } else {
        onSaved(result);
        setMessage("Saved.");
      }
    } catch (err) {
      setError(toApiError(err));
    } finally {
      setBusy(false);
    }
  }

  async function save(event: FormEvent) {
    event.preventDefault();
    await run(async () => {
      let updated = await admin.updateUser(user.id, { display_name: name, email });
      if ([...roles].sort().join() !== [...user.roles].sort().join()) {
        updated = await admin.setUserRoles(user.id, roles);
      }
      return updated;
    });
  }

  return (
    <div className="stack">
      <form onSubmit={(e) => void save(e)} noValidate className="card">
        <TextField label="Name" required value={name} onChange={(e) => setName(e.target.value)} />
        <TextField
          label="Email"
          type="email"
          required
          value={email}
          onChange={(e) => setEmail(e.target.value)}
        />
        <RoleCheckboxes value={roles} onChange={setRoles} />
        <Button type="submit" busy={busy} disabled={roles.length === 0}>
          Save changes
        </Button>
      </form>
      <div className="card actions">
        <Button
          variant="secondary"
          busy={busy}
          onClick={() => void run(() => admin.setUserStatus(user.id, user.status !== "ACTIVE"))}
        >
          {user.status === "ACTIVE" ? "Disable account" : "Enable account"}
        </Button>
        <Button
          variant="secondary"
          busy={busy}
          disabled={user.status !== "ACTIVE"}
          onClick={() =>
            void run(async () =>
              (await admin.sendPasswordLink(user.id)).sent
                ? "Password link sent by email."
                : "The email could not be sent. Check the email settings.",
            )
          }
        >
          Send password link
        </Button>
        <Button
          variant="secondary"
          busy={busy}
          onClick={() =>
            void run(
              async () =>
                `${(await admin.revokeUserSessions(user.id)).sessions_revoked} session(s) signed out.`,
            )
          }
        >
          Sign out everywhere
        </Button>
      </div>
      <ErrorNotice error={error} />
      <SuccessNotice message={message} />
    </div>
  );
}

/** The TxContact agent seat a moderator's phone calls ring (D-101); one seat per person. */
function AgentSeat({ user, onSaved }: { user: admin.User; onSaved: (u: admin.User) => void }) {
  const [seat, setSeat] = useState(user.telephony_agent_id ?? "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  return (
    <form
      className="card"
      noValidate
      onSubmit={(e) => {
        e.preventDefault();
        setBusy(true);
        setError(null);
        setMessage(null);
        setAgentSeat(user.id, seat.trim())
          .then((r) => {
            onSaved({ ...user, telephony_agent_id: r.telephony_agent_id });
            setMessage(r.telephony_agent_id ? "Agent seat saved." : "Agent seat removed.");
          })
          .catch((err: unknown) => setError(toApiError(err)))
          .finally(() => setBusy(false));
      }}
    >
      <h2>Phone calls</h2>
      <p className="muted">
        The TxContact agent seat this person signs in to. Calls they start ring them there. Leave it
        empty for people who do not make phone calls.
      </p>
      <TextField
        label="TxContact agent seat"
        value={seat}
        maxLength={40}
        onChange={(e) => setSeat(e.target.value)}
      />
      <Button type="submit" variant="secondary" busy={busy}>
        Save agent seat
      </Button>
      <ErrorNotice error={error} />
      <SuccessNotice message={message} />
    </form>
  );
}

export function UserDetailPage() {
  const { userId = "" } = useParams();
  const { state, reload, replace } = useResource(() => admin.getUser(userId), [userId]);
  return (
    <section aria-labelledby="user-title" className="stack">
      <h1 id="user-title">User</h1>
      {state.status === "loading" ? <LoadingState /> : null}
      {state.status === "failed" ? <ErrorState error={state.error} onRetry={reload} /> : null}
      {state.status === "loaded" ? (
        <>
          <p>
            Status: {state.data.status === "ACTIVE" ? "Active" : "Disabled"} · Two-step sign-in:{" "}
            {state.data.mfa_enabled ? "on" : "off"} · Password:{" "}
            {state.data.password_set ? "set" : "invitation pending"}
          </p>
          <Editor key={state.data.id + state.data.status} user={state.data} onSaved={replace} />
          {state.data.roles.includes("MODERATOR") ? (
            <AgentSeat key={`seat-${state.data.id}`} user={state.data} onSaved={replace} />
          ) : null}
        </>
      ) : null}
    </section>
  );
}
