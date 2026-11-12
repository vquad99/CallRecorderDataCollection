// Participants of a project (PART-*). Names and phone numbers appear only for roles allowed to see
// them; the server decides what each role receives.
import { useEffect, useState } from "react";

import { apiDownload, type ApiError } from "../../api/client";
import * as work from "../../api/work";
import { useAuth } from "../../auth/AuthContext";
import type { Language } from "../../api/projects";
import { Button } from "../../components/form/Button";
import { Select } from "../../components/form/Select";
import { TextField } from "../../components/form/TextField";
import { ErrorNotice, SuccessNotice } from "../../components/Notice";
import { Pagination } from "../../components/Pagination";
import { EmptyState, ErrorState, LoadingState } from "../../components/StateViews";
import { toApiError, useResource } from "../../hooks/useResource";
import { COUNTRY_CODES, languageLabel, languageOptions, PHONE_DIGITS, splitPhone } from "./choices";
import { useProject } from "./ProjectDetailPage";

export const EMPTY: work.ParticipantFields = {
  display_label: "",
  phone: null,
  language_code: "",
  dialect: "",
  notes: "",
};

export function ParticipantForm({
  initial,
  languages,
  submitLabel,
  onSubmit,
  busy,
}: {
  initial: work.ParticipantFields;
  languages: readonly Language[]; // the project's languages; empty means any
  submitLabel: string;
  onSubmit: (f: work.ParticipantFields) => void;
  busy: boolean;
}) {
  const [f, setF] = useState(initial);
  const [phone, setPhone] = useState(() => splitPhone(initial.phone));
  const phoneError =
    phone.digits && phone.digits.length !== PHONE_DIGITS
      ? `Type exactly ${PHONE_DIGITS} digits (you typed ${phone.digits.length}).`
      : undefined;
  return (
    <form
      className="card"
      onSubmit={(e) => {
        e.preventDefault();
        if (phoneError) return;
        onSubmit({
          ...f,
          phone: phone.digits ? `${phone.cc}${phone.digits}` : null,
          email: f.email?.trim(),
        });
      }}
    >
      <TextField
        label="Name or label"
        required
        value={f.display_label}
        onChange={(e) => setF({ ...f, display_label: e.target.value })}
      />
      <Select
        label="Country code"
        value={phone.cc}
        onChange={(e) => setPhone({ ...phone, cc: e.target.value })}
        options={COUNTRY_CODES.map((c) => ({ value: c.code, label: `${c.code} ${c.name}` }))}
      />
      <TextField
        label="Phone number"
        hint={`${PHONE_DIGITS} digits, without the country code. Needed for telephony tasks.`}
        inputMode="numeric"
        autoComplete="tel-national"
        maxLength={PHONE_DIGITS}
        value={phone.digits}
        {...(phoneError ? { error: phoneError } : {})}
        onChange={(e) => setPhone({ ...phone, digits: e.target.value.replace(/\D/g, "") })}
      />
      <TextField
        label="Email address"
        type="email"
        hint="Optional. Used to send the participant their consent form link."
        value={f.email ?? ""}
        onChange={(e) => setF({ ...f, email: e.target.value })}
      />
      <Select
        label="Language code"
        required
        value={f.language_code}
        onChange={(e) => setF({ ...f, language_code: e.target.value })}
        options={languageOptions(languages, initial.language_code)}
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
        disabled={!f.display_label.trim() || !f.language_code.trim() || Boolean(phoneError)}
      >
        {submitLabel}
      </Button>
    </form>
  );
}

/** People who already exist in another of the caller's projects, added here as they are (D-090). */
function AddExisting({
  projectId,
  refresh,
  busy,
  onAdd,
}: {
  projectId: string;
  refresh: number;
  busy: boolean;
  onAdd: (code: string) => void;
}) {
  const [typed, setTyped] = useState("");
  const [search, setSearch] = useState("");
  // Ask the server once typing pauses, not on every key.
  useEffect(() => {
    const id = window.setTimeout(() => setSearch(typed.trim()), 300);
    return () => window.clearTimeout(id);
  }, [typed]);
  const found = useResource(
    () => work.linkCandidates(projectId, search),
    [projectId, search, refresh],
  );
  const people = found.state.status === "loaded" ? found.state.data : [];
  return (
    <section className="card pick" aria-labelledby="add-existing-title">
      <div className="pick__head">
        <div>
          <h2 id="add-existing-title">Add an existing participant</h2>
          <p className="muted">
            People from your other projects who are not in this one yet. They keep their code,
            details and consent history.
          </p>
        </div>
        {found.state.status === "loaded" ? (
          <span className="pick__count">
            {people.length === 1 ? "1 person" : `${people.length} people`}
          </span>
        ) : null}
      </div>
      <TextField
        label="Search your other projects"
        type="search"
        placeholder="Code or name, e.g. P000123"
        value={typed}
        onChange={(e) => setTyped(e.target.value)}
      />
      {found.state.status === "loading" ? <LoadingState label="Searching" /> : null}
      {found.state.status === "failed" ? (
        <ErrorState error={found.state.error} onRetry={found.reload} />
      ) : null}
      {found.state.status === "loaded" && people.length === 0 ? (
        <p className="pick__empty">
          {search ? `No one matches "${search}".` : "No one to add: everyone is already here."}
        </p>
      ) : null}
      {people.length > 0 ? (
        <ul className="pick__list">
          {people.map((c) => (
            <li key={c.id} className="pick__row">
              <span className="pick__code">{c.participant_code}</span>
              <span className="pick__name">{c.display_label ?? "Name hidden"}</span>
              <span className="pick__meta">
                {languageLabel(c.language_code)}
                {c.dialect ? ` · ${c.dialect}` : ""}
              </span>
              <Button
                variant="secondary"
                busy={busy}
                aria-label={`Add ${c.participant_code}`}
                onClick={() => onAdd(c.participant_code)}
              >
                Add
              </Button>
            </li>
          ))}
        </ul>
      ) : null}
    </section>
  );
}

