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
  qc: {
    passed: number;
    rejected: number;
    returned: number;
    waiting: number;
    auto_pass: number;
    auto_review: number;
    auto_fail: number;
  } | null;
  queues: Record<string, number> | null;
  team: { name: string; recordings: number; recorded_hours: number }[] | null;
  storage_bytes: number | null;
  /** Phone calls, for managers (D-108). */
  calls: {
    placed: number;
    recorded: number;
    could_not_be_placed: number;
    needs_a_person: number;
    open: number;
  } | null;
  /** What the filters offer; `staff` for managers only. */
  options: {
    languages?: string[];
    dialects?: string[];
    staff?: { id: string; name: string }[];
  };
  /** The chosen days, when days were chosen. */
  date_from: string | null;
  date_to: string | null;
}

/** What narrows the dashboard (D-108). Days are counted in the report's time zone. */
export type DashboardFilters = {
  project_id?: string | undefined;
  days?: number;
  mode?: string | undefined;
  language?: string | undefined;
  dialect?: string | undefined;
  status?: string | undefined;
  staff_id?: string | undefined;
  date_from?: string | undefined;
  date_to?: string | undefined;
};

export const getDashboard = (params: DashboardFilters) =>
  apiRequest<Dashboard>(`/api/v1/dashboard${query(params)}`);
