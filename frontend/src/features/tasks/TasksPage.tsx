// Tasks the user can see: all in their projects for task managers, only their own otherwise
// (TASK-005, TASK-011). The same list sits on a project's Tasks tab, fixed to that project (D-117).
// The filters live in the address (?status=AUDIO_QC&project=...), so a link from the dashboard
// opens the list already filtered and the browser's Back button keeps them.
import { useEffect, useState } from "react";
import { Link, useLocation, useSearchParams } from "react-router";

import { listProjects } from "../../api/projects";
import { listTasks, transitionTask, type TaskSummary } from "../../api/work";
import { useAuth } from "../../auth/AuthContext";
import { DataTable } from "../../components/DataTable";
import { Button } from "../../components/form/Button";
import { Select } from "../../components/form/Select";
import { TextField } from "../../components/form/TextField";
import { Icon } from "../../components/Icon";
import { ErrorNotice, SuccessNotice } from "../../components/Notice";
import { Pagination } from "../../components/Pagination";
import { EmptyState, ErrorState, LoadingState } from "../../components/StateViews";
import { StatusBadge } from "../../components/StatusBadge";
import { useAction } from "../../hooks/useAction";
import { useDebounced } from "../../hooks/useDebounced";
import { toApiError, useResource } from "../../hooks/useResource";
import { day } from "../../lib/format";
import { labelFor, MODE_LABELS, PRIORITY_LABELS, TASK_STATUS_LABELS } from "../../lib/labels";
import "./tasks.css";

const PAGE_SIZE = 25;

export function TasksPage({ fixedProjectId }: { fixedProjectId?: string } = {}) {
  const { can } = useAuth();
  const inProject = fixedProjectId !== undefined;
  const [params, setParams] = useSearchParams();
  const status = params.get("status") ?? "";
  const mode = params.get("mode") ?? "";
  const projectId = fixedProjectId ?? params.get("project") ?? "";
  const page = Number(params.get("page") ?? "1") || 1;
  /** Change filters in the address; any change of filter starts again at page 1. */
  const setFilter = (patch: Record<string, string>) =>
    setParams(
      (now) => {
        const next = new URLSearchParams(now);
        for (const [key, value] of Object.entries(patch)) {
          if (value) next.set(key, value);
          else next.delete(key);
        }
        if (!("page" in patch)) next.delete("page");
        return next;
      },
      { replace: true },
    );
  const [typed, setTyped] = useState(params.get("search") ?? "");
  const search = params.get("search") ?? "";
  // The address keeps the search once typing pauses (O7).
  const settled = useDebounced(typed.trim());
  useEffect(() => {
    if (settled !== search) setFilter({ search: settled });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [settled]);
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
        page_size: PAGE_SIZE,
      }),
    [projectId, status, mode, search, page],
  );
  const codes =
    projects.state.status === "loaded"
      ? Object.fromEntries(projects.state.data.items.map((p) => [p.id, p.code]))
      : {};
  // Many tasks at once (D-093): approve the ones waiting for admin review, each through the
  // single-task checks. Exports are per project, on the project's Export tab (D-094).
  const canSelect = can("tasks.assign");
  // The selection belongs to the list it was made in: another filter or page starts empty.
  const listKey = JSON.stringify([projectId, status, mode, search, page]);
  const [selection, setSelection] = useState<{ key: string; ids: string[] }>({ key: "", ids: [] });
  const selected = selection.key === listKey ? selection.ids : [];
  const setSelected = (ids: string[]) => setSelection({ key: listKey, ids });
  // A message handed over by the page before (for example "Task T000012 deleted.").
  const handed = (useLocation().state as { message?: string } | null)?.message ?? null;
  const { busy, error, message, run } = useAction(tasks.reload, handed);
  const rows: TaskSummary[] = tasks.state.status === "loaded" ? tasks.state.data.items : [];
  const chosen = rows.filter((t) => selected.includes(t.id));
  const waiting = chosen.filter((t) => t.status === "ADMIN_REVIEW");
  const toggle = (id: string) =>
    setSelected(selected.includes(id) ? selected.filter((x) => x !== id) : [...selected, id]);

  const approveSelected = () =>
    run(async () => {
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
      setSelected([]);
      return (
        `${done} approved.` +
        (skipped ? ` ${skipped} skipped: not waiting for admin review.` : "") +
        (failed.length ? ` Not approved: ${failed.join("; ")}.` : "")
      );
    }, "approve");

  const newTask = can("tasks.assign") ? (
    <Link
      className="button button--primary"
      to={inProject ? `/tasks/new?project=${projectId}` : "/tasks/new"}
    >
      <Icon name="plus" size={16} weight="bold" />
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
          <h1 id="tasks-title">Tasks</h1>
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
            onChange={(e) => setFilter({ project: e.target.value })}
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
          onChange={(e) => setFilter({ status: e.target.value })}
          options={[
            { value: "", label: "All" },
            ...Object.entries(TASK_STATUS_LABELS).map(([value, label]) => ({ value, label })),
          ]}
        />
        <Select
          label="Recording type"
          value={mode}
          onChange={(e) => setFilter({ mode: e.target.value })}
          options={[
            { value: "", label: "All" },
            ...Object.entries(MODE_LABELS).map(([value, label]) => ({ value, label })),
          ]}
        />
      </div>
      {canSelect && selected.length > 0 ? (
        <div className="card bulkbar" role="group" aria-label="Actions for selected tasks">
          <strong>{selected.length} selected</strong>
          <Button
            icon="verified"
            busy={busy === "approve"}
            disabled={waiting.length === 0 || busy !== null}
            onClick={() => void approveSelected()}
          >
            Approve selected ({waiting.length})
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
          <DataTable className="tasks-table">
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
                <th scope="col">Recording type</th>
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
                      {labelFor(MODE_LABELS, t.recording_mode)}
                    </span>
                  </td>
                  <td>
                    <StatusBadge status={t.status} label={labelFor(TASK_STATUS_LABELS, t.status)} />
                  </td>
                  <td>
                    <span className={`priority priority--${t.priority.toLowerCase()}`}>
                      {labelFor(PRIORITY_LABELS, t.priority)}
                    </span>
                  </td>
                  <td>{t.due_at ? day(t.due_at) : "-"}</td>
                </tr>
              ))}
            </tbody>
          </DataTable>
          <Pagination
            page={page}
            pageSize={PAGE_SIZE}
            total={tasks.state.data.total}
            onPage={(n) => setFilter({ page: String(n) })}
          />
        </>
      ) : null}
    </section>
  );
}
