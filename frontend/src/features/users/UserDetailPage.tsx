// Edit one user: name, email, roles, status, password link, sessions, phone seat
// (USER-001..003, USER-008).
import { useState } from "react";
import { useParams } from "react-router";

import * as admin from "../../api/admin";
import { setAgentSeat, showSeatPassword } from "../../api/telephony";
import { BackLink } from "../../components/BackLink";
import { useConfirm } from "../../components/ConfirmDialog";
import { Button } from "../../components/form/Button";
import { TextField } from "../../components/form/TextField";
import { ErrorNotice, SuccessNotice } from "../../components/Notice";
import { SavedPassword } from "../../components/SavedPassword";
import { ErrorState, LoadingState } from "../../components/StateViews";
import { useAction } from "../../hooks/useAction";
import { useResource } from "../../hooks/useResource";
import { RoleCheckboxes } from "./RoleCheckboxes";

function Editor({ user, onSaved }: { user: admin.User; onSaved: (u: admin.User) => void }) {
  const [name, setName] = useState(user.display_name);
  const [email, setEmail] = useState(user.email);
  const [roles, setRoles] = useState(user.roles);
  const { busy, error, message, run, setMessage } = useAction();
  const confirm = useConfirm(setMessage);
  const active = user.status === "ACTIVE";

  const save = () =>
    void run(async () => {
      let updated = await admin.updateUser(user.id, { display_name: name, email });
      if ([...roles].sort().join() !== [...user.roles].sort().join()) {
        updated = await admin.setUserRoles(user.id, roles);
      }
      onSaved(updated);
      return "Saved.";
    }, "save");
  const enable = () =>
    void run(async () => {
      onSaved(await admin.setUserStatus(user.id, true));
      return "Account enabled.";
    }, "status");
  const disable = () =>
    confirm.ask({
      title: `Disable the account of ${user.display_name}?`,
      message: "They are signed out and cannot sign in until the account is enabled again.",
      confirmLabel: "Disable account",
      danger: true,
      action: async () => {
        onSaved(await admin.setUserStatus(user.id, false));
        return "Account disabled.";
      },
    });
  const signOutEverywhere = () =>
    confirm.ask({
      title: `Sign ${user.display_name} out everywhere?`,
      message: "Every device they are signed in on is signed out.",
      confirmLabel: "Sign out everywhere",
      action: async () =>
        `${(await admin.revokeUserSessions(user.id)).sessions_revoked} session(s) signed out.`,
    });
  const resetTwoStep = () =>
    confirm.ask({
      title: `Reset two-step sign-in for ${user.display_name}?`,
      message:
        "Only when they have lost their authenticator. They are signed out and set it up again at their next sign-in.",
      confirmLabel: "Reset two-step sign-in",
      danger: true,
      action: async () => {
        await admin.resetUserMfa(user.id);
        onSaved({ ...user, mfa_enabled: false });
        return "Two-step sign-in reset. They are signed out everywhere.";
      },
    });

  return (
    <div className="stack">
      <div className="actions" role="group" aria-label="Account actions">
        <Button
          variant="secondary"
          icon={active ? "prohibit" : "ok"}
          busy={busy === "status"}
          disabled={busy !== null}
          onClick={active ? disable : enable}
        >
          {active ? "Disable account" : "Enable account"}
        </Button>
        <Button
          variant="secondary"
          icon="mail"
          busy={busy === "link"}
          disabled={!active || busy !== null}
          onClick={() =>
            void run(
              async () =>
                (await admin.sendPasswordLink(user.id)).sent
                  ? "Password link sent by email."
                  : "The email could not be sent. Check the email settings.",
              "link",
            )
          }
        >
          Send password link
        </Button>
        <Button
          variant="secondary"
          icon="logout"
          disabled={busy !== null}
          onClick={signOutEverywhere}
        >
          Sign out everywhere
        </Button>
        {user.mfa_enabled ? (
          <Button variant="secondary" icon="key" disabled={busy !== null} onClick={resetTwoStep}>
            Reset two-step sign-in
          </Button>
        ) : null}
      </div>
      <form
        noValidate
        className="card"
        onSubmit={(e) => {
          e.preventDefault();
          save();
        }}
      >
        <h2>Details</h2>
        <TextField label="Name" required value={name} onChange={(e) => setName(e.target.value)} />
        <TextField
          label="Email"
          type="email"
          required
          value={email}
          onChange={(e) => setEmail(e.target.value)}
        />
        <RoleCheckboxes value={roles} onChange={setRoles} />
        <Button type="submit" busy={busy === "save"} disabled={roles.length === 0}>
          Save changes
        </Button>
      </form>
      <ErrorNotice error={error} />
      <SuccessNotice message={message} />
      {confirm.dialog}
    </div>
  );
}

