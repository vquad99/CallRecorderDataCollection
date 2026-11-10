// Projects the user can see (PROJ-001, PROJ-012).
import { useState } from "react";
import { Link } from "react-router";

import { listProjects } from "../../api/projects";
import { useAuth } from "../../auth/AuthContext";
import { Select } from "../../components/form/Select";
import { TextField } from "../../components/form/TextField";
import { Pagination } from "../../components/Pagination";
import { EmptyState, ErrorState, LoadingState } from "../../components/StateViews";
import { useResource } from "../../hooks/useResource";
import { Avatar, Icon, IconTile } from "../../components/Icon";
import { StatusBadge } from "../../components/StatusBadge";

const PAGE_SIZE = 25;
export const STATUS_LABELS: Record<string, string> = {
  DRAFT: "Draft",
  ACTIVE: "Active",
  PAUSED: "Paused",
  COMPLETED: "Completed",
  ARCHIVED: "Archived",
};

export function ProjectsPage() {
  const { can } = useAuth();
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("");
  const [page, setPage] = useState(1);
  const { state, reload } = useResource(
    () => listProjects({ search, status, page, page_size: PAGE_SIZE }),
    [search, status, page],
  );

  return (
    <section aria-labelledby="projects-title" className="stack">
      <div className="page-header">
        <h1 id="projects-title">
          <IconTile name="projects" tone="blue" />
          Projects
        </h1>
        {can("projects.create") ? (
          <Link className="button button--primary" to="/projects/new">
            <Icon name="plus" size={18} weight="bold" />
            New project
          </Link>
        ) : null}
      </div>
      <div className="filters">
        <TextField
          label="Search"
          type="search"
          value={search}
          onChange={(e) => {
            setSearch(e.target.value);
            setPage(1);
          }}
        />
        <Select
          label="Status"
          value={status}
          onChange={(e) => {
            setStatus(e.target.value);
            setPage(1);
          }}
          options={[
            { value: "", label: "All" },
            ...Object.entries(STATUS_LABELS).map(([value, label]) => ({ value, label })),
          ]}
        />
      </div>
      {state.status === "loading" ? <LoadingState label="Loading projects" /> : null}
      {state.status === "failed" ? <ErrorState error={state.error} onRetry={reload} /> : null}
      {state.status === "loaded" && state.data.items.length === 0 ? (
        <EmptyState title="No projects" message="You are not a member of any project yet." />
      ) : null}
      {state.status === "loaded" && state.data.items.length > 0 ? (
        <>
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th scope="col">Code</th>
                  <th scope="col">Name</th>
                  <th scope="col">Status</th>
                  <th scope="col">Modes</th>
                </tr>
              </thead>
              <tbody>
                {state.data.items.map((p) => (
                  <tr key={p.id}>
                    <td>
                      <span className="cell-person">
                        <Avatar name={p.code} square />
                        <Link to={`/projects/${p.id}`}>{p.code}</Link>
                      </span>
                    </td>
                    <td>{p.name}</td>
                    <td>
                      <StatusBadge status={p.status} label={STATUS_LABELS[p.status] ?? p.status} />
                    </td>
                    <td>
                      {[
                        p.allows_telephony ? "Telephony" : "",
                        p.allows_face_to_face ? "Face-to-face" : "",
                      ]
                        .filter(Boolean)
                        .join(", ")}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <Pagination page={page} pageSize={PAGE_SIZE} total={state.data.total} onPage={setPage} />
        </>
      ) : null}
    </section>
  );
}
