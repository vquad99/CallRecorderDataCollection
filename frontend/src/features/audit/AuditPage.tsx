// Read-only audit log (SEC-001). Project Admins see entries about their projects only. Each action
// reads in words, with its key under it (the key is what the Action box takes), and a change lists
// only what changed, one line per field: "Status: DRAFT → ASSIGNED".
import { useState } from "react";

import { listAudit } from "../../api/work";
import { DataTable } from "../../components/DataTable";
import { Select } from "../../components/form/Select";
import { TextField } from "../../components/form/TextField";
import { Pagination } from "../../components/Pagination";
import { EmptyState, ErrorState, LoadingState } from "../../components/StateViews";
import { useDebounced } from "../../hooks/useDebounced";
import { useResource } from "../../hooks/useResource";
import { when } from "../../lib/format";
import { labelFor } from "../../lib/labels";
import "./audit.css";

/** Areas of the platform: the first part of an action ("task" for "task.created"). */
const AREAS: Record<string, string> = {
  auth: "Sign-in",
  user: "Users",
  project: "Projects",
  participant: "Participants",
  consent: "Consent",
  task: "Tasks",
  recording: "Recordings",
  asset: "Audio files",
  audio_qc: "Audio QC",
  call: "Phone calls",
  calls: "Call lists",
  export: "Exports",
  payments: "Payments",
  settings: "Settings",
};

/** Actions that do not read well as "Area: what happened". */
const ACTIONS: Record<string, string> = {
  "auth.login": "Signed in",
  "auth.logout": "Signed out",
  "auth.login_failed": "Sign-in failed",
  "auth.mfa_enabled": "Two-step sign-in turned on",
  "auth.mfa_disabled": "Two-step sign-in turned off",
  "auth.view_as_started": "Started viewing as another user",
  "auth.view_as_stopped": "Stopped viewing as another user",
  "audio_qc.automatic": "Automatic audio check",
  "call.b_dialled": "Phone calls: Participant B dialled",
  "consent.self_recorded": "Consent: Answered on the participant page",
  "task.qc_auto_assigned": "Tasks: QC assigned automatically",
  "user.agent_seat": "Users: Phone seat changed",
  "user.mfa_reset": "Users: Two-step sign-in reset",
  "user.phone_line_signed_in": "Phone line signed in",
};

/** What an entry is about. */
const RECORD_TYPES: Record<string, string> = {
  user: "User",
  session: "Sign-in session",
  project: "Project",
  participant: "Participant",
  participant_document: "Participant document",
  task: "Task",
  recording: "Recording",
  audio_asset: "Audio file",
  call: "Phone call",
  calls: "Call list",
  export_job: "Export",
  system_settings: "Settings",
};

/** "Tasks: Status changed" for task.status_changed. */
export function actionLabel(action: string): string {
  const known = ACTIONS[action];
  if (known) return known;
  const dot = action.indexOf(".");
  if (dot < 0) return labelFor({}, action);
  return `${labelFor(AREAS, action.slice(0, dot))}: ${labelFor({}, action.slice(dot + 1))}`;
}

const present = (v: unknown) => v !== null && v !== undefined;

/** A value as plain words: lists joined, nothing as "-", JSON only for what is nested. */
function plain(value: unknown): string {
  if (!present(value) || value === "") return "-";
  if (typeof value === "boolean") return value ? "Yes" : "No";
  if (Array.isArray(value)) {
    const items = value.map((v) =>
      present(v) && typeof v === "object" ? JSON.stringify(v) : plain(v),
    );
    return items.length ? items.join(", ") : "-";
  }
  return typeof value === "object" ? JSON.stringify(value) : String(value);
}

const fields = (value: unknown): Record<string, unknown> =>
  !present(value)
    ? {}
    : typeof value === "object" && !Array.isArray(value)
      ? (value as Record<string, unknown>)
      : { value };

/** One line per field: "Field: old → new" for what changed, "Field: value" for a one-sided entry
 * and for what only the "after" side names (a status change's comment, say). */
