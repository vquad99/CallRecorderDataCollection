// User list with search, filters, pagination and CSV export (USER-004, USER-006).
import { useState } from "react";
import { Link, useNavigate } from "react-router";

import { apiDownload } from "../../api/client";
import { listUsers, ROLE_CODES, ROLE_LABELS } from "../../api/admin";
import { Button } from "../../components/form/Button";
import { Select } from "../../components/form/Select";
import { TextField } from "../../components/form/TextField";
import { ErrorNotice } from "../../components/Notice";
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
  const [search, setSearch] = useState("");
  const [role, setRole] = useState("");
  const [status, setStatus] = useState("");
  const [page, setPage] = useState(1);
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
  const query = useDebounced(search.trim());
  const { state, reload } = useResource(
    () => listUsers({ search: query, role, status, page, page_size: PAGE_SIZE }),
    [query, role, status, page],
  );

  return (
    <section aria-labelledby="users-title" className="stack">
      <div className="page-header">
        <h1 id="users-title">Users</h1>
        <div className="actions">
          <Link className="button button--primary" to="/admin/users/new">
            <Icon name="userPlus" size={16} />
            Add user
          </Link>
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
        </div>
      </div>
      <ErrorNotice error={error} />
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
          label="Role"
          value={role}
          onChange={(e) => {
            setRole(e.target.value);
            setPage(1);
          }}
          options={[
            { value: "", label: "All roles" },
            ...ROLE_CODES.map((c) => ({ value: c, label: ROLE_LABELS[c] ?? c })),
          ]}
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
            { value: "ACTIVE", label: "Active" },
            { value: "DISABLED", label: "Disabled" },
          ]}
        />
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
          <Pagination page={page} pageSize={PAGE_SIZE} total={state.data.total} onPage={setPage} />
        </>
      ) : null}
    </section>
  );
}
