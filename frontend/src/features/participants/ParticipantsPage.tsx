// Participants section (D-073): everyone in a project in one place, with the work done on many at
// once - add from a file, assign to another project, send consent forms, remove - and the review
// of each participant's own consent answer (approve, reject with a note, resend the form).
import { useState } from "react";

import { apiDownload, type ApiError } from "../../api/client";
import { listProjects } from "../../api/projects";
import * as work from "../../api/work";
import { Button } from "../../components/form/Button";
import { Select } from "../../components/form/Select";
import { TextField } from "../../components/form/TextField";
import { Icon, IconTile } from "../../components/Icon";
import { ErrorNotice, SuccessNotice } from "../../components/Notice";
import { Pagination } from "../../components/Pagination";
import { EmptyState, ErrorState, LoadingState } from "../../components/StateViews";
import { StatusBadge } from "../../components/StatusBadge";
import { toApiError, useResource } from "../../hooks/useResource";
import { ConsentList, EMPTY, ParticipantForm } from "../projects/ParticipantsTab";

const ANSWER: Record<string, [string, string]> = {
  NONE: ["DRAFT", "Not answered"],
  GIVEN: ["ACTIVE", "Agreed"],
  REFUSED: ["REJECTED", "Did not agree"],
  WITHDRAWN: ["RETURNED", "Withdrawn"],
};
const REVIEW: Record<string, [string, string]> = {
  PENDING: ["ON_HOLD", "Waiting for review"],
  APPROVED: ["APPROVED", "Approved"],
  REJECTED: ["REJECTED", "Sent back"],
};
const SAMPLE = "name,phone,email,language,dialect\nAsha Rao,+919876543210,asha@example.org,hi,\n";

