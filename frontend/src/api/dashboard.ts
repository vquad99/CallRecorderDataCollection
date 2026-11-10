// Dashboard summary (GET /api/v1/dashboard). The server decides the view from the caller's role.
import { apiRequest } from "./client";
import { query } from "./admin";

export type DashboardView = "client" | "worker" | "manager";

export interface ModeTotals {
  mode: "FACE_TO_FACE" | "TELEPHONY";
  recorded_hours: number;
  approved_hours: number;
  recordings: number;
  target_hours_per_day: number;
}

export interface DayTotals {
  day: string;
  recorded_hours: number;
  approved_hours: number;
}

export interface Dashboard {
  view: DashboardView;
  timezone: string;
  project_id: string | null;
  projects: { id: string; code: string; name: string }[];
  recorded_hours: number;
  approved_hours: number;
  recordings: number;
  target_hours_per_day: number;
  today_hours: number;
  by_mode: ModeTotals[];
  daily: DayTotals[];
  tasks_total: number;
  tasks_approved: number;
  tasks_by_status: Record<string, number> | null;
  qc: { passed: number; rejected: number; returned: number; waiting: number } | null;
  queues: Record<string, number> | null;
  team: { name: string; recordings: number; recorded_hours: number }[] | null;
  storage_bytes: number | null;
}

export const getDashboard = (params: { project_id?: string | undefined; days?: number }) =>
  apiRequest<Dashboard>(`/api/v1/dashboard${query(params)}`);
