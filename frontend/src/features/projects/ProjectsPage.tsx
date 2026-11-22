// Projects the user can see (PROJ-001, PROJ-012). The search, the status and the page live in the
// address (?search=...&status=ACTIVE&page=2), so opening a project and coming back with the
// browser's Back button keeps them (FEA-07), as on the Tasks page.
import { useEffect, useState } from "react";
import { Link, useLocation, useSearchParams } from "react-router";

import { listProjects } from "../../api/projects";
import { useAuth } from "../../auth/AuthContext";
import { DataTable } from "../../components/DataTable";
import { Button } from "../../components/form/Button";
import { Select } from "../../components/form/Select";
import { TextField } from "../../components/form/TextField";
import { Icon } from "../../components/Icon";
import { SuccessNotice } from "../../components/Notice";
import { Pagination } from "../../components/Pagination";
import { EmptyState, ErrorState, LoadingState } from "../../components/StateViews";
import { StatusBadge } from "../../components/StatusBadge";
import { useDebounced } from "../../hooks/useDebounced";
import { useResource } from "../../hooks/useResource";
import { labelFor, MODE_LABELS, PROJECT_STATUS_LABELS } from "../../lib/labels";

const PAGE_SIZE = 25;

export function ProjectsPage() {
  const { can } = useAuth();
  // Set by New project after a save (D-084); kept while the list is filtered.
  const handed = (useLocation().state as { created?: string } | null)?.created ?? null;
  const [created] = useState(handed);
  const [params, setParams] = useSearchParams();
  const search = params.get("search") ?? "";
  const status = params.get("status") ?? "";
  const page = Math.max(1, Math.trunc(Number(params.get("page") ?? "1")) || 1);
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
  const [typed, setTyped] = useState(search);
  // The address keeps the search once typing pauses (O7).
  const settled = useDebounced(typed.trim());
  useEffect(() => {
    if (settled !== search) setFilter({ search: settled });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [settled]);
  const { state, reload } = useResource(
    () =>
      listProjects({
        search: search || undefined,
        status: status || undefined,
        page,
        page_size: PAGE_SIZE,
      }),
    [search, status, page],
  );
  const filtered = search !== "" || status !== "";
  const clearFilters = () => {
    setTyped("");
    setFilter({ search: "", status: "" });
  };

  return (
    <section aria-labelledby="projects-title" className="stack">
      <div className="page-header">
        <h1 id="projects-title">Projects</h1>
        {can("projects.create") ? (
          <Link className="button button--primary" to="/projects/new">
            <Icon name="plus" size={16} weight="bold" />
            New project
          </Link>
        ) : null}
      </div>
      <SuccessNotice message={created} />
      {/* The filters in a framed bar of their own, Clear filters last, as on every list (D-158). */}
      <div className="filters" role="group" aria-label="Filters">
        <TextField
          label="Search"
          type="search"
          value={typed}
          onChange={(e) => setTyped(e.target.value)}
        />
        <Select
          label="Status"
          value={status}
          onChange={(e) => setFilter({ status: e.target.value })}
          options={[
            { value: "", label: "All" },
            ...Object.entries(PROJECT_STATUS_LABELS).map(([value, label]) => ({ value, label })),
          ]}
        />
        {filtered || typed !== "" ? (
          <Button variant="secondary" icon="filterX" onClick={clearFilters}>
            Clear filters
          </Button>
        ) : null}
      </div>
      {state.status === "loading" ? <LoadingState label="Loading projects" /> : null}
      {state.status === "failed" ? <ErrorState error={state.error} onRetry={reload} /> : null}
      {state.status === "loaded" && state.data.items.length === 0 ? (
        filtered ? (
          <EmptyState title="No projects match" message="Try another search or status." />
        ) : can("projects.create") ? (
          <EmptyState
            title="No projects yet"
            message="Create the first one with New project; it starts as a draft."
          />
        ) : (
          <EmptyState title="No projects" message="You are not a member of any project yet." />
        )
      ) : null}
      {state.status === "loaded" && state.data.items.length > 0 ? (
        <>
          <DataTable>
            <thead>
              <tr>
                <th scope="col">Code</th>
                <th scope="col">Name</th>
                <th scope="col">Status</th>
                <th scope="col">Recording type</th>
              </tr>
            </thead>
            <tbody>
              {state.data.items.map((p) => (
                <tr key={p.id}>
                  <td className="mono">
                    <Link to={`/projects/${p.id}`}>{p.code}</Link>
                  </td>
                  <td>{p.name}</td>
                  <td>
                    <StatusBadge
                      status={p.status}
                      label={labelFor(PROJECT_STATUS_LABELS, p.status)}
                    />
                  </td>
                  <td>
                    {[
                      p.allows_telephony ? MODE_LABELS.TELEPHONY : "",
                      p.allows_face_to_face ? MODE_LABELS.FACE_TO_FACE : "",
                    ]
                      .filter(Boolean)
                      .join(", ") || "-"}
                  </td>
                </tr>
              ))}
            </tbody>
          </DataTable>
          <Pagination
            page={page}
            pageSize={PAGE_SIZE}
            total={state.data.total}
            onPage={(n) => setFilter({ page: n > 1 ? String(n) : "" })}
          />
        </>
      ) : null}
    </section>
  );
}