function BulkAdd({ projectId, onDone }: { projectId: string; onDone: () => void }) {
  const [csv, setCsv] = useState("");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<work.ImportResult | null>(null);
  const [error, setError] = useState<ApiError | null>(null);

  function send(confirm: boolean) {
    setBusy(true);
    setError(null);
    work
      .importParticipants(projectId, csv, confirm)
      .then((r) => {
        setResult(r);
        if (confirm) onDone();
      })
      .catch((err: unknown) => setError(toApiError(err)))
      .finally(() => setBusy(false));
  }

  return (
    <section className="card stack stack--tight" aria-labelledby="bulk-add-title">
      <h2 id="bulk-add-title">Add many participants</h2>
      <p className="muted">
        Paste rows or choose a CSV file. First line: <code>name,phone,email,language,dialect</code>.
        Phone, email and dialect may be empty. Check the rows first; only rows without a problem are
        added.
      </p>
      <div className="field">
        <label htmlFor="bulk-csv" className="field__label">
          Participants (CSV)
        </label>
        <textarea
          id="bulk-csv"
          className="field__input mono"
          rows={7}
          placeholder={SAMPLE}
          value={csv}
          onChange={(e) => {
            setCsv(e.target.value);
            setResult(null);
          }}
        />
      </div>
      <div className="actions">
        <label className="button button--secondary">
          <Icon name="upload" size={15} />
          Choose a file
          <input
            type="file"
            accept=".csv,text/csv"
            className="sr-only"
            onChange={(e) => {
              const file = e.target.files?.[0];
              if (file) void file.text().then((t) => (setCsv(t), setResult(null)));
            }}
          />
        </label>
        <Button variant="secondary" busy={busy} disabled={!csv.trim()} onClick={() => send(false)}>
          Check rows
        </Button>
        <Button
          busy={busy}
          disabled={!result || result.ready === 0 || result.created > 0}
          onClick={() => send(true)}
        >
          Add {result?.ready ?? 0} participants
        </Button>
      </div>
      <ErrorNotice error={error} />
      {result ? (
        <>
          <p role="status">
            {result.created > 0
              ? `${result.created} added.`
              : `${result.ready} of ${result.rows.length} rows are ready.`}
          </p>
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th scope="col">Line</th>
                  <th scope="col">Name</th>
                  <th scope="col">Result</th>
                </tr>
              </thead>
              <tbody>
                {result.rows.map((r) => (
                  <tr key={r.line} className={r.ok ? "" : "row--invalid"}>
                    <td>{r.line}</td>
                    <td>{r.name || "-"}</td>
                    <td>
                      {r.message}
                      {r.participant_code ? ` (${r.participant_code})` : ""}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      ) : null}
    </section>
  );
}

const ANSWER_WORDS: Record<string, string> = {
  GIVEN: "Agreed",
  REFUSED: "Did not agree",
  WITHDRAWN: "Withdrew consent",
};
const when = (iso: string) => new Date(iso).toLocaleString();

/** One participant's consent form as they answered it, with a printable download. */
function ConsentFormPanel({
  projectId,
  participantId,
  onClose,
}: {
  projectId: string;
  participantId: string;
  onClose: () => void;
}) {
  const { state, reload } = useResource(
    () => work.consentForm(projectId, participantId),
    [projectId, participantId],
  );
  const [error, setError] = useState<ApiError | null>(null);
  return (
    <section className="card stack stack--tight" aria-label="Consent form">
      {state.status === "loading" ? <LoadingState label="Loading the consent form" /> : null}
      {state.status === "failed" ? <ErrorState error={state.error} onRetry={reload} /> : null}
      {state.status === "loaded" ? (
        <>
          <div className="page-header">
            <h2>Consent form of {state.data.participant_code}</h2>
            <div className="actions">
              <Button
                variant="secondary"
                onClick={() =>
                  void apiDownload(
                    work.consentFormFileUrl(projectId, participantId),
                    `consent_${state.data.project_code}_${state.data.participant_code}.html`,
                  ).catch((err: unknown) => setError(toApiError(err)))
                }
              >
                <Icon name="upload" size={15} />
                Download
              </Button>
              <Button variant="secondary" onClick={onClose}>
                Close
              </Button>
            </div>
          </div>
          <dl className="checks">
            <div className="checks__row">
              <dt>Answer</dt>
              <dd>
                {state.data.current ? ANSWER_WORDS[state.data.current.status] : "Not answered yet"}
              </dd>
            </div>
            {state.data.current ? (
              <div className="checks__row">
                <dt>Answered on</dt>
                <dd>{when(state.data.current.answered_at)}</dd>
              </div>
            ) : null}
            <div className="checks__row">
              <dt>Form version</dt>
              <dd>{state.data.form_version}</dd>
            </div>
            {state.data.current?.review_status ? (
              <div className="checks__row">
                <dt>Review</dt>
                <dd>
                  {REVIEW[state.data.current.review_status]?.[1]}
                  {state.data.current.review_note ? `: ${state.data.current.review_note}` : ""}
                </dd>
              </div>
            ) : null}
          </dl>
          <h3>{state.data.answered ? "Form text they answered" : "Form text they will see"}</h3>
          <div className="consent-doc">
            {state.data.form_text.trim() || "No consent form has been written for this project."}
          </div>
          {state.data.earlier.length > 0 ? (
            <>
              <h3>Earlier answers</h3>
              <ul className="list">
                {state.data.earlier.map((a) => (
                  <li key={a.answered_at}>
                    {when(a.answered_at)} · {ANSWER_WORDS[a.status]} · version {a.policy_version}
                  </li>
                ))}
              </ul>
            </>
          ) : null}
          <ErrorNotice error={error} />
        </>
      ) : null}
    </section>
  );
}

export function ParticipantsPage() {
  const projects = useResource(() => listProjects({ page: 1, page_size: 100 }), []);
  const [chosen, setChosen] = useState("");
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const [panel, setPanel] = useState<"add" | "bulk" | null>(null);
  const [editing, setEditing] = useState<work.Participant | null>(null);
  const [consentFor, setConsentFor] = useState<string | null>(null);
  const [viewing, setViewing] = useState<string | null>(null);
  const [selected, setSelected] = useState<string[]>([]);
  const [target, setTarget] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [outcome, setOutcome] = useState<work.BulkResult | null>(null);

  const all = projects.state.status === "loaded" ? projects.state.data.items : [];
  const projectId = chosen || all[0]?.id || "";
  const list = useResource(
    () =>
      projectId
        ? work.listParticipants(projectId, { search, page, page_size: 25 })
        : Promise.resolve(null),
    [projectId, search, page],
  );
  const rows = list.state.status === "loaded" && list.state.data ? list.state.data.items : [];
  const live = rows.filter((p) => !p.deleted);

  async function run(action: () => Promise<string>) {
    setBusy(true);
    setError(null);
    setMessage(null);
    setOutcome(null);
    try {
      setMessage(await action());
      list.reload();
    } catch (err) {
      setError(toApiError(err));
    } finally {
      setBusy(false);
    }
  }
  const bulk = (
    action: "assign" | "remove" | "send_consent",
    extra: { target_project_id?: string; reason?: string } = {},
  ) =>
    run(async () => {
      const r = await work.bulkParticipants(projectId, {
        action,
        participant_ids: selected,
        ...extra,
      });
      setOutcome(r);
      setSelected([]);
      return `${r.done} done, ${r.failed} not done.`;
    });
  const toggle = (id: string) =>
    setSelected(selected.includes(id) ? selected.filter((x) => x !== id) : [...selected, id]);

  if (projects.state.status === "loading") return <LoadingState label="Loading projects" />;
  if (projects.state.status === "failed")
    return <ErrorState error={projects.state.error} onRetry={projects.reload} />;

  return (
    <section aria-labelledby="participants-title" className="stack">
      <div className="page-header">
        <h1 id="participants-title">
          <IconTile name="people" tone="blue" />
          Participants
        </h1>
        <div className="actions">
          <Button
            variant="secondary"
            disabled={!projectId}
            onClick={() => (setPanel(panel === "bulk" ? null : "bulk"), setEditing(null))}
          >
            <Icon name="upload" size={15} />
            Add many
          </Button>
          <Button
            disabled={!projectId}
            onClick={() => (setPanel(panel === "add" ? null : "add"), setEditing(null))}
          >
            <Icon name="plus" size={15} weight="bold" />
            Add participant
          </Button>
        </div>
      </div>
      {all.length === 0 ? (
        <EmptyState title="No projects" message="You are not a member of any project yet." />
      ) : (
        <div className="filters">
          <Select
            label="Project"
            value={projectId}
            onChange={(e) => {
              setChosen(e.target.value);
              setPage(1);
              setSelected([]);
              setOutcome(null);
            }}
            options={all.map((p) => ({ value: p.id, label: `${p.code} · ${p.name}` }))}
          />
          <TextField
            label="Search by name or code"
            type="search"
            value={search}
            onChange={(e) => {
              setSearch(e.target.value);
              setPage(1);
            }}
          />
        </div>
      )}
      {panel === "add" && projectId ? (
        <ParticipantForm
          initial={EMPTY}
          submitLabel="Add participant"
          busy={busy}
          onSubmit={(f) =>
            void run(async () => {
              const p = await work.createParticipant(projectId, f);
              setPanel(null);
              return `${p.participant_code} added.`;
            })
          }
        />
      ) : null}
      {panel === "bulk" && projectId ? (
        <BulkAdd projectId={projectId} onDone={() => list.reload()} />
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
            email: editing.email ?? (editing.has_email ? undefined : ""),
          }}
          submitLabel={`Save ${editing.participant_code}`}
          busy={busy}
          onSubmit={(f) =>
            void run(async () => {
              await work.correctParticipant(projectId, editing.id, f);
              setEditing(null);
              return `${editing.participant_code} saved.`;
            })
          }
        />
      ) : null}
      <ErrorNotice error={error} />
      <SuccessNotice message={message} />
      {outcome && outcome.failed > 0 ? (
        <ul className="notice notice--error list" aria-label="Not done">
          {outcome.results
            .filter((r) => !r.ok)
            .map((r) => (
              <li key={r.participant_id}>
                {r.participant_code}: {r.message}
              </li>
            ))}
        </ul>
      ) : null}
      {selected.length > 0 ? (
        <div className="card bulkbar" role="group" aria-label="Actions for selected participants">
          <strong>{selected.length} selected</strong>
          <Button variant="secondary" busy={busy} onClick={() => void bulk("send_consent")}>
            <Icon name="mail" size={15} />
            Send consent form
          </Button>
          <Select
            label="Assign to project"
            value={target}
            onChange={(e) => setTarget(e.target.value)}
            options={[
              { value: "", label: "Choose a project" },
              ...all
                .filter((p) => p.id !== projectId)
                .map((p) => ({ value: p.id, label: `${p.code} · ${p.name}` })),
            ]}
          />
          <Button
            variant="secondary"
            busy={busy}
            disabled={!target}
            onClick={() => void bulk("assign", { target_project_id: target })}
          >
            Assign
          </Button>
          <Button
            variant="secondary"
            busy={busy}
            onClick={() => {
              const reason = window.prompt(
                `Why remove ${selected.length} participant(s)? Their personal data will be deleted.`,
              );
              if (reason) void bulk("remove", { reason });
            }}
          >
            <Icon name="trash" size={15} />
            Remove
          </Button>
        </div>
      ) : null}
      {list.state.status === "loading" ? <LoadingState label="Loading participants" /> : null}
      {list.state.status === "failed" ? (
        <ErrorState error={list.state.error} onRetry={list.reload} />
      ) : null}
      {list.state.status === "loaded" && list.state.data && rows.length === 0 ? (
        <EmptyState
          title="No participants"
          message="Add one, or add many from a file, to get started."
        />
      ) : null}
      {rows.length > 0 && list.state.status === "loaded" && list.state.data ? (
        <>
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th scope="col">
                    <input
                      type="checkbox"
                      aria-label="Select all on this page"
                      checked={live.length > 0 && live.every((p) => selected.includes(p.id))}
                      onChange={(e) => setSelected(e.target.checked ? live.map((p) => p.id) : [])}
                    />
                  </th>
                  <th scope="col">Code</th>
                  <th scope="col">Name</th>
                  <th scope="col">Contact</th>
                  <th scope="col">Language</th>
                  <th scope="col">Consent form</th>
                  <th scope="col">Actions</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((p) => {
                  const answer = ANSWER[p.consent_status ?? ""];
                  const review = REVIEW[p.consent_review ?? ""];
                  return (
                    <tr key={p.id}>
                      <td>
                        {p.deleted ? null : (
                          <input
                            type="checkbox"
                            aria-label={`Select ${p.participant_code}`}
                            checked={selected.includes(p.id)}
                            onChange={() => toggle(p.id)}
                          />
                        )}
                      </td>
                      <td className="mono">{p.participant_code}</td>
                      <td>{p.display_label ?? <span className="muted">Hidden</span>}</td>
                      <td>
                        {p.phone ?? (p.has_phone ? "Phone on file" : "")}
                        {p.has_email ? (
                          <div className="muted">{p.email ?? "Email on file"}</div>
                        ) : null}
                      </td>
                      <td>
                        {p.language_code}
                        {p.dialect ? ` (${p.dialect})` : ""}
                      </td>
                      <td>
                        <span className="actions">
                          {answer ? <StatusBadge status={answer[0]} label={answer[1]} /> : null}
                          {p.consent_status === "GIVEN" && review ? (
                            <StatusBadge status={review[0]} label={review[1]} />
                          ) : null}
                        </span>
                      </td>
                      <td className="actions">
                        {p.deleted ? (
                          <span className="muted">Removed</span>
                        ) : (
                          <>
                            {p.consent_status === "GIVEN" && p.consent_review !== "APPROVED" ? (
                              <Button
                                variant="secondary"
                                busy={busy}
                                onClick={() =>
                                  void run(async () => {
                                    await work.reviewConsent(projectId, p.id, "APPROVED");
                                    return `Consent of ${p.participant_code} approved.`;
                                  })
                                }
                              >
                                Approve
                              </Button>
                            ) : null}
                            {p.consent_status === "GIVEN" && p.consent_review !== "REJECTED" ? (
                              <Button
                                variant="secondary"
                                busy={busy}
                                onClick={() => {
                                  const note = window.prompt(
                                    `Why is the consent of ${p.participant_code} not accepted? The participant will see this.`,
                                  );
                                  if (note)
                                    void run(async () => {
                                      await work.reviewConsent(projectId, p.id, "REJECTED", note);
                                      return `Consent of ${p.participant_code} sent back.`;
                                    });
                                }}
                              >
                                Reject
                              </Button>
                            ) : null}
                            {p.has_email ? (
                              <Button
                                variant="secondary"
                                busy={busy}
                                onClick={() =>
                                  void run(async () => {
                                    const r = await work.emailPortalLink(projectId, p.id);
                                    if (!r.sent) throw new Error("The email could not be sent.");
                                    return `Consent form sent to ${p.participant_code}.`;
                                  })
                                }
                              >
                                {p.link_active ? "Resend" : "Send"}
                              </Button>
                            ) : null}
                            <Button
                              variant="secondary"
                              onClick={() => (
                                setViewing(viewing === p.id ? null : p.id),
                                setConsentFor(null)
                              )}
                            >
                              View
                            </Button>
                            <Button
                              variant="secondary"
                              onClick={() => (
                                setConsentFor(consentFor === p.id ? null : p.id),
                                setViewing(null)
                              )}
                            >
                              History
                            </Button>
                            <Button
                              variant="secondary"
                              onClick={() => (setEditing(p), setPanel(null))}
                            >
                              Correct
                            </Button>
                          </>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          {viewing ? (
            <ConsentFormPanel
              key={viewing}
              projectId={projectId}
              participantId={viewing}
              onClose={() => setViewing(null)}
            />
          ) : null}
          {consentFor ? (
            <section className="card" aria-label="Consent history">
              <h2>Consent history</h2>
              <ConsentList projectId={projectId} participantId={consentFor} />
            </section>
          ) : null}
          <Pagination page={page} pageSize={25} total={list.state.data.total} onPage={setPage} />
        </>
      ) : null}
    </section>
  );
}
