// Participants section (D-073): everyone in a project in one place, with the work done on many at
// once - add from a file, assign to another project, remove - and each participant's own answer
// on the consent form. The form is emailed by itself to everyone who joins a project and an
// answer counts at once (D-129); "Email consent form again" is for an email that was lost.
import { useState } from "react";

import { getProject, listProjects } from "../../api/projects";
import * as work from "../../api/work";
import { useConfirm } from "../../components/ConfirmDialog";
import { DataTable } from "../../components/DataTable";
import { Button } from "../../components/form/Button";
import { Select } from "../../components/form/Select";
import { TextField } from "../../components/form/TextField";
import { Icon, IconTile } from "../../components/Icon";
import { ErrorNotice, SuccessNotice } from "../../components/Notice";
import { Pagination } from "../../components/Pagination";
import { EmptyState, ErrorState, LoadingState } from "../../components/StateViews";
import { StatusBadge } from "../../components/StatusBadge";
import { useAction } from "../../hooks/useAction";
import { useResource } from "../../hooks/useResource";
import { consentAnswer } from "../../lib/labels";
import { languageLabel } from "../projects/choices";
import { useParticipantWindows } from "./ParticipantEditor";

const SAMPLE =
  "name,phone,email,language,dialect,district\nAsha Rao,+919876543210,asha@example.org,hi,,Pune\n";

type BulkAction = "assign" | "remove" | "send_consent";

function BulkAdd({ projectId, onDone }: { projectId: string; onDone: () => void }) {
  const [csv, setCsv] = useState("");
  const [result, setResult] = useState<work.ImportResult | null>(null);
  const { busy, error, run } = useAction();
  const send = (confirm: boolean) =>
    void run(
      async () => {
        const r = await work.importParticipants(projectId, csv, confirm);
        setResult(r);
        if (confirm) onDone();
      },
      confirm ? "add" : "check",
    );

  return (
    <section className="card stack stack--tight" aria-labelledby="bulk-add-title">
      <h2 id="bulk-add-title">Add many participants</h2>
      <p className="muted">
        Paste rows or choose a CSV file. First line:{" "}
        <code>name,phone,email,language,dialect,district</code>. Every row needs an email; phone,
        dialect and district may be empty. Check the rows first; only rows without a problem are
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
        <Button
          variant="secondary"
          busy={busy === "check"}
          disabled={!csv.trim() || busy !== null}
          onClick={() => send(false)}
        >
          Check rows
        </Button>
        <Button
          busy={busy === "add"}
          disabled={!result || result.ready === 0 || result.created > 0 || busy !== null}
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
          <DataTable>
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
          </DataTable>
        </>
      ) : null}
    </section>
  );
}

