// User list with search, filters, pagination and CSV export (USER-004, USER-006).
import { useState } from "react";
import { Link, useNavigate } from "react-router";

import { apiDownload, type ApiError } from "../../api/client";
import { listUsers, ROLE_CODES, ROLE_LABELS } from "../../api/admin";
import { Button } from "../../components/form/Button";
import { Select } from "../../components/form/Select";
import { TextField } from "../../components/form/TextField";
import { ErrorNotice } from "../../components/Notice";
import { Pagination } from "../../components/Pagination";
import { EmptyState, ErrorState, LoadingState } from "../../components/StateViews";
import { toApiError, useResource } from "../../hooks/useResource";
import { Avatar, Icon, IconTile } from "../../components/Icon";
import { StatusBadge } from "../../components/StatusBadge";
import { useAuth } from "../../auth/AuthContext";

const PAGE_SIZE = 25;

export function UsersPage() {
  const [search, setSearch] = useState("");
  const [role, setRole] = useState("");
  const [status, setStatus] = useState("");
  const [page, setPage] = useState(1);
  const [exportError, setExportError] = useState<ApiError | null>(null);
  const [viewError, setViewError] = useState<ApiError | null>(null);
  const { user: me, viewAs } = useAuth();
  const navigate = useNavigate();
  // Super Admin only (D-100): see the app exactly as this person does, read-only.
  const canViewAs = Boolean(me?.roles.includes("SUPER_ADMIN") && !me.viewer);

  function startViewing(id: string) {
    setViewError(null);
    viewAs(id)
      .then(() => navigate("/"))
      .catch((err: unknown) => setViewError(toApiError(err)));
  }
  const { state, reload } = useResource(
    () => listUsers({ search, role, status, page, page_size: PAGE_SIZE }),
    [search, role, status, page],
  );

  async function exportCsv() {
    setExportError(null);
    try {
      await apiDownload("/api/v1/users/export", "users.csv");
    } catch (err) {
      setExportError(toApiError(err));
    }
  }

  return (
    <section aria-labelledby="users-title" className="stack">
      <div className="page-header">
        <h1 id="users-title">
          <IconTile name="users" tone="violet" />
          Users
        </h1>
        <div className="actions">
          <Link className="button button--primary" to="/admin/users/new">
            <Icon name="plus" size={18} weight="bold" />
            Add user
          </Link>
          <Link className="button button--secondary" to="/admin/users/import">
            <Icon name="upload" size={18} />
            Import CSV
          </Link>
          <Button variant="secondary" onClick={() => void exportCsv()}>
            Export CSV
          </Button>
        </div>
      </div>
      <ErrorNotice error={exportError} />
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
      <ErrorNotice error={viewError} />
      {state.status === "loading" ? <LoadingState label="Loading users" /> : null}
      {state.status === "failed" ? <ErrorState error={state.error} onRetry={reload} /> : null}
      {state.status === "loaded" && state.data.items.length === 0 ? (
        <EmptyState title="No users found" />
      ) : null}
      {state.status === "loaded" && state.data.items.length > 0 ? (
        <>
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th scope="col">Name</th>
                  <th scope="col">Email</th>
                  <th scope="col">Roles</th>
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
                    <td>
                      <StatusBadge
                        status={
                          u.status === "ACTIVE"
                            ? u.password_set
                              ? "ACTIVE"
                              : "INVITED"
                            : "DISABLED"
                        }
                        label={`${u.status === "ACTIVE" ? "Active" : "Disabled"}${u.password_set ? "" : " (invitation pending)"}`}
                      />
                    </td>
                    {canViewAs ? (
                      <td className="actions">
                        {u.status === "ACTIVE" && u.id !== me?.id ? (
                          <Button variant="secondary" onClick={() => startViewing(u.id)}>
                            View as {u.display_name}
                          </Button>
                        ) : null}
                      </td>
                    ) : null}
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
