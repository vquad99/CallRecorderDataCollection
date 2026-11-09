// Create a user and send the invitation (USER-001, USER-002).
import { useState, type FormEvent } from "react";
import { Link } from "react-router";

import { createUser, type User } from "../../api/admin";
import type { ApiError } from "../../api/client";
import { Button } from "../../components/form/Button";
import { TextField } from "../../components/form/TextField";
import { ErrorNotice, SuccessNotice } from "../../components/Notice";
import { toApiError } from "../../hooks/useResource";
import { RoleCheckboxes } from "./RoleCheckboxes";

export function UserCreatePage() {
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [roles, setRoles] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const [created, setCreated] = useState<{ user: User; invite_sent: boolean } | null>(null);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      setCreated(await createUser({ email, display_name: name, roles }));
    } catch (err) {
      setError(toApiError(err));
    } finally {
      setBusy(false);
    }
  }

  if (created) {
    return (
      <section className="stack">
        <h1>User added</h1>
        <SuccessNotice
          message={
            created.invite_sent
              ? `${created.user.email} was invited by email to set a password.`
              : `${created.user.email} was added, but the invitation email could not be sent. Use "Send password link" on the user page.`
          }
        />
        <Link to={`/admin/users/${created.user.id}`}>Open user</Link>
      </section>
    );
  }

  return (
    <section aria-labelledby="new-user-title" className="stack">
      <h1 id="new-user-title">Add user</h1>
      <form onSubmit={submit} noValidate className="card">
        <TextField
          label="Email"
          type="email"
          required
          value={email}
          onChange={(e) => setEmail(e.target.value)}
        />
        <TextField label="Name" required value={name} onChange={(e) => setName(e.target.value)} />
        <RoleCheckboxes value={roles} onChange={setRoles} />
        <ErrorNotice error={error} />
        <Button type="submit" busy={busy} disabled={!email || !name || roles.length === 0}>
          Add and send invitation
        </Button>
      </form>
    </section>
  );
}
