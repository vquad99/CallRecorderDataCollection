// Tasks the user can see: all in their projects for task managers, only their own otherwise (TASK-005, TASK-011).
// The same list sits on a project's Tasks tab, fixed to that project (D-117).
import { useEffect, useState } from "react";
import { Link, useLocation } from "react-router";

import type { ApiError } from "../../api/client";
import { listProjects } from "../../api/projects";
import { listTasks, TASK_STATUS_LABELS, transitionTask, type TaskSummary } from "../../api/work";
import { useAuth } from "../../auth/AuthContext";
import { Button } from "../../components/form/Button";
import { Select } from "../../components/form/Select";
import { ErrorNotice, SuccessNotice } from "../../components/Notice";
import { TextField } from "../../components/form/TextField";
import { Pagination } from "../../components/Pagination";
import { EmptyState, ErrorState, LoadingState } from "../../components/StateViews";
import { toApiError, useResource } from "../../hooks/useResource";
import { Icon, IconTile } from "../../components/Icon";
import { StatusBadge } from "../../components/StatusBadge";

export function TasksPage({ fixedProjectId }: { fixedProjectId?: string } = {}) {
  const { can } = useAuth();
  const inProject = fixedProjectId !== undefined;
  const [chosenProject, setProjectId] = useState("");
  const projectId = fixedProjectId ?? chosenProject;
  const [status, setStatus] = useState("");
  const [mode, setMode] = useState("");
  const [page, setPage] = useState(1);
  const [typed, setTyped] = useState("");
  const [search, setSearch] = useState("");
  // Ask the server once typing pauses, not on every key (O7).
  useEffect(() => {
    const id = window.setTimeout(() => {
      setSearch(typed.trim());
      setPage(1);
    }, 300);
    return () => window.clearTimeout(id);
  }, [typed]);
  const projects = useResource(
    () =>
      inProject
        ? Promise.resolve({ items: [], total: 0, page: 1, page_size: 100 })
        : listProjects({ page_size: 100 }),
    [inProject],
  );
  const tasks = useResource(
    () =>
      listTasks({
        project_id: projectId,
        status,
        mode,
        search: search || undefined,
        page,
        page_size: 25,
      }),
    [projectId, status, mode, search, page],
  );
  const codes =
    projects.state.status === "loaded"
      ? Object.fromEntries(projects.state.data.items.map((p) => [p.id, p.code]))
      : {};
  const reset = () => setPage(1);
  // Many tasks at once (D-093): approve the ones waiting for admin review, each through the
  // single-task checks. Exports are per project, on the project's Export tab (D-094).
  const canSelect = can("tasks.assign");
  // The selection belongs to the list it was made in: another filter or page starts empty.
  const listKey = JSON.stringify([projectId, status, mode, search, page]);
  const [selection, setSelection] = useState<{ key: string; ids: string[] }>({ key: "", ids: [] });
  const selected = selection.key === listKey ? selection.ids : [];
  const setSelected = (ids: string[]) => setSelection({ key: listKey, ids });
  const [busy, setBusy] = useState<"approve" | null>(null);
  // A message handed over by the page before (for example "Task T000012 deleted.").
  const handed = (useLocation().state as { message?: string } | null)?.message ?? null;
  const [message, setMessage] = useState<string | null>(handed);
  const [error, setError] = useState<ApiError | null>(null);
  const rows: TaskSummary[] = tasks.state.status === "loaded" ? tasks.state.data.items : [];
  const chosen = rows.filter((t) => selected.includes(t.id));
  const waiting = chosen.filter((t) => t.status === "ADMIN_REVIEW");
  const toggle = (id: string) =>
    setSelected(selected.includes(id) ? selected.filter((x) => x !== id) : [...selected, id]);

  async function approveSelected() {
    setBusy("approve");
    setMessage(null);
    setError(null);
    let done = 0;
    const failed: string[] = [];
    for (const t of waiting) {
      try {
        await transitionTask(t.id, "APPROVED", "", "");
        done += 1;
      } catch (err) {
        failed.push(`${t.task_code}: ${toApiError(err).message}`);
      }
    }
    const skipped = chosen.length - waiting.length;
    setMessage(
      `${done} approved.` +
        (skipped ? ` ${skipped} skipped: not waiting for admin review.` : "") +
        (failed.length ? ` Not approved: ${failed.join("; ")}.` : ""),
    );
    setSelected([]);
    setBusy(null);
    tasks.reload();
  }

  const newTask = can("tasks.assign") ? (
    <Link
      className="button button--primary"
      to={inProject ? `/tasks/new?project=${projectId}` : "/tasks/new"}
    >
      <Icon name="plus" size={18} weight="bold" />
      New task
    </Link>
  ) : null;

  return (
    <section aria-labelledby={inProject ? undefined : "tasks-title"} className="stack">
      {inProject ? (
        <div className="actions">
          {newTask}
          {tasks.state.status === "loaded" ? (
            <span className="muted">
              {tasks.state.data.total === 1
                ? "1 task in this project"
                : `${tasks.state.data.total} tasks in this project`}
            </span>
          ) : null}
        </div>
      ) : (
        <div className="page-header">
          <h1 id="tasks-title">
            <IconTile name="tasks" tone="teal" />
            Tasks
          </h1>
          {newTask}
        </div>
      )}
      <div className="filters">
        <TextField
          label="Task or participant code"
          type="search"
          value={typed}
          onChange={(e) => setTyped(e.target.value)}
        />
        {inProject ? null : (
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
        )}
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
      {canSelect && selected.length > 0 ? (
        <div className="card bulkbar" role="group" aria-label="Actions for selected tasks">
          <strong>{selected.length} selected</strong>
          <Button
            busy={busy === "approve"}
            disabled={waiting.length === 0 || busy !== null}
            onClick={() => void approveSelected()}
          >
            Approve selected ({waiting.length})
          </Button>
          <Button variant="secondary" disabled={busy !== null} onClick={() => setSelected([])}>
            Clear
          </Button>
        </div>
      ) : null}
      <SuccessNotice message={message} />
      <ErrorNotice error={error} />
      {tasks.state.status === "loading" ? <LoadingState label="Loading tasks" /> : null}
      {tasks.state.status === "failed" ? (
        <ErrorState error={tasks.state.error} onRetry={tasks.reload} />
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
                  {canSelect ? (
                    <th scope="col">
                      <input
                        type="checkbox"
                        aria-label="Select every task on this page"
                        checked={rows.length > 0 && chosen.length === rows.length}
                        onChange={(e) => setSelected(e.target.checked ? rows.map((t) => t.id) : [])}
                      />
                    </th>
                  ) : null}
                  <th scope="col">Task</th>
                  {inProject ? null : <th scope="col">Project</th>}
                  <th scope="col">Mode</th>
                  <th scope="col">Status</th>
                  <th scope="col">Priority</th>
                  <th scope="col">Due</th>
                </tr>
              </thead>
              <tbody>
                {tasks.state.data.items.map((t) => (
                  <tr key={t.id}>
                    {canSelect ? (
                      <td>
                        <input
                          type="checkbox"
                          aria-label={`Select ${t.task_code}`}
                          checked={selected.includes(t.id)}
                          onChange={() => toggle(t.id)}
                        />
                      </td>
                    ) : null}
                    <td>
                      <Link className="code" to={`/tasks/${t.id}`}>
                        {t.task_code}
                      </Link>
                    </td>
                    {inProject ? null : <td>{codes[t.project_id] ?? "-"}</td>}
                    <td>
                      <span className="cell-icon">
                        <Icon name={t.recording_mode === "TELEPHONY" ? "phone" : "mic"} size={15} />
                        {t.recording_mode === "TELEPHONY" ? "Telephony" : "Face-to-face"}
                      </span>
                    </td>
                    <td>
                      <StatusBadge status={t.status} label={TASK_STATUS_LABELS[t.status]} />
                    </td>
                    <td>
                      <span className={`priority priority--${t.priority.toLowerCase()}`}>
                        {t.priority.toLowerCase()}
                      </span>
                    </td>
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
