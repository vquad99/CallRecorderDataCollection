// Participants section (D-073): everyone in a project in one place, with the work done on many at
// once - add from a file, assign to another project, remove - and each participant's own answer
// on the consent form. The form is emailed by itself to everyone who joins a project and an
// answer counts at once (D-129); "Email consent form again" is for an email that was lost. In a
// project that takes signed forms nothing is emailed: staff upload the scan (D-144). A selection
// belongs to the list it was made in: another project, search or page starts with none ticked, so
// an action never reaches people who are not shown (FEW-05).
import { Fragment, useState } from "react";

import { getProject, listAllProjects } from "../../api/projects";
import * as work from "../../api/work";
import { useConfirm } from "../../components/ConfirmDialog";
import { DataTable } from "../../components/DataTable";
import { Button, IconButton } from "../../components/form/Button";
import { Select } from "../../components/form/Select";
import { TextField } from "../../components/form/TextField";
import { Icon } from "../../components/Icon";
import { ErrorNotice, SuccessNotice } from "../../components/Notice";
import { PageHeader } from "../../components/PageHeader";
import { Pagination } from "../../components/Pagination";
import { EmptyState, ErrorState, LoadingState } from "../../components/StateViews";
import { StatusBadge } from "../../components/StatusBadge";
import { useAction } from "../../hooks/useAction";
import { useDebounced } from "../../hooks/useDebounced";
import { useResource } from "../../hooks/useResource";
import { plural } from "../../lib/format";
import { consentAnswer, FORM_MISSING } from "../../lib/labels";
import { speakerRulesOf } from "../../lib/speakers";
import { languageLabel } from "../projects/choices";
import { DocumentBadges } from "./Documents";
import { DetailsMissing } from "./ParticipantDetails";
import { useParticipantWindows } from "./ParticipantEditor";

// The file's columns: who they are, then the speaker details (D-143); `district` is the native
// district.
const COLUMNS =
  "name,phone,email,language,dialect,district,age,gender,current_state,current_district," +
  "current_pincode,native_state,native_pincode,native_language,education,education_medium," +
  "recording_state,recording_district,recording_pincode";
const SAMPLE =
  `${COLUMNS}\n` +
  "Asha Naik,+919876543210,asha@example.org,kok,,Salcete,34,female,Goa,North Goa,403001,Goa," +
  "403601,Konkani,bachelors,english,Goa,North Goa,403001\n";
/** The columns as shown: the line may break after any comma, so it never runs past its section
 * (D-158). */
