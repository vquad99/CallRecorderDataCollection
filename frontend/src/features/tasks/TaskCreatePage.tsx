// Create a recording task (TASK-001); the project's allowed modes drive the choices (PROJ-011).
import { useState, type FormEvent } from "react";
import { Link, useNavigate, useSearchParams } from "react-router";

import { getProject, listMembers, listProjects } from "../../api/projects";
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
import { useResource } from "../../hooks/useResource";
import { DataTable } from "../../components/DataTable";
import { MODE_LABELS, PRIORITY_LABELS } from "../../lib/labels";

const SAMPLE =
  "participant_a,participant_b,mode,priority,due_date,moderator\n" +
  "P000001,P000002,face_to_face,normal,2026-12-31,moderator@example.org\n" +
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
        <code>participant_a,participant_b,mode,priority,due_date,moderator</code>. Write
        participants by their code (P000001); both must have agreed to the consent form and have
        complete speaker details, and the project&apos;s limits on conversations per speaker and
        pairs apply, counting the rows above. Mode, priority, due date (YYYY-MM-DD) and moderator
        (their email) may be empty; with a moderator the task is assigned at once. Check the rows
        first; only rows without a problem are added.
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
          Add {result?.ready ?? 0} tasks
        </Button>
      </div>
      <ErrorNotice error={error} />
      {result ? (
        <>
          <p role="status">
            {result.created > 0
              ? `${result.created} tasks added.`
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
  const [a, setA] = useState("");
  const [b, setB] = useState("");
  const [priority, setPriority] = useState("NORMAL");
  const [due, setDue] = useState("");
  const [moderator, setModerator] = useState("");
  const { busy, error, run } = useAction();
  const projects = useResource(() => listProjects({ status: "ACTIVE", page_size: 100 }), []);
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
  const people = useResource(
    () => (projectId ? listParticipants(projectId, { page_size: 100 }) : Promise.resolve(null)),
    [projectId],
  );

  const detail = project.state.status === "loaded" ? project.state.data : null;
  const modes = detail
    ? [
        ...(detail.allows_telephony ? [{ value: "TELEPHONY", label: MODE_LABELS.TELEPHONY }] : []),
        ...(detail.allows_face_to_face
          ? [{ value: "FACE_TO_FACE", label: MODE_LABELS.FACE_TO_FACE }]
          : []),
      ]
    : [];
  const listed = people.state.status === "loaded" ? people.state.data : null;
  // A task is only for people who agreed to the project's consent form (D-129).
  const agreed = (listed?.items ?? []).filter((p) => p.consent_status === "GIVEN");
  // The project's pairing rules (D-143): who cannot be chosen is shown greyed out, with why. A is
  // chosen first; B's list also leaves out who already had a conversation with that A. The server
  // checks again when the task is made.
  const limit = detail?.max_conversations_per_speaker ?? null;
  const blocked = (p: Participant, chosenA = "") => {
    const used = p.pairing?.conversations ?? 0;
    if (p.speaker_details_complete === false) return "details missing";
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
      label: `${p.participant_code}${p.display_label ? ` ${p.display_label}` : ""}${p.has_phone ? "" : " (no phone)"}${why ? ` – ${why}` : ""}`,
      disabled: Boolean(why),
    };
  };
  const optionsA = agreed.map((p) => option(p));
  const optionsB = agreed.filter((p) => p.id !== a).map((p) => option(p, a));
  const someBlocked = [...optionsA, ...optionsB].some((o) => o.disabled);
  const chooseA = (next: string) => {
    setA(next);
    // B stays only while it may still be paired with the new A.
    const chosenB = agreed.find((p) => p.id === b);
    if (next === b || (chosenB && blocked(chosenB, next))) setB("");
  };
  // A task needs two people: say so instead of showing two empty lists.
  const tooFew = listed && listed.total < 2 ? listed.total : null;
  const leftOut = listed !== null && listed.total > agreed.length;

  function submit(event: FormEvent) {
    event.preventDefault();
    void run(async () => {
      const task = await createTask({
        project_id: projectId,
        recording_mode: mode,
        participant_a_id: a,
        participant_b_id: b,
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
            setA("");
            setB("");
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
            Only people who agreed to the consent form can be chosen.
            {agreed.length < 2
              ? ` ${agreed.length === 0 ? "Nobody here has" : "Only 1 person here has"} agreed yet, and a task needs two.`
              : ""}
          </p>
        ) : null}
        {projectId ? (
          <>
            <Select
              label="Recording type"
              value={mode}
              onChange={(e) => setMode(e.target.value)}
              options={[{ value: "", label: "Choose a recording type" }, ...modes]}
            />
            <Select
              label="Participant A"
              value={a}
              onChange={(e) => chooseA(e.target.value)}
              options={[{ value: "", label: "Choose participant A" }, ...optionsA]}
            />
            <Select
              label="Participant B"
              value={b}
              onChange={(e) => setB(e.target.value)}
              options={[{ value: "", label: "Choose participant B" }, ...optionsB]}
            />
            {someBlocked ? (
              <p className="field__hint">
                Greyed-out people cannot be chosen now; the reason is after their name. A task needs
                complete speaker details
                {limit === null ? "" : `, at most ${limit} conversations per speaker`}
                {detail?.unique_pairs ? ", and each pair of speakers only once" : ""}.
              </p>
            ) : null}
            <Select
              label="Priority"
              value={priority}
              onChange={(e) => setPriority(e.target.value)}
              options={Object.entries(PRIORITY_LABELS).map(([value, label]) => ({
                value,
                label,
              }))}
            />
            <Select
              label="Moderator"
              value={moderator}
              onChange={(e) => setModerator(e.target.value)}
              options={[{ value: "", label: "Assign later" }, ...moderators]}
            />
            <TextField
              label="Due date"
              type="date"
              value={due}
              onChange={(e) => setDue(e.target.value)}
            />
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
          disabled={!projectId || !mode || !a || !b}
        >
          Create task
        </Button>
      </form>
      {projectId ? <BulkTasks key={projectId} projectId={projectId} /> : null}
    </section>
  );
}
