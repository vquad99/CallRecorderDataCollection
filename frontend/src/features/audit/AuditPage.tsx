// Read-only audit log (SEC-001). Project Admins see entries about their projects only.
import { useState } from "react";

import { listAudit } from "../../api/work";
import { TextField } from "../../components/form/TextField";
import { Pagination } from "../../components/Pagination";
import { EmptyState, ErrorState, LoadingState } from "../../components/StateViews";
import { useResource } from "../../hooks/useResource";

const show = (v: unknown) => (v === null || v === undefined ? "" : JSON.stringify(v));

export function AuditPage() {
  const [action, setAction] = useState("");
  const [entityType, setEntityType] = useState("");
  const [page, setPage] = useState(1);
  const { state, reload } = useResource(
    () => listAudit({ action, entity_type: entityType, page, page_size: 50 }),
    [action, entityType, page],
  );
  return (
    <section aria-labelledby="audit-title" className="stack">
      <h1 id="audit-title">Audit log</h1>
      <div className="filters">
        <TextField
          label="Action"
          hint="e.g. task, user.roles_changed"
          value={action}
          onChange={(e) => {
            setAction(e.target.value);
            setPage(1);
          }}
        />
        <TextField
          label="Entity type"
          hint="e.g. task, user, project"
          value={entityType}
          onChange={(e) => {
            setEntityType(e.target.value);
            setPage(1);
          }}
        />
      </div>
      {state.status === "loading" ? <LoadingState label="Loading audit log" /> : null}
      {state.status === "failed" ? (
        <ErrorState message={state.error.message} onRetry={reload} />
      ) : null}
      {state.status === "loaded" && state.data.items.length === 0 ? (
        <EmptyState title="No entries" />
      ) : null}
      {state.status === "loaded" && state.data.items.length > 0 ? (
        <>
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th scope="col">When</th>
                  <th scope="col">Who</th>
                  <th scope="col">Action</th>
                  <th scope="col">Entity</th>
                  <th scope="col">Change</th>
                </tr>
              </thead>
              <tbody>
                {state.data.items.map((e) => (
                  <tr key={e.id}>
                    <td>{new Date(e.created_at).toLocaleString()}</td>
                    <td>{e.actor_email ?? "Platform / anonymous"}</td>
                    <td>{e.action}</td>
                    <td>
                      {e.entity_type}{" "}
                      {e.entity_id ? <span className="muted break">{e.entity_id}</span> : null}
                    </td>
                    <td className="mono break">
                      {show(e.before) ? <div>before: {show(e.before)}</div> : null}
                      {show(e.after) ? <div>after: {show(e.after)}</div> : null}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <Pagination page={page} pageSize={50} total={state.data.total} onPage={setPage} />
        </>
      ) : null}
    </section>
  );
}
