// Create a recording task (TASK-001); the project's allowed modes drive the choices (PROJ-011).
import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router";

import type { ApiError } from "../../api/client";
import { getProject, listProjects } from "../../api/projects";
import { createTask, importTasks, listParticipants, type TaskImportResult } from "../../api/work";
import { Button } from "../../components/form/Button";
import { Icon } from "../../components/Icon";
import { Select } from "../../components/form/Select";
import { TextField } from "../../components/form/TextField";
import { ErrorNotice } from "../../components/Notice";
import { ErrorState, LoadingState } from "../../components/StateViews";
import { toApiError, useResource } from "../../hooks/useResource";

const SAMPLE =
  "participant_a,participant_b,mode,priority,due_date,moderator\n" +
  "P000001,P000002,face_to_face,normal,2026-12-31,moderator@example.org\n";

/** Many tasks at once from a CSV of participant codes (D-083): check the rows, then add. */
function BulkTasks({ projectId }: { projectId: string }) {
  const [csv, setCsv] = useState("");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<TaskImportResult | null>(null);
  const [error, setError] = useState<ApiError | null>(null);

  function send(confirm: boolean) {
    setBusy(true);
    setError(null);
    importTasks(projectId, csv, confirm)
      .then(setResult)
      .catch((err: unknown) => setError(toApiError(err)))
      .finally(() => setBusy(false));
  }

  return (
    <section className="card stack stack--tight" aria-labelledby="bulk-tasks-title">
      <h2 id="bulk-tasks-title">Add many tasks</h2>
      <p className="muted">
        Paste rows or choose a CSV file, one task per line. First line:{" "}
        <code>participant_a,participant_b,mode,priority,due_date,moderator</code>. Write
        participants by their code (P000001). Mode, priority, due date (YYYY-MM-DD) and moderator
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
          <div className="table-wrap">
            <table className="table">
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
            </table>
          </div>
        </>
      ) : null}
    </section>
  );
}

export function TaskCreatePage() {
  const navigate = useNavigate();
  const [projectId, setProjectId] = useState("");
  const [mode, setMode] = useState("");
  const [a, setA] = useState("");
  const [b, setB] = useState("");
  const [priority, setPriority] = useState("NORMAL");
  const [due, setDue] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const projects = useResource(() => listProjects({ status: "ACTIVE", page_size: 100 }), []);
  const project = useResource(
    () => (projectId ? getProject(projectId) : Promise.resolve(null)),
    [projectId],
  );
  const people = useResource(
    () => (projectId ? listParticipants(projectId, { page_size: 100 }) : Promise.resolve(null)),
    [projectId],
  );

  const detail = project.state.status === "loaded" ? project.state.data : null;
  const modes = detail
    ? [
        ...(detail.allows_telephony ? [{ value: "TELEPHONY", label: "Telephony" }] : []),
        ...(detail.allows_face_to_face ? [{ value: "FACE_TO_FACE", label: "Face-to-face" }] : []),
      ]
    : [];
  const options =
    people.state.status === "loaded" && people.state.data
      ? people.state.data.items.map((p) => ({
          value: p.id,
          label: `${p.participant_code}${p.display_label ? ` ${p.display_label}` : ""}${p.has_phone ? "" : " (no phone)"}`,
        }))
      : [];
  // A task needs two people: say so instead of showing two empty lists.
  const tooFew =
    people.state.status === "loaded" && people.state.data && people.state.data.total < 2
      ? people.state.data.total
      : null;

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const task = await createTask({
        project_id: projectId,
        recording_mode: mode,
        participant_a_id: a,
        participant_b_id: b,
        priority,
        due_at: due ? new Date(due).toISOString() : null,
      });
      navigate(`/tasks/${task.id}`);
    } catch (err) {
      setError(toApiError(err));
    } finally {
      setBusy(false);
    }
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
      <h1 id="new-task-title">New task</h1>
      <form className="card" onSubmit={(e) => void submit(e)} noValidate>
        <Select
          label="Project (active projects)"
          value={projectId}
          onChange={(e) => {
            setProjectId(e.target.value);
            setMode("");
            setA("");
            setB("");
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
        ) : null}
        {projectId ? (
          <>
            <Select
              label="Recording mode"
              value={mode}
              onChange={(e) => setMode(e.target.value)}
              options={[{ value: "", label: "Choose a mode" }, ...modes]}
            />
            <Select
              label="Participant A"
              value={a}
              onChange={(e) => setA(e.target.value)}
              options={[{ value: "", label: "Choose participant A" }, ...options]}
            />
            <Select
              label="Participant B"
              value={b}
              onChange={(e) => setB(e.target.value)}
              options={[
                { value: "", label: "Choose participant B" },
                ...options.filter((o) => o.value !== a),
              ]}
            />
            <Select
              label="Priority"
              value={priority}
              onChange={(e) => setPriority(e.target.value)}
              options={["LOW", "NORMAL", "HIGH", "URGENT"].map((v) => ({
                value: v,
                label: v.toLowerCase(),
              }))}
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
        <Button type="submit" busy={busy} disabled={!projectId || !mode || !a || !b}>
          Create task
        </Button>
      </form>
      {projectId ? <BulkTasks key={projectId} projectId={projectId} /> : null}
    </section>
  );
}