const COLUMNS_SHOWN = COLUMNS.split(",").map((column, i) => (
  <Fragment key={column}>
    {i > 0 ? "," : null}
    {i > 0 ? <wbr /> : null}
    {column}
  </Fragment>
));

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
        Paste rows or choose a CSV file. First line: <code>{COLUMNS_SHOWN}</code>. Every row needs
        an email; phone and dialect may be empty. The speaker details (<code>district</code> is the
        native district; <code>gender</code> male or female; <code>education</code> primary,
        secondary, higher_secondary, diploma, bachelors, masters, phd or other;{" "}
        <code>education_medium</code> english or non_english; states written in full; PIN codes of 6
        digits) may be left empty, but a task needs them all. Check the rows first; only rows
        without a problem are added.
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
          <Icon name="fileUp" size={16} />
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
          icon="tasks"
          busy={busy === "check"}
          disabled={!csv.trim() || busy !== null}
          onClick={() => send(false)}
        >
          Check rows
        </Button>
        <Button
          icon="plus"
          busy={busy === "add"}
          disabled={!result || result.ready === 0 || result.created > 0 || busy !== null}
          onClick={() => send(true)}
        >
          {result?.ready ? `Add ${plural(result.ready, "participant")}` : "Add participants"}
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
  // Every project the person can see, not only the newest 100 (PERF-09).
  const projects = useResource(() => listAllProjects(), []);
  const [projectId, setProjectId] = useState("");
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const [bulkAdd, setBulkAdd] = useState(false);
  // The selection belongs to the list it was made in: another project, search or page starts
  // empty, so Remove never deletes someone who is not on the screen.
  const listKey = JSON.stringify([projectId, search.trim(), page]);
  const [selection, setSelection] = useState<{ key: string; ids: string[] }>({ key: "", ids: [] });
  const selected = selection.key === listKey ? selection.ids : [];
  const setSelected = (ids: string[]) => setSelection({ key: listKey, ids });
  const [target, setTarget] = useState("");
  const [outcome, setOutcome] = useState<(work.BulkResult & { action: BulkAction }) | null>(null);

  const all = projects.state.status === "loaded" ? projects.state.data.items : [];
  // Nothing is chosen for the person: consent forms, links and removals belong to one project,
  // so the project is always picked by hand first.
  const query = useDebounced(search.trim());
  const list = useResource(
    () =>
      projectId
        ? work.listParticipants(projectId, { search: query, page, page_size: 25 })
        : Promise.resolve(null),
    [projectId, query, page],
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
  // Consent online (emailed) or a signed form uploaded by staff (D-144).
  const mode =
    detail.state.status === "loaded" && detail.state.data
      ? detail.state.data.consent_mode
      : undefined;
  const online = mode !== "UPLOAD";
  const windows = useParticipantWindows({
    projectId,
    languages,
    consentMode: mode,
    // The chosen project's speaker ages and needed details (D-145); none until it has loaded.
    ...(detail.state.status === "loaded" && detail.state.data
      ? { rules: speakerRulesOf(detail.state.data) }
      : {}),
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
      title: `Remove ${plural(selected.length, "participant")}?`,
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
      <PageHeader
        id="participants-title"
        title="Participants"
        lead="The people who record, project by project."
        actions={
          <>
            <Button
              variant="secondary"
              icon="fileUp"
              disabled={!projectId}
              onClick={() => setBulkAdd(!bulkAdd)}
            >
              Add many
            </Button>
            <Button
              icon="userPlus"
              disabled={!projectId}
              onClick={() => windows.open({ kind: "add" })}
            >
              Add participant
            </Button>
          </>
        }
      />
      {all.length === 0 ? (
        <EmptyState title="No projects" message="You are not a member of any project yet." />
      ) : (
        // The filters, a section of their own; the project's box as wide as its names (D-158). The
        // search is worded as on the project's Participants and on Payments (D-159).
        <div className="filters participants-filters" role="group" aria-label="Filters">
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
            label="Search by code or name"
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
            icon="projects"
            busy={busy === "bulk-assign"}
            disabled={!target || busy !== null}
            onClick={assignSelected}
          >
            Add to that project
          </Button>
          {online ? (
            <Button
              variant="secondary"
              icon="mail"
              busy={busy === "bulk-consent"}
              disabled={busy !== null}
              onClick={resendSelected}
            >
              Email consent form again
            </Button>
          ) : null}
          <Button
            variant="secondary"
            icon="trash"
            disabled={busy !== null}
            onClick={removeSelected}
          >
            Remove
          </Button>
          <Button
            variant="secondary"
            icon="close"
            disabled={busy !== null}
            onClick={() => setSelected([])}
          >
            Clear selection
          </Button>
        </div>
      ) : null}
      {list.state.status === "loading" ? <LoadingState label="Loading participants" /> : null}
      {list.state.status === "failed" ? (
        <ErrorState error={list.state.error} onRetry={list.reload} />
      ) : null}
      {list.state.status === "loaded" && list.state.data && rows.length === 0 ? (
        query ? (
          <EmptyState title="No participants match" message="Try another code or name." />
        ) : (
          <EmptyState
            title="No participants"
            message="Add one, or add many from a file, to get started."
          />
        )
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
                const answer = consentAnswer(p.consent_status, mode);
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
                    <td>
                      {p.display_label ?? <span className="muted">Hidden</span>}
                      {p.deleted ? null : (
                        <div className="row-badges">
                          {p.speaker_details_complete === false ? <DetailsMissing /> : null}
                          {/* The consent chip may already say the form is missing (D-144). */}
                          <DocumentBadges
                            p={p}
                            mode={mode}
                            consent={answer.label !== FORM_MISSING.label}
                          />
                        </div>
                      )}
                    </td>
                    <td>
                      {p.phone ?? (p.has_phone ? "Phone on file" : "")}
                      {p.has_email ? (
                        <div className="muted">{p.email ?? "Email on file"}</div>
                      ) : null}
                      {/* Nothing to reach them by: a dash, as for any empty value (D-158). */}
                      {!p.phone && !p.has_phone && !p.has_email ? "-" : null}
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
                          <IconButton
                            icon="eye"
                            label="View"
                            onClick={() => windows.open({ kind: "details", participant: p })}
                          />
                          <IconButton
                            icon="history"
                            label="Consent history"
                            onClick={() => windows.open({ kind: "history", participant: p })}
                          />
                          <IconButton
                            icon="fileText"
                            label="Documents"
                            onClick={() => windows.open({ kind: "documents", participant: p })}
                          />
                          {online && p.has_email && p.consent_status !== "GIVEN" ? (
                            <IconButton
                              icon="mail"
                              label="Email consent form again"
                              busy={busy === `email-${p.id}`}
                              disabled={busy !== null}
                              onClick={() =>
                                void run(() => work.emailConsentForm(projectId, p), `email-${p.id}`)
                              }
                            />
                          ) : null}
                          <IconButton
                            icon="pencil"
                            label="Edit"
                            onClick={() => windows.open({ kind: "edit", participant: p })}
                          />
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
