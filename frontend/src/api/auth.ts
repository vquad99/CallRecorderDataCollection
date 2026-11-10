import { apiRequest } from "./client";

export interface Me {
  id: string;
  email: string;
  display_name: string;
  roles: string[];
  permissions: string[];
  project_ids: string[];
  mfa_enabled: boolean;
}

export interface SessionInfo {
  id: string;
  created_at: string;
  last_seen_at: string;
  expires_at: string;
  ip: string | null;
  user_agent: string | null;
  current: boolean;
}

export const ensureCsrf = () => apiRequest<null>("/api/v1/auth/csrf");
export const getMe = () => apiRequest<Me>("/api/v1/auth/me");
export const login = (email: string, password: string, totpCode?: string) =>
  apiRequest<Me>("/api/v1/auth/login", {
    method: "POST",
    body: { email, password, ...(totpCode ? { totp_code: totpCode } : {}) },
  });
export const logout = () => apiRequest<null>("/api/v1/auth/logout", { method: "POST" });
export const forgotPassword = (email: string) =>
  apiRequest<{ status: string }>("/api/v1/auth/password/forgot", {
    method: "POST",
    body: { email },
  });
export const resetPassword = (token: string, newPassword: string) =>
  apiRequest<null>("/api/v1/auth/password/reset", {
    method: "POST",
    body: { token, new_password: newPassword },
  });
export const changePassword = (current: string, next: string) =>
  apiRequest<null>("/api/v1/auth/password/change", {
    method: "POST",
    body: { current_password: current, new_password: next },
  });
export const listSessions = () => apiRequest<SessionInfo[]>("/api/v1/auth/sessions");
export const revokeSession = (id: string) =>
  apiRequest<null>(`/api/v1/auth/sessions/${id}`, { method: "DELETE" });
export const mfaEnroll = (password: string) =>
  apiRequest<{ secret: string; otpauth_uri: string }>("/api/v1/auth/mfa/enroll", {
    method: "POST",
    body: { password },
  });
export const mfaConfirm = (code: string) =>
  apiRequest<null>("/api/v1/auth/mfa/confirm", { method: "POST", body: { code } });
export const mfaDisable = (password: string, code: string) =>
  apiRequest<null>("/api/v1/auth/mfa/disable", { method: "POST", body: { password, code } });