export function ParticipantsPage() {
  const projects = useResource(() => listProjects({ page: 1, page_size: 100 }), []);
  const [projectId, setProjectId] = useState("");
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const [bulkAdd, setBulkAdd] = useState(false);
  const [selected, setSelected] = useState<string[]>([]);
  const [target, setTarget] = useState("");
  const [outcome, setOutcome] = useState<(work.BulkResult & { action: BulkAction }) | null>(null);

  const all = projects.state.status === "loaded" ? projects.state.data.items : [];
  // Nothing is chosen for the person: consent forms, links and removals belong to one project,
  // so the project is always picked by hand first.
  const list = useResource(
    () =>
      projectId
        ? work.listParticipants(projectId, { search, page, page_size: 25 })
        : Promise.resolve(null),
    [projectId, search, page],
  );
  const { busy, error, message, run, setMessage } = useAction(list.reload);
  const confirm = useConfirm(setMessage);
  const rows = list.state.status === "loaded" && list.state.data ? list.state.data.items : [];
  // The chosen project's languages fill the participant form's language list.
  const detail = useResource(
    () => (projectId ? getProject(projectId) : Promise.resolve(null)),
    [projectId],
  );
  const languages =
    detail.state.status === "loaded" && detail.state.data ? detail.state.data.languages : [];
  const windows = useParticipantWindows({
    projectId,
    languages,
    onSaved: (text) => {
      setMessage(text);
      list.reload();
    },
  });
  const live = rows.filter((p) => !p.deleted);

  /** One action for every selected participant; the ones it could not do are listed, and so
   * are the ones assigned, with what happened to their consent form (D-129). */
  const bulkAction = async (
    action: BulkAction,
    extra: { target_project_id?: string; reason?: string } = {},
  ) => {
    setOutcome(null);
    const r = await work.bulkParticipants(projectId, {
      action,
      participant_ids: selected,
      ...extra,
    });
    setOutcome({ ...r, action });
    setSelected([]);
    list.reload();
    return `${r.done} done, ${r.failed} not done.`;
  };
  const assignSelected = () =>
    void run(() => bulkAction("assign", { target_project_id: target }), "bulk-assign");
  // D-139: everyone ticked who has not agreed gets this project's consent form again.
  const resendSelected = () => void run(() => bulkAction("send_consent"), "bulk-consent");
  const removeSelected = () =>
    confirm.ask({
      title: `Remove ${selected.length} participant(s)?`,
      message: "Their personal data is deleted. Their codes stay in the records.",
      askReason: "Why are they removed?",
      confirmLabel: "Remove",
      danger: true,
      action: ({ comment }) => bulkAction("remove", { reason: comment }),
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
          <Button variant="secondary" disabled={!projectId} onClick={() => setBulkAdd(!bulkAdd)}>
            <Icon name="upload" size={15} />
            Add many
          </Button>
          <Button disabled={!projectId} onClick={() => windows.open({ kind: "add" })}>
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
              setProjectId(e.target.value);
              setPage(1);
              setSelected([]);
              setOutcome(null);
            }}
            options={[
              { value: "", label: "Choose a project" },
              ...all.map((p) => ({ value: p.id, label: `${p.code} · ${p.name}` })),
            ]}
          />
          <TextField
            label="Search by name or code"
            type="search"
            value={search}
            disabled={!projectId}
            onChange={(e) => {
              setSearch(e.target.value);
              setPage(1);
            }}
          />
        </div>
      )}
      {all.length > 0 && !projectId ? (
        <EmptyState
          title="Choose a project"
          message="Participants, consent forms and links belong to a project. Choose one above to see its participants and work with them."
        />
      ) : null}
      {bulkAdd && projectId ? <BulkAdd projectId={projectId} onDone={list.reload} /> : null}
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
      {outcome && outcome.action !== "remove" && outcome.done > 0 ? (
        <ul
          className="notice notice--info list"
          aria-label={outcome.action === "assign" ? "Added to the other project" : "Consent forms"}
        >
          {outcome.results
            .filter((r) => r.ok)
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
          <Select
            label="Also add them to another project"
            value={target}
            onChange={(e) => setTarget(e.target.value)}
            options={[
              { value: "", label: "Choose the other project" },
              ...all
                .filter((p) => p.id !== projectId)
                .map((p) => ({ value: p.id, label: `${p.code} · ${p.name}` })),
            ]}
          />
          <Button
            variant="secondary"
            busy={busy === "bulk-assign"}
            disabled={!target || busy !== null}
            onClick={assignSelected}
          >
            Add to that project
          </Button>
          <Button
            variant="secondary"
            busy={busy === "bulk-consent"}
            disabled={busy !== null}
            onClick={resendSelected}
          >
            Email consent form again
          </Button>
          <Button variant="secondary" disabled={busy !== null} onClick={removeSelected}>
            <Icon name="trash" size={15} />
            Remove
          </Button>
          <Button variant="secondary" disabled={busy !== null} onClick={() => setSelected([])}>
            Clear selection
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
          <DataTable>
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
                const answer = consentAnswer(p.consent_status);
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
                      {languageLabel(p.language_code)}
                      {p.dialect ? <div className="muted">{p.dialect}</div> : null}
                    </td>
                    <td>
                      <StatusBadge tone={answer.tone} label={answer.label} />
                    </td>
                    <td className="actions">
                      {p.deleted ? (
                        <span className="muted">Removed</span>
                      ) : (
                        <>
                          {p.has_email && p.consent_status !== "GIVEN" ? (
                            <Button
                              variant="secondary"
                              busy={busy === `email-${p.id}`}
                              disabled={busy !== null}
                              onClick={() =>
                                void run(() => work.emailConsentForm(projectId, p), `email-${p.id}`)
                              }
                            >
                              Email consent form again
                            </Button>
                          ) : null}
                          <Button
                            variant="secondary"
                            onClick={() => windows.open({ kind: "details", participant: p })}
                          >
                            View
                          </Button>
                          <Button
                            variant="secondary"
                            onClick={() => windows.open({ kind: "history", participant: p })}
                          >
                            Consent history
                          </Button>
                          <Button
                            variant="secondary"
                            onClick={() => windows.open({ kind: "edit", participant: p })}
                          >
                            Edit
                          </Button>
                        </>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </DataTable>
          <Pagination page={page} pageSize={25} total={list.state.data.total} onPage={setPage} />
        </>
      ) : null}
      {windows.dialog}
      {confirm.dialog}
    </section>
  );
}
