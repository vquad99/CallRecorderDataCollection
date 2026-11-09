// Create a recording task (TASK-001); the project's allowed modes drive the choices (PROJ-011).
import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router";

import type { ApiError } from "../../api/client";
import { getProject, listProjects } from "../../api/projects";
import { createTask, listParticipants } from "../../api/work";
import { Button } from "../../components/form/Button";
import { Select } from "../../components/form/Select";
import { TextField } from "../../components/form/TextField";
import { ErrorNotice } from "../../components/Notice";
import { LoadingState } from "../../components/StateViews";
import { toApiError, useResource } from "../../hooks/useResource";

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

  if (projects.state.status === "loading") return <LoadingState />;
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
          </>
        ) : null}
        <ErrorNotice error={error} />
        <Button type="submit" busy={busy} disabled={!projectId || !mode || !a || !b}>
          Create task
        </Button>
      </form>
    </section>
  );
}
