import { apiRequest } from "./client";

export interface User {
  id: string;
  email: string;
  display_name: string;
  status: "ACTIVE" | "DISABLED";
  roles: string[];
  mfa_enabled: boolean;
  password_set: boolean;
  last_login_at: string | null;
  created_at: string;
}

export interface Page<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}

export interface ImportRow {
  line: number;
  email: string;
  display_name: string;
  roles: string[];
  errors: string[];
}

export interface Setting {
  key: string;
  value: number | null;
  min_value: number;
  max_value: number;
  updated_at: string;
}

export const ROLE_LABELS: Record<string, string> = {
  SUPER_ADMIN: "Super Admin",
  PROJECT_ADMIN: "Project Admin",
  MODERATOR: "Moderator",
  TRANSCRIBER: "Transcriber",
  QC_EXECUTIVE: "QC Executive",
  CLIENT_VIEWER: "Client Viewer",
};
export const ROLE_CODES = Object.keys(ROLE_LABELS);

export function query(params: Record<string, string | number | undefined>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== "") search.set(key, String(value));
  }
  const text = search.toString();
  return text ? `?${text}` : "";
}

export const listUsers = (params: Record<string, string | number | undefined>) =>
  apiRequest<Page<User>>(`/api/v1/users${query(params)}`);
export const getUser = (id: string) => apiRequest<User>(`/api/v1/users/${id}`);
export const createUser = (body: { email: string; display_name: string; roles: string[] }) =>
  apiRequest<{ user: User; invite_sent: boolean }>("/api/v1/users", { method: "POST", body });
export const updateUser = (id: string, body: { email?: string; display_name?: string }) =>
  apiRequest<User>(`/api/v1/users/${id}`, { method: "PATCH", body });
export const setUserStatus = (id: string, active: boolean) =>
  apiRequest<User>(`/api/v1/users/${id}/${active ? "enable" : "disable"}`, { method: "POST" });
export const setUserRoles = (id: string, roles: string[]) =>
  apiRequest<User>(`/api/v1/users/${id}/roles`, { method: "PUT", body: { roles } });
export const sendPasswordLink = (id: string) =>
  apiRequest<{ sent: boolean }>(`/api/v1/users/${id}/send-password-link`, { method: "POST" });
export const revokeUserSessions = (id: string) =>
  apiRequest<{ sessions_revoked: number }>(`/api/v1/users/${id}/sessions/revoke`, {
    method: "POST",
  });
export const previewImport = (csv: string) =>
  apiRequest<{ rows: ImportRow[]; valid_count: number; invalid_count: number }>(
    "/api/v1/users/import/preview",
    { method: "POST", body: { csv } },
  );
export const confirmImport = (csv: string) =>
  apiRequest<{ created: number; skipped: ImportRow[]; invites_failed: number }>(
    "/api/v1/users/import/confirm",
    { method: "POST", body: { csv } },
  );
export const getSettings = () => apiRequest<Setting[]>("/api/v1/settings");
export const updateSettings = (values: Record<string, number>) =>
  apiRequest<Setting[]>("/api/v1/settings", { method: "PATCH", body: { values } });
