// Create a recording task (TASK-001); the project's allowed modes drive the choices (PROJ-011). A
// project records one type (D-153): its tasks take it, and only a project made before that allows
// both asks for it. A project has hundreds of speakers: the lists hold the first ones by code, and
// "Find participant" finds anyone else by code or name (FEW-04); the people chosen stay chosen
// while the search changes.
import { useState, type FormEvent } from "react";
import { Link, useNavigate, useSearchParams } from "react-router";

import { getProject, listAllProjects, listMembers } from "../../api/projects";
import {
  createTask,
  importTasks,
  listParticipants,
  type Participant,
  type TaskImportResult,
} from "../../api/work";
import { BackLink } from "../../components/BackLink";
import { Button } from "../../components/form/Button";
import { Icon } from "../../components/Icon";
import { Select } from "../../components/form/Select";
import { TextField } from "../../components/form/TextField";
import { ErrorNotice } from "../../components/Notice";
import { ErrorState, LoadingState } from "../../components/StateViews";
import { useAction } from "../../hooks/useAction";
import { useDebounced } from "../../hooks/useDebounced";
import { useResource } from "../../hooks/useResource";
import { DataTable } from "../../components/DataTable";
import { consentCounts, MODE_LABELS, PRIORITY_LABELS } from "../../lib/labels";
import { onlyMode } from "../projects/recordingType";
import "./tasks.css";

/** People listed at a time; a search finds the others (FEW-04). */
const PEOPLE_PAGE = 25;

/** "1 task" or "3 tasks". */
const tasksWord = (n: number) => `${n} task${n === 1 ? "" : "s"}`;

/** The list with the person chosen in it, first when the search no longer finds them. */
const withChosen = (list: Participant[], chosen: Participant | null) =>
  chosen && !list.some((p) => p.id === chosen.id) ? [chosen, ...list] : list;

const SAMPLE =
  "participant_a,participant_b,mode,priority,due_date,moderator\n" +
  "P000001,P000002,,normal,2026-12-31,moderator@example.org\n" +
  "P000003,P000004,,,,\n";

/** Save the sample as a CSV file the admin fills in (D-085). */
function downloadSample() {
  const url = URL.createObjectURL(new Blob([SAMPLE], { type: "text/csv" }));
  const link = document.createElement("a");
  link.href = url;
  link.download = "tasks_template.csv";
  link.click();
  URL.revokeObjectURL(url);
}