export function ConsentList({
  projectId,
  participantId,
}: {
  projectId: string;
  participantId: string;
}) {
  const { state, reload } = useResource(
    () => work.consentHistory(projectId, participantId),
    [projectId, participantId],
  );
  if (state.status === "loading") return <LoadingState label="Loading consent" />;
  if (state.status === "failed") return <ErrorState error={state.error} onRetry={reload} />;
  if (state.data.length === 0) return <p className="muted">No consent recorded yet.</p>;
  return (
    <ul className="list">
      {state.data.map((c) => (
        <li key={c.id}>
          {c.status} ({c.method.toLowerCase().replace(/_/g, " ")}), policy v{c.policy_version},{" "}
          {new Date(c.created_at).toLocaleString()}
          {c.captured_by === null ? " · answered by the participant" : ""}
        </li>
      ))}
    </ul>
  );
}

const minutesText = (value: number | undefined) =>
  value === undefined ? "–" : value.toLocaleString(undefined, { maximumFractionDigits: 2 });

export function ParticipantsTab() {
  const { project } = useProject();
  const { can } = useAuth();
  const canManage = can("participants.manage");
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const [adding, setAdding] = useState(false);
  const [editing, setEditing] = useState<work.Participant | null>(null);
  const [consentFor, setConsentFor] = useState<string | null>(null);
  const [link, setLink] = useState<{ code: string; url: string; expires_at: string } | null>(null);
  const [addingExisting, setAddingExisting] = useState(false);
  const [refresh, setRefresh] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const list = useResource(
    () => work.listParticipants(project.id, { search, page, page_size: 25 }),
    [project.id, search, page],
  );

  // The server sends minutes only to people who may export the project (D-095).
  const showMinutes =
    list.state.status === "loaded" && list.state.data.items.some((p) => p.minutes != null);

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
              setAddingExisting(false);
              setEditing(null);
            }}
          >
            {adding ? "Close form" : "Add participant"}
          </Button>
        ) : null}
        {canManage ? (
          <Button
            variant="secondary"
            onClick={() => {
              setAddingExisting(!addingExisting);
              setAdding(false);
              setEditing(null);
            }}
          >
            {addingExisting ? "Close search" : "Add existing participant"}
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
      {addingExisting ? (
        <AddExisting
          projectId={project.id}
          refresh={refresh}
          busy={busy}
          onAdd={(code) =>
            void run(async () => {
              await work.linkParticipant(project.id, code);
              setRefresh((n) => n + 1);
              return `${code} added to this project.`;
            })
          }
        />
      ) : null}
      {adding ? (
        <ParticipantForm
          initial={EMPTY}
          languages={project.languages}
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
          languages={project.languages}
          initial={{
            display_label: editing.display_label ?? "",
            phone: editing.phone?.startsWith("•") ? null : editing.phone,
            language_code: editing.language_code,
            dialect: editing.dialect,
            notes: editing.notes ?? "",
            email: editing.email ?? (editing.has_email ? undefined : ""),
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
        <ErrorState error={list.state.error} onRetry={list.reload} />
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
                  {showMinutes ? (
                    <>
                      <th scope="col" className="num">
                        Recorded min
                      </th>
                      <th scope="col" className="num">
                        Approved min
                      </th>
                      <th
                        scope="col"
                        className="num"
                        title="Half of approved: two participants share each conversation"
                      >
                        Payable min
                      </th>
                    </>
                  ) : null}
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
                    {showMinutes ? (
                      <>
                        <td className="num">{minutesText(p.minutes?.recorded_minutes)}</td>
                        <td className="num">{minutesText(p.minutes?.approved_minutes)}</td>
                        <td className="num">
                          <strong>{minutesText(p.minutes?.payable_minutes)}</strong>
                        </td>
                      </>
                    ) : null}
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
                            busy={busy}
                            onClick={() => {
                              setLink(null);
                              void run(async () => {
                                const made = await work.createPortalLink(project.id, p.id);
                                setLink({ code: p.participant_code, ...made });
                                return `Personal link created for ${p.participant_code}.`;
                              });
                            }}
                          >
                            Personal link
                          </Button>
                          {p.has_email ? (
                            <Button
                              variant="secondary"
                              busy={busy}
                              onClick={() => {
                                setLink(null);
                                void run(async () => {
                                  const r = await work.emailPortalLink(project.id, p.id);
                                  if (!r.sent) throw new Error("The email could not be sent.");
                                  return `Consent form link emailed to ${p.participant_code}.`;
                                });
                              }}
                            >
                              Email consent link
                            </Button>
                          ) : null}
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
          {link ? (
            <section className="card stack stack--tight" aria-label="Personal link">
              <h2>Personal link for {link.code}</h2>
              <p className="muted">
                Give this link to the participant only. It opens their consent form and their own
                sessions, works until {new Date(link.expires_at).toLocaleDateString()}, and is shown
                once: creating a new link ends this one.
              </p>
              <p className="mono break">{link.url}</p>
              <div className="actions">
                <Button
                  variant="secondary"
                  onClick={() => void navigator.clipboard.writeText(link.url)}
                >
                  Copy link
                </Button>
                <Button variant="secondary" onClick={() => setLink(null)}>
                  Hide
                </Button>
              </div>
            </section>
          ) : null}
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
