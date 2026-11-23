// User list with search, filters, pagination and CSV export (USER-004, USER-006). The search,
// filters and page live in the address (?role=MODERATOR&page=2), so opening a user and coming back
// with the browser's Back button finds the list as it was.
import { useEffect, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router";

import { apiDownload } from "../../api/client";
import { listUsers, ROLE_CODES, ROLE_LABELS } from "../../api/admin";
import { Button } from "../../components/form/Button";
import { Select } from "../../components/form/Select";
import { TextField } from "../../components/form/TextField";
import { ErrorNotice } from "../../components/Notice";
import { PageHeader } from "../../components/PageHeader";
import { Pagination } from "../../components/Pagination";
import { EmptyState, ErrorState, LoadingState } from "../../components/StateViews";
import { useAction } from "../../hooks/useAction";
import { useDebounced } from "../../hooks/useDebounced";
import { useResource } from "../../hooks/useResource";
import { Avatar, Icon } from "../../components/Icon";
import { StatusBadge } from "../../components/StatusBadge";
import { useAuth } from "../../auth/AuthContext";
import { DataTable } from "../../components/DataTable";

const PAGE_SIZE = 25;

export function UsersPage() {
  const [params, setParams] = useSearchParams();
  const search = params.get("search") ?? "";
  const role = params.get("role") ?? "";
  const status = params.get("status") ?? "";
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
  const [typed, setTyped] = useState(search);
  // The address keeps the search once typing pauses (O7).
  const settled = useDebounced(typed.trim());
  useEffect(() => {
    if (settled !== search) setFilter({ search: settled });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [settled]);
  const { busy, error, run } = useAction();
  const { user: me, viewAs } = useAuth();
  const navigate = useNavigate();
  // Super Admin only (D-100): see the app exactly as this person does, read-only.
  const canViewAs = Boolean(me?.roles.includes("SUPER_ADMIN") && !me.viewer);

  const startViewing = (id: string) =>
    void run(async () => {
      await viewAs(id);
      void navigate("/");
    }, id);
  const { state, reload } = useResource(
    () => listUsers({ search, role, status, page, page_size: PAGE_SIZE }),
    [search, role, status, page],
  );

  return (
    <section aria-labelledby="users-title" className="stack">
      {/* The main button last, as on every other page (D-159). */}
      <PageHeader
        id="users-title"
        title="Users"
        lead="Staff accounts, their roles and their projects."
        actions={
          <>
            <Link className="button button--secondary" to="/admin/users/import">
              <Icon name="fileUp" size={16} />
              Import CSV
            </Link>
            <Button
              variant="secondary"
              icon="fileCsv"
              busy={busy === "export"}
              onClick={() =>
                void run(() => apiDownload("/api/v1/users/export", "users.csv"), "export")
              }
            >
              Export CSV
            </Button>
            <Link className="button button--primary" to="/admin/users/new">
              <Icon name="userPlus" size={16} />
              Add user
            </Link>
          </>
        }
      />
      <ErrorNotice error={error} />
      {/* The filters, a section of their own (D-158). */}
      <div className="filters" role="group" aria-label="Filters">
        <TextField
          label="Search"
          type="search"
          value={typed}
          onChange={(e) => setTyped(e.target.value)}
        />
        <Select
          label="Role"
          value={role}
          onChange={(e) => setFilter({ role: e.target.value })}
          options={[
            { value: "", label: "All roles" },
            ...ROLE_CODES.map((c) => ({ value: c, label: ROLE_LABELS[c] ?? c })),
          ]}
        />
        <Select
          label="Status"
          value={status}
          onChange={(e) => setFilter({ status: e.target.value })}
          options={[
            { value: "", label: "All" },
            { value: "ACTIVE", label: "Active" },
            { value: "DISABLED", label: "Disabled" },
          ]}
        />
        {typed || role || status ? (
          <Button
            variant="secondary"
            icon="filterX"
            onClick={() => {
              setTyped("");
              setFilter({ search: "", role: "", status: "" });
            }}
          >
            Clear filters
          </Button>
        ) : null}
      </div>
      {state.status === "loading" ? <LoadingState label="Loading users" /> : null}
      {state.status === "failed" ? <ErrorState error={state.error} onRetry={reload} /> : null}
      {state.status === "loaded" && state.data.items.length === 0 ? (
        <EmptyState title="No users found" />
      ) : null}
      {state.status === "loaded" && state.data.items.length > 0 ? (
        <>
          <DataTable>
            <thead>
              <tr>
                <th scope="col">Name</th>
                <th scope="col">Email</th>
                <th scope="col">Roles</th>
                <th scope="col">Phone seat</th>
                <th scope="col">Status</th>
                {canViewAs ? (
                  <th scope="col">
                    <span className="sr-only">View as</span>
                  </th>
                ) : null}
              </tr>
            </thead>
            <tbody>
              {state.data.items.map((u) => (
                <tr key={u.id}>
                  <td>
                    <span className="cell-person">
                      <Avatar name={u.display_name} />
                      <Link to={`/admin/users/${u.id}`}>{u.display_name}</Link>
                    </span>
                  </td>
                  <td>{u.email}</td>
                  <td>{u.roles.map((r) => ROLE_LABELS[r] ?? r).join(", ")}</td>
                  <td>{u.telephony_agent_id || "-"}</td>
                  <td>
                    <StatusBadge
                      status={
                        u.status === "ACTIVE" ? (u.password_set ? "ACTIVE" : "INVITED") : "DISABLED"
                      }
                      label={`${u.status === "ACTIVE" ? "Active" : "Disabled"}${u.password_set ? "" : " (invitation pending)"}`}
                    />
                  </td>
                  {canViewAs ? (
                    <td className="actions">
                      {u.status === "ACTIVE" && u.id !== me?.id ? (
                        <Button
                          variant="secondary"
                          icon="eye"
                          aria-label={`View as ${u.display_name}`}
                          busy={busy === u.id}
                          onClick={() => startViewing(u.id)}
                        >
                          View as
                        </Button>
                      ) : null}
                    </td>
                  ) : null}
                </tr>
              ))}
            </tbody>
          </DataTable>
          <Pagination
            page={page}
            pageSize={PAGE_SIZE}
            total={state.data.total}
            onPage={(n) => setFilter({ page: String(n) })}
          />
        </>
      ) : null}
    </section>
  );
}
