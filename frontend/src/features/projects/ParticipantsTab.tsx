// Participants of a project (PART-*). Names and phone numbers appear only for roles allowed to see
// them; the server decides what each role receives.
import { useState } from "react";

import { apiDownload, type ApiError } from "../../api/client";
import * as work from "../../api/work";
import { useAuth } from "../../auth/AuthContext";
import { Button } from "../../components/form/Button";
import { TextField } from "../../components/form/TextField";
import { ErrorNotice, SuccessNotice } from "../../components/Notice";
import { Pagination } from "../../components/Pagination";
import { EmptyState, ErrorState, LoadingState } from "../../components/StateViews";
import { toApiError, useResource } from "../../hooks/useResource";
import { useProject } from "./ProjectDetailPage";

const EMPTY: work.ParticipantFields = {
  display_label: "",
  phone: null,
  language_code: "",
  dialect: "",
  notes: "",
};

function ParticipantForm({
  initial,
  submitLabel,
  onSubmit,
  busy,
}: {
  initial: work.ParticipantFields;
  submitLabel: string;
  onSubmit: (f: work.ParticipantFields) => void;
  busy: boolean;
}) {
  const [f, setF] = useState(initial);
  return (
    <form
      className="card"
      onSubmit={(e) => {
        e.preventDefault();
        onSubmit({ ...f, phone: f.phone?.trim() ? f.phone : null });
      }}
    >
      <TextField
        label="Name or label"
        required
        value={f.display_label}
        onChange={(e) => setF({ ...f, display_label: e.target.value })}
      />
      <TextField
        label="Phone number"
        hint="International format, e.g. +91 98765 43210. Needed for telephony tasks."
        value={f.phone ?? ""}
        onChange={(e) => setF({ ...f, phone: e.target.value })}
      />
      <TextField
        label="Language code"
        hint="One of the project's languages, e.g. hi."
        required
        value={f.language_code}
        onChange={(e) => setF({ ...f, language_code: e.target.value })}
      />
      <TextField
        label="Dialect"
        value={f.dialect}
        onChange={(e) => setF({ ...f, dialect: e.target.value })}
      />
      <TextField
        label="Internal notes"
        value={f.notes}
        onChange={(e) => setF({ ...f, notes: e.target.value })}
      />
      <Button
        type="submit"
        busy={busy}
        disabled={!f.display_label.trim() || !f.language_code.trim()}
      >
        {submitLabel}
      </Button>
    </form>
  );
}

function ConsentList({ projectId, participantId }: { projectId: string; participantId: string }) {
  const { state, reload } = useResource(
    () => work.consentHistory(projectId, participantId),
    [projectId, participantId],
  );
  if (state.status === "loading") return <LoadingState label="Loading consent" />;
  if (state.status === "failed")
    return <ErrorState message={state.error.message} onRetry={reload} />;
  if (state.data.length === 0) return <p className="muted">No consent recorded yet.</p>;
  return (
    <ul className="list">
      {state.data.map((c) => (
        <li key={c.id}>
          {c.status} ({c.method.toLowerCase().replace(/_/g, " ")}), policy v{c.policy_version},{" "}
          {new Date(c.created_at).toLocaleString()}
        </li>
      ))}
    </ul>
  );
}