export function changeLines(before: unknown, after: unknown): string[] {
  const was = fields(before);
  const now = fields(after);
  const both = present(before) && present(after);
  const lines: string[] = [];
  for (const key of new Set([...Object.keys(was), ...Object.keys(now)])) {
    const name = labelFor({}, key);
    if (!both) {
      lines.push(`${name}: ${plain(present(before) ? was[key] : now[key])}`);
      continue;
    }
    const old = plain(was[key]);
    const next = plain(now[key]);
    if (old !== next) lines.push(key in was ? `${name}: ${old} → ${next}` : `${name}: ${next}`);
  }
  return lines;
}

export function AuditPage() {
  const [area, setArea] = useState("");
  const [action, setAction] = useState("");
  const [entityType, setEntityType] = useState("");
  const [page, setPage] = useState(1);
  // An exact action typed in wins over the area; asked once typing pauses.
  const asked = useDebounced(action.trim()) || area;
  const { state, reload } = useResource(
    () => listAudit({ action: asked, entity_type: entityType, page, page_size: 50 }),
    [asked, entityType, page],
  );
  return (
    <section aria-labelledby="audit-title" className="stack">
      <h1 id="audit-title">Audit log</h1>
      <div className="filters">
        <Select
          label="Area"
          value={area}
          onChange={(e) => {
            setArea(e.target.value);
            setPage(1);
          }}
          options={[
            { value: "", label: "Every area" },
            ...Object.entries(AREAS).map(([value, label]) => ({ value, label })),
          ]}
        />
        <Select
          label="About"
          value={entityType}
          onChange={(e) => {
            setEntityType(e.target.value);
            setPage(1);
          }}
          options={[
            { value: "", label: "Anything" },
            ...Object.entries(RECORD_TYPES).map(([value, label]) => ({ value, label })),
          ]}
        />
        <TextField
          label="Action"
          placeholder="e.g. recording.completed"
          title="Optional: the exact action, for example recording.completed."
          value={action}
          onChange={(e) => {
            setAction(e.target.value);
            setPage(1);
          }}
        />
      </div>
      {state.status === "loading" ? <LoadingState label="Loading audit log" /> : null}
      {state.status === "failed" ? <ErrorState error={state.error} onRetry={reload} /> : null}
      {state.status === "loaded" && state.data.items.length === 0 ? (
        <EmptyState title="No entries" />
      ) : null}
      {state.status === "loaded" && state.data.items.length > 0 ? (
        <>
          <DataTable>
            <thead>
              <tr>
                <th scope="col">When</th>
                <th scope="col">Who</th>
                <th scope="col">Action</th>
                <th scope="col">About</th>
                <th scope="col">Change</th>
              </tr>
            </thead>
            <tbody>
              {state.data.items.map((e) => {
                const lines = changeLines(e.before, e.after);
                return (
                  <tr key={e.id}>
                    <td className="nowrap">{when(e.created_at)}</td>
                    <td className="break">{e.actor_email ?? "Platform"}</td>
                    <td>
                      {actionLabel(e.action)}
                      <div className="muted mono">{e.action}</div>
                    </td>
                    <td>
                      {labelFor(RECORD_TYPES, e.entity_type)}
                      {e.entity_id ? (
                        <div className="muted mono" title={e.entity_id}>
                          {e.entity_id.slice(0, 8)}
                        </div>
                      ) : null}
                    </td>
                    <td>
                      {lines.length > 0 ? (
                        <details className="audit-change">
                          <summary>
                            {present(e.before) && present(e.after) ? "Before and after" : "Details"}
                          </summary>
                          <ul className="audit-change__lines">
                            {lines.map((line, i) => (
                              <li key={i}>{line}</li>
                            ))}
                          </ul>
                        </details>
                      ) : (
                        <span className="muted">-</span>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </DataTable>
          <Pagination page={page} pageSize={50} total={state.data.total} onPage={setPage} />
        </>
      ) : null}
    </section>
  );
}
