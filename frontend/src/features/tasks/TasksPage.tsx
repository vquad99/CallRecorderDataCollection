// Tasks the user can see: all in their projects for task managers, only their own otherwise (TASK-005, TASK-011).
import { useState } from "react";
import { Link } from "react-router";

import { listProjects } from "../../api/projects";
import { listTasks, TASK_STATUS_LABELS } from "../../api/work";
import { useAuth } from "../../auth/AuthContext";
import { Select } from "../../components/form/Select";
import { Pagination } from "../../components/Pagination";
import { EmptyState, ErrorState, LoadingState } from "../../components/StateViews";
import { useResource } from "../../hooks/useResource";

export function TasksPage() {
  const { can } = useAuth();
  const [projectId, setProjectId] = useState("");
  const [status, setStatus] = useState("");
  const [mode, setMode] = useState("");
  const [page, setPage] = useState(1);
  const projects = useResource(() => listProjects({ page_size: 100 }), []);
  const tasks = useResource(
    () => listTasks({ project_id: projectId, status, mode, page, page_size: 25 }),
    [projectId, status, mode, page],
  );
  const codes =
    projects.state.status === "loaded"
      ? Object.fromEntries(projects.state.data.items.map((p) => [p.id, p.code]))
      : {};
  const reset = () => setPage(1);

  return (
    <section aria-labelledby="tasks-title" className="stack">
      <div className="page-header">
        <h1 id="tasks-title">Tasks</h1>
        {can("tasks.assign") ? (
          <Link className="button button--primary" to="/tasks/new">
            New task
          </Link>
        ) : null}
      </div>
      <div className="filters">
        <Select
          label="Project"
          value={projectId}
          onChange={(e) => {
            setProjectId(e.target.value);
            reset();
          }}
          options={[
            { value: "", label: "All projects" },
            ...(projects.state.status === "loaded"
              ? projects.state.data.items.map((p) => ({ value: p.id, label: p.code }))
              : []),
          ]}
        />
        <Select
          label="Status"
          value={status}
          onChange={(e) => {
            setStatus(e.target.value);
            reset();
          }}
          options={[
            { value: "", label: "All" },
            ...Object.entries(TASK_STATUS_LABELS).map(([value, label]) => ({ value, label })),
          ]}
        />
        <Select
          label="Mode"
          value={mode}
          onChange={(e) => {
            setMode(e.target.value);
            reset();
          }}
          options={[
            { value: "", label: "All" },
            { value: "TELEPHONY", label: "Telephony" },
            { value: "FACE_TO_FACE", label: "Face-to-face" },
          ]}
        />
      </div>
      {tasks.state.status === "loading" ? <LoadingState label="Loading tasks" /> : null}
      {tasks.state.status === "failed" ? (
        <ErrorState message={tasks.state.error.message} onRetry={tasks.reload} />
      ) : null}
      {tasks.state.status === "loaded" && tasks.state.data.items.length === 0 ? (
        <EmptyState
          title="No tasks"
          message="Nothing matches, or nothing is assigned to you yet."
        />
      ) : null}
      {tasks.state.status === "loaded" && tasks.state.data.items.length > 0 ? (
        <>
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th scope="col">Task</th>
                  <th scope="col">Project</th>
                  <th scope="col">Mode</th>
                  <th scope="col">Status</th>
                  <th scope="col">Priority</th>
                  <th scope="col">Due</th>
                </tr>
              </thead>
              <tbody>
                {tasks.state.data.items.map((t) => (
                  <tr key={t.id}>
                    <td>
                      <Link to={`/tasks/${t.id}`}>{t.task_code}</Link>
                    </td>
                    <td>{codes[t.project_id] ?? "-"}</td>
                    <td>{t.recording_mode === "TELEPHONY" ? "Telephony" : "Face-to-face"}</td>
                    <td>{TASK_STATUS_LABELS[t.status]}</td>
                    <td>{t.priority.toLowerCase()}</td>
                    <td>{t.due_at ? new Date(t.due_at).toLocaleDateString() : "-"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <Pagination page={page} pageSize={25} total={tasks.state.data.total} onPage={setPage} />
        </>
      ) : null}
    </section>
  );
}
