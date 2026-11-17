// Read-only audit log (SEC-001). Project Admins see entries about their projects only.
import { useState } from "react";

import { listAudit } from "../../api/work";
import { DataTable } from "../../components/DataTable";
import { Select } from "../../components/form/Select";
import { TextField } from "../../components/form/TextField";
import { IconTile } from "../../components/Icon";
import { Pagination } from "../../components/Pagination";
import { EmptyState, ErrorState, LoadingState } from "../../components/StateViews";
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
  audio_qc: "Audio QC",
  call: "Phone calls",
  export: "Exports",
  settings: "Settings",
};

/** What an entry is about. */
const RECORD_TYPES: Record<string, string> = {
  user: "User",
  session: "Sign-in session",
  project: "Project",
  participant: "Participant",
  task: "Task",
  recording: "Recording",
  audio_asset: "Audio file",
  call: "Phone call",
  export_job: "Export",
  system_settings: "Settings",
};

const show = (v: unknown) => (v === null || v === undefined ? "" : JSON.stringify(v));

export function AuditPage() {
  const [area, setArea] = useState("");
  const [action, setAction] = useState("");
  const [entityType, setEntityType] = useState("");
  const [page, setPage] = useState(1);
  // An exact action typed in wins over the area.
  const asked = action.trim() || area;
  const { state, reload } = useResource(
    () => listAudit({ action: asked, entity_type: entityType, page, page_size: 50 }),
    [asked, entityType, page],
  );
  return (
    <section aria-labelledby="audit-title" className="stack">
      <h1 id="audit-title">
        <IconTile name="audit" tone="slate" />
        Audit log
      </h1>
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
          hint="Optional: the exact action, for example recording.completed."
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
              {state.data.items.map((e) => (
                <tr key={e.id}>
                  <td>{when(e.created_at)}</td>
                  <td>{e.actor_email ?? "Platform"}</td>
                  <td className="mono">{e.action}</td>
                  <td>
                    {labelFor(RECORD_TYPES, e.entity_type)}
                    {e.entity_id ? <div className="muted mono break">{e.entity_id}</div> : null}
                  </td>
                  <td>
                    {show(e.before) || show(e.after) ? (
                      <details className="audit-change">
                        <summary>Before and after</summary>
                        <div className="mono break">
                          {show(e.before) ? <div>before: {show(e.before)}</div> : null}
                          {show(e.after) ? <div>after: {show(e.after)}</div> : null}
                        </div>
                      </details>
                    ) : (
                      <span className="muted">-</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </DataTable>
          <Pagination page={page} pageSize={50} total={state.data.total} onPage={setPage} />
        </>
      ) : null}
    </section>
  );
}