export function ParticipantsTab() {
  const { project } = useProject();
  const { can } = useAuth();
  const canManage = can("participants.manage");
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const [adding, setAdding] = useState(false);
  const [editing, setEditing] = useState<work.Participant | null>(null);
  const [consentFor, setConsentFor] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const list = useResource(
    () => work.listParticipants(project.id, { search, page, page_size: 25 }),
    [project.id, search, page],
  );

  async function run(action: () => Promise<string>) {
    setBusy(true);
    setError(null);
    setMessage(null);
    try {
      setMessage(await action());
      list.reload();
    } catch (err) {
      setError(toApiError(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="stack">
      <div className="actions">
        {canManage ? (
          <Button
            onClick={() => {
              setAdding(!adding);
              setEditing(null);
            }}
          >
            {adding ? "Close form" : "Add participant"}
          </Button>
        ) : null}
        {can("participants.export") ? (
          <Button
            variant="secondary"
            onClick={() =>
              void run(async () => {
                await apiDownload(
                  `/api/v1/projects/${project.id}/participants/export`,
                  "participants.csv",
                );
                return "Contact list downloaded.";
              })
            }
          >
            Export contacts
          </Button>
        ) : null}
      </div>
      {adding ? (
        <ParticipantForm
          initial={EMPTY}
          submitLabel="Add participant"
          busy={busy}
          onSubmit={(f) =>
            void run(async () => {
              const p = await work.createParticipant(project.id, f);
              setAdding(false);
              return `${p.participant_code} added.`;
            })
          }
        />
      ) : null}
      {editing ? (
        <ParticipantForm
          key={editing.id}
          initial={{
            display_label: editing.display_label ?? "",
            phone: editing.phone?.startsWith("•") ? null : editing.phone,
            language_code: editing.language_code,
            dialect: editing.dialect,
            notes: editing.notes ?? "",
          }}
          submitLabel={`Save ${editing.participant_code}`}
          busy={busy}
          onSubmit={(f) =>
            void run(async () => {
              const p = await work.correctParticipant(project.id, editing.id, f);
              setEditing(null);
              return `${p.participant_code} corrected.`;
            })
          }
        />
      ) : null}
      <ErrorNotice error={error} />
      <SuccessNotice message={message} />
      <TextField
        label="Search by code or name"
        type="search"
        value={search}
        onChange={(e) => {
          setSearch(e.target.value);
          setPage(1);
        }}
      />
      {list.state.status === "loading" ? <LoadingState label="Loading participants" /> : null}
      {list.state.status === "failed" ? (
        <ErrorState message={list.state.error.message} onRetry={list.reload} />
      ) : null}
      {list.state.status === "loaded" && list.state.data.items.length === 0 ? (
        <EmptyState title="No participants yet" />
      ) : null}
      {list.state.status === "loaded" && list.state.data.items.length > 0 ? (
        <>
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th scope="col">Code</th>
                  <th scope="col">Name</th>
                  <th scope="col">Phone</th>
                  <th scope="col">Language</th>
                  <th scope="col">Actions</th>
                </tr>
              </thead>
              <tbody>
                {list.state.data.items.map((p) => (
                  <tr key={p.id}>
                    <td>{p.participant_code}</td>
                    <td>{p.display_label ?? <span className="muted">Hidden</span>}</td>
                    <td>
                      {p.phone ?? (p.has_phone ? <span className="muted">Hidden</span> : "None")}
                    </td>
                    <td>
                      {p.language_code}
                      {p.dialect ? ` (${p.dialect})` : ""}
                    </td>
                    <td className="actions">
                      {p.consent_visible ? (
                        <Button
                          variant="secondary"
                          onClick={() => setConsentFor(consentFor === p.id ? null : p.id)}
                        >
                          Consent
                        </Button>
                      ) : null}
                      {canManage ? (
                        <>
                          <Button
                            variant="secondary"
                            onClick={() => {
                              setEditing(p);
                              setAdding(false);
                            }}
                          >
                            Correct
                          </Button>
                          <Button
                            variant="secondary"
                            busy={busy}
                            onClick={() => {
                              const reason = window.prompt(
                                `Why delete ${p.participant_code}? Personal data will be removed.`,
                              );
                              if (reason)
                                void run(async () => {
                                  await work.deleteParticipant(project.id, p.id, reason);
                                  return `${p.participant_code} deleted.`;
                                });
                            }}
                          >
                            Delete
                          </Button>
                        </>
                      ) : null}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {consentFor ? (
            <section className="card" aria-label="Consent history">
              <h2>Consent history</h2>
              <ConsentList projectId={project.id} participantId={consentFor} />
            </section>
          ) : null}
          <Pagination page={page} pageSize={25} total={list.state.data.total} onPage={setPage} />
        </>
      ) : null}
    </div>
  );
}