/** The phone seat a moderator's calls go through (D-101), one seat per person, and its password
 * for the Chirp app (D-130). The saved password is never sent to the page unless asked for. */
function PhoneSeat({ user, onSaved }: { user: admin.User; onSaved: (u: admin.User) => void }) {
  const [seat, setSeat] = useState(user.telephony_agent_id ?? "");
  const [password, setPassword] = useState("");
  // A new save may change the password: whatever was shown before is hidden again.
  const [saves, setSaves] = useState(0);
  const { busy, error, message, run } = useAction();
  return (
    <form
      className="card"
      noValidate
      onSubmit={(e) => {
        e.preventDefault();
        void run(async () => {
          const r = await setAgentSeat(user.id, seat.trim(), password);
          onSaved({
            ...user,
            telephony_agent_id: r.telephony_agent_id,
            telephony_has_password: r.has_password,
          });
          setPassword("");
          setSaves((n) => n + 1);
          return r.telephony_agent_id ? "Phone seat saved." : "Phone seat removed.";
        });
      }}
    >
      <h2>Phone calls</h2>
      <TextField
        label="Seat number"
        hint="The seat number TxContact gave for this moderator (for example 80003). One seat per person."
        value={seat}
        maxLength={40}
        onChange={(e) => setSeat(e.target.value)}
      />
      <TextField
        label="Seat password"
        type="password"
        autoComplete="new-password"
        hint={
          user.telephony_has_password
            ? "Leave empty to keep the saved password."
            : "The password TxContact gave for this seat. The portal signs the moderator's phone line in with it."
        }
        value={password}
        maxLength={200}
        onChange={(e) => setPassword(e.target.value)}
      />
      {user.telephony_has_password ? (
        <SavedPassword key={saves} label="Saved password" load={() => showSeatPassword(user.id)} />
      ) : null}
      <Button type="submit" variant="secondary" icon="phone" busy={busy !== null}>
        Save phone seat
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
      <BackLink to="/admin/users">All users</BackLink>
      <h1 id="user-title">{state.status === "loaded" ? state.data.display_name : "User"}</h1>
      {state.status === "loading" ? <LoadingState /> : null}
      {state.status === "failed" ? <ErrorState error={state.error} onRetry={reload} /> : null}
      {state.status === "loaded" ? (
        <>
          <p>
            Status: {state.data.status === "ACTIVE" ? "Active" : "Disabled"} · Two-step sign-in:{" "}
            {state.data.mfa_enabled ? "on" : "off"} · Password:{" "}
            {state.data.password_set ? "set" : "invitation pending"}
          </p>
          <Editor key={state.data.id} user={state.data} onSaved={replace} />
          {/* Also for someone who is no longer a moderator but still holds a seat: it can be
              freed for the next person. */}
          {state.data.roles.includes("MODERATOR") || state.data.telephony_agent_id ? (
            <PhoneSeat key={`seat-${state.data.id}`} user={state.data} onSaved={replace} />
          ) : null}
        </>
      ) : null}
    </section>
  );
}
