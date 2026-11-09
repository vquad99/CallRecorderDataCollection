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

export function getReadiness(signal?: AbortSignal): Promise<Readiness> {
  return apiRequest<Readiness>("/health/ready", {
    acceptStatuses: [503],
    ...(signal ? { signal } : {}),
  });
}

export function getVersion(signal?: AbortSignal): Promise<VersionInfo> {
  return apiRequest<VersionInfo>("/api/v1/version", signal ? { signal } : {});
}
