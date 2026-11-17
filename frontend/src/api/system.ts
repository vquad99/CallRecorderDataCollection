import { apiRequest } from "./client";

export type CheckState = "ok" | "error" | "not_configured";

export interface Readiness {
  status: "ready" | "not_ready";
  checks: Record<string, CheckState>;
}

export interface VersionInfo {
  name: string;
  version: string;
  environment: string;
}

/** What the platform found wrong with itself at its last look (D-109). */
export interface OperationAlerts {
  /** Whether anyone is told by email (ALERT_EMAIL), and to how many addresses. */
  email_configured: boolean;
  recipients: number;
  active: { code: string; summary: string; count: number; since: string }[];
}

export interface SystemStatus extends Readiness {
  version: VersionInfo;
  alerts?: OperationAlerts;
}

/** The Super Admin's System status page (owner 2026-11-11: nobody else sees it). */
export function getSystemStatus(signal?: AbortSignal): Promise<SystemStatus> {
  return apiRequest<SystemStatus>("/api/v1/system/status", signal ? { signal } : {});
}