/** Many tasks at once from a CSV of participant codes (D-083): check the rows, then add. */
function BulkTasks({ projectId }: { projectId: string }) {
  const [csv, setCsv] = useState("");
  const [result, setResult] = useState<TaskImportResult | null>(null);
  const { busy: working, error, run } = useAction();
  const busy = working !== null;
  const send = (confirm: boolean) =>
    void run(async () => setResult(await importTasks(projectId, csv, confirm)));

  return (
    <section className="card stack stack--tight" aria-labelledby="bulk-tasks-title">
      <h2 id="bulk-tasks-title">Add many tasks</h2>
      <p className="muted">
        Paste rows or choose a CSV file, one task per line. First line:{" "}
        <code className="bulk-tasks__head">
          participant_a,participant_b,mode,priority,due_date,moderator
        </code>
        . Write participants by their code (P000001); both must have agreed to the consent form,
        have the speaker details the project needs and be within its speaker ages, and the
        project&apos;s limits on conversations per speaker and pairs apply, counting the rows above.
        Mode, priority, due date (YYYY-MM-DD) and moderator (their email) may be empty; an empty
        mode is the project&apos;s recording type, and with a moderator the task is assigned at
        once. Check the rows first; only rows without a problem are added.
      </p>
      <div className="field">
        <label htmlFor="bulk-tasks-csv" className="field__label">
          Tasks (CSV)
        </label>
        <textarea
          id="bulk-tasks-csv"
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
        <Button variant="secondary" icon="fileCsv" onClick={downloadSample}>
          Download sample CSV
        </Button>
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
          busy={busy}
          disabled={!csv.trim()}
          onClick={() => send(false)}
        >
          Check rows
        </Button>
        <Button
          icon="plus"
          busy={busy}
          disabled={!result || result.ready === 0 || result.created > 0}
          onClick={() => send(true)}
        >
          {result?.ready ? `Add ${tasksWord(result.ready)}` : "Add tasks"}
        </Button>
      </div>
      <ErrorNotice error={error} />
      {result ? (
        <>
          <p role="status">
            {result.created > 0
              ? `${tasksWord(result.created)} added.`
              : `${result.ready} of ${result.rows.length} rows are ready.`}
          </p>
          <DataTable>
            <thead>
              <tr>
                <th scope="col">Line</th>
                <th scope="col">Participants</th>
                <th scope="col">Result</th>
              </tr>
            </thead>
            <tbody>
              {result.rows.map((r) => (
                <tr key={r.line} className={r.ok ? "" : "row--invalid"}>
                  <td>{r.line}</td>
                  <td>{r.pair}</td>
                  <td>
                    {r.task_code ? <Link to="/tasks">{r.task_code}</Link> : null}
                    {r.task_code ? " " : ""}
                    {r.message}
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

export function TaskCreatePage() {
  const navigate = useNavigate();
  // Opened from a project's Tasks tab: that project is already chosen.
  const [params] = useSearchParams();
  const [projectId, setProjectId] = useState(params.get("project") ?? "");
  const [mode, setMode] = useState("");
  // The people chosen, kept whole: a new search does not drop them from their lists.
  const [a, setA] = useState<Participant | null>(null);
  const [b, setB] = useState<Participant | null>(null);
  const [find, setFind] = useState("");
  // Asked once typing pauses; an empty box (or another project) lists the first people at once.
  const settled = useDebounced(find.trim());
  const search = find.trim() ? settled : "";
  const [priority, setPriority] = useState("NORMAL");
  const [due, setDue] = useState("");
  const [moderator, setModerator] = useState("");
  const { busy, error, run } = useAction();
  // Every active project, past the first 100 too (PERF-09).
  const projects = useResource(() => listAllProjects({ status: "ACTIVE" }), []);
  const project = useResource(
    () => (projectId ? getProject(projectId) : Promise.resolve(null)),
    [projectId],
  );
  const members = useResource(
    () => (projectId ? listMembers(projectId) : Promise.resolve([])),
    [projectId],
  );
  const moderators =
    members.state.status === "loaded"
      ? members.state.data
          .filter((m) => m.roles.includes("MODERATOR") && m.status === "ACTIVE")
          .map((m) => ({
            value: m.user_id,
            label: m.email ? `${m.display_name} (${m.email})` : m.display_name,
          }))
      : [];
  // The first people by code, or those whose code or name matches the search.
  const people = useResource(
    () =>
      projectId
        ? listParticipants(projectId, { search: search || undefined, page_size: PEOPLE_PAGE })
        : Promise.resolve(null),
    [projectId, search],
  );

  const detail = project.state.status === "loaded" ? project.state.data : null;
  // The project's one type (D-153); a project made before it that allows both still asks.
  const only = detail ? onlyMode(detail) : null;
  const chosenMode = only ?? mode;
  const modes = detail
    ? [
        ...(detail.allows_telephony ? [{ value: "TELEPHONY", label: MODE_LABELS.TELEPHONY }] : []),
        ...(detail.allows_face_to_face
          ? [{ value: "FACE_TO_FACE", label: MODE_LABELS.FACE_TO_FACE }]
          : []),
      ]
    : [];
  const listed = people.state.status === "loaded" ? people.state.data : null;
  const rows = listed?.items ?? [];
  // The list holds what the search found (the whole project when nothing is typed).
  const searching = search !== "";
  // A task is only for people who agreed to the project's consent form (D-129), or whose signed
  // form was uploaded where the project takes uploads (D-144).
  const agreed = rows.filter((p) => consentCounts(p.consent_status));
  // The project's pairing rules (D-143): who cannot be chosen is shown greyed out, with why. A is
  // chosen first; B's list also leaves out who already had a conversation with that A. The server
  // checks again when the task is made.
  const limit = detail?.max_conversations_per_speaker ?? null;
  // The project's speaker ages (D-145), for people whose age this user sees.
  const ages = detail ? { min: detail.speaker_min_age, max: detail.speaker_max_age } : null;
  // A phone call needs both numbers (the server refuses it otherwise); face to face, nobody asks.
  const phoneCalls = chosenMode === "TELEPHONY";
  const blocked = (p: Participant, chosenA = "") => {
    const used = p.pairing?.conversations ?? 0;
    // The server judges the details against the project's list (D-145).
    if (p.speaker_details_complete === false) return "details missing";
    if (phoneCalls && !p.has_phone) return "no phone number";
    if (ages && p.age != null && (p.age < ages.min || p.age > ages.max))
      return `outside the ages ${ages.min} to ${ages.max}`;
    if (limit !== null && used >= limit)
      return `${used} ${used === 1 ? "conversation" : "conversations"} already`;
    if (detail?.unique_pairs && chosenA && p.pairing?.paired_with.includes(chosenA))
      return "already paired with the chosen A";
    return "";
  };
  const option = (p: Participant, chosenA = "") => {
    const why = blocked(p, chosenA);
    return {
      value: p.id,
      label: `${p.participant_code}${p.display_label ? ` ${p.display_label}` : ""}${why ? ` – ${why}` : ""}`,
      disabled: Boolean(why),
    };
  };
  const optionsA = withChosen(agreed, a).map((p) => option(p));
  const optionsB = withChosen(
    agreed.filter((p) => p.id !== a?.id),
    b,
  ).map((p) => option(p, a?.id));
  const someBlocked = [...optionsA, ...optionsB].some((o) => o.disabled);
  const known = (id: string) =>
    [...agreed, ...(a ? [a] : []), ...(b ? [b] : [])].find((p) => p.id === id) ?? null;
  const chooseA = (id: string) => {
    setA(known(id));
    // B stays only while it may still be paired with the new A.
    if (b && (id === b.id || blocked(b, id))) setB(null);
  };
  // A task needs two people: say so instead of showing two empty lists (the whole project only).
  const tooFew = listed && !searching && listed.total < 2 ? listed.total : null;
  // Someone listed has not agreed: they are left out of the lists, and the notice says why.
  const leftOut = rows.some((p) => !consentCounts(p.consent_status));
  // Every person of the project is listed: how many agreed is known.
  const complete = listed !== null && !searching && listed.total <= rows.length;
  // What the lists hold, under the search box (FEW-04).
  const found = !listed
    ? ""
    : searching && rows.length === 0
      ? `Nobody in this project matches “${search}”.`
      : listed.total <= rows.length
        ? ""
        : searching
          ? `Showing ${rows.length} of ${listed.total} matches: type more of the code or name.`
          : `Showing ${rows.length} of ${listed.total}: type a code or name to find others.`;

  function submit(event: FormEvent) {
    event.preventDefault();
    void run(async () => {
      const task = await createTask({
        project_id: projectId,
        recording_mode: chosenMode,
        participant_a_id: a?.id ?? "",
        participant_b_id: b?.id ?? "",
        priority,
        due_at: due ? new Date(due).toISOString() : null,
        ...(moderator ? { moderator_id: moderator } : {}),
      });
      void navigate(`/tasks/${task.id}`);
    });
  }

  if (projects.state.status === "loading") return <LoadingState label="Loading projects" />;
  if (projects.state.status === "failed") {
    return (
      <section aria-labelledby="new-task-title" className="stack">
        <h1 id="new-task-title">New task</h1>
        <ErrorState error={projects.state.error} onRetry={projects.reload} />
      </section>
    );
  }
  // The chosen project's details and people: a failure is reported, never an empty list.
  const projectError =
    project.state.status === "failed"
      ? project.state.error
      : people.state.status === "failed"
        ? people.state.error
        : null;
  const projectOptions =
    projects.state.status === "loaded"
      ? projects.state.data.items.map((p) => ({ value: p.id, label: `${p.code} ${p.name}` }))
      : [];
  return (
    <section aria-labelledby="new-task-title" className="stack">
      <BackLink to="/tasks">All tasks</BackLink>
      <h1 id="new-task-title">New task</h1>
      <form className="card" onSubmit={submit} noValidate>
        <Select
          label="Project (active projects)"
          value={projectId}
          onChange={(e) => {
            setProjectId(e.target.value);
            setMode("");
            setFind("");
            setA(null);
            setB(null);
            setModerator("");
          }}
          options={[{ value: "", label: "Choose a project" }, ...projectOptions]}
        />
        {projectId && tooFew !== null ? (
          <p className="notice notice--info" role="status">
            This project has {tooFew === 0 ? "no participants" : "only 1 participant"}. A task needs
            two.{" "}
            <Link to={`/projects/${projectId}/participants`}>Add participants to the project</Link>{" "}
            first, then come back here.
          </p>
        ) : projectId && leftOut ? (
          <p className="notice notice--info" role="status">
            {detail?.consent_mode === "UPLOAD"
              ? "Only people whose signed consent form is uploaded, or who agreed online, can be chosen."
              : "Only people who agreed to the consent form can be chosen."}
            {complete && agreed.length < 2
              ? ` ${agreed.length === 0 ? "Nobody here has" : "Only 1 person here has"} agreed yet, and a task needs two.`
              : ""}
          </p>
        ) : null}
        {projectId ? (
          <>
            {only ? (
              <p className="field">
                <span className="field__label">Recording type</span>
                <span>
                  {MODE_LABELS[only]} <span className="muted">(the project&apos;s type)</span>
                </span>
              </p>
            ) : detail ? (
              <Select
                label="Recording type"
                value={mode}
                onChange={(e) => setMode(e.target.value)}
                options={[{ value: "", label: "Choose a recording type" }, ...modes]}
              />
            ) : null}
            <div className="task-form__find">
              <TextField
                label="Find participant (code or name)"
                type="search"
                autoComplete="off"
                value={find}
                onChange={(e) => setFind(e.target.value)}
                // Enter finds; it never sends the task half-filled.
                onKeyDown={(e) => {
                  if (e.key === "Enter") e.preventDefault();
                }}
              />
              <p className="field__hint task-form__found" role="status">
                {found}
              </p>
            </div>
            <div className="form-grid task-form__pair">
              <Select
                label="Participant A"
                value={a?.id ?? ""}
                onChange={(e) => chooseA(e.target.value)}
                options={[{ value: "", label: "Choose participant A" }, ...optionsA]}
              />
              <Select
                label="Participant B"
                value={b?.id ?? ""}
                onChange={(e) => setB(known(e.target.value))}
                options={[{ value: "", label: "Choose participant B" }, ...optionsB]}
              />
            </div>
            {someBlocked ? (
              <p className="field__hint task-form__rules">
                Greyed-out people cannot be chosen now; the reason is after their name. A task needs
                the speaker details the project asks for
                {phoneCalls ? ", a phone number for each speaker" : ""}
                {ages ? `, speakers aged ${ages.min} to ${ages.max}` : ""}
                {limit === null ? "" : `, at most ${limit} conversations per speaker`}
                {detail?.unique_pairs ? ", and each pair of speakers only once" : ""}.
              </p>
            ) : null}
            <Select
              label="Moderator"
              value={moderator}
              onChange={(e) => setModerator(e.target.value)}
              options={[{ value: "", label: "Assign later" }, ...moderators]}
            />
            <div className="form-grid task-form__pair">
              <Select
                label="Priority"
                value={priority}
                onChange={(e) => setPriority(e.target.value)}
                options={Object.entries(PRIORITY_LABELS).map(([value, label]) => ({
                  value,
                  label,
                }))}
              />
              <TextField
                label="Due date"
                type="date"
                value={due}
                onChange={(e) => setDue(e.target.value)}
              />
            </div>
            {projectError ? (
              <>
                <ErrorNotice error={projectError} />
                <Button
                  variant="secondary"
                  icon="refresh"
                  onClick={() => {
                    project.reload();
                    people.reload();
                  }}
                >
                  Try again
                </Button>
              </>
            ) : null}
          </>
        ) : null}
        <ErrorNotice error={error} />
        <Button
          type="submit"
          icon="plus"
          busy={busy !== null}
          disabled={!projectId || !chosenMode || !a || !b}
        >
          Create task
        </Button>
      </form>
      {projectId ? <BulkTasks key={projectId} projectId={projectId} /> : null}
    </section>
  );
}
