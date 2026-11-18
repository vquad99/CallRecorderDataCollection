// Payments (D-137): each project's rates (rupees per approved minute) and what moderators and
// participants earned on approved tasks. Money and minutes travel as text with two places.
import { apiDownload, apiRequest, query } from "./client";

export type Payee = "moderators" | "participants";

export interface ProjectRates {
  project_id: string;
  project_code: string;
  project_name: string;
  /** Rupees per approved minute; null: no rate set yet. */
  moderator_rate: string | null;
  participant_rate: string | null;
  updated_at: string | null;
  updated_by: string | null;
}

export interface PayTotals {
  /** Approved tasks (moderators) or approved sessions (participants). */
  count: number;
  minutes: string;
  /** The sum of the amounts: minutes of projects with no rate are not in it. */
  amount: string;
  minutes_without_rate: string;
}

interface PayRow {
  project_id: string;
  project_code: string;
  rate: string | null;
  /** null: the project has no rate yet. */
  amount: string | null;
}

export interface ModeratorPay extends PayRow {
  user_id: string;
  name: string;
  approved_tasks: number;
  approved_minutes: string;
}

export interface ParticipantPay extends PayRow {
  participant_id: string;
  participant_code: string;
  /** Only for people who may see participants' details (D-128). */
  name: string | null;
  approved_sessions: number;
  /** The participant's equal share of each approved session. */
  payable_minutes: string;
}

export interface Payments<Row> {
  timezone: string;
  date_from: string | null;
  date_to: string | null;
  totals: PayTotals;
  rows: Row[];
}

export interface PayFilters {
  project_id?: string | undefined;
  /** Approval days, India time (YYYY-MM-DD). */
  date_from?: string | undefined;
  date_to?: string | undefined;
  search?: string | undefined;
}

const base = "/api/v1/payments";

export const listRates = () => apiRequest<ProjectRates[]>(`${base}/rates`);
export const setRates = (
  projectId: string,
  body: { moderator_rate: string | null; participant_rate: string | null },
) => apiRequest<ProjectRates>(`${base}/rates/${projectId}`, { method: "PUT", body });
export const moderatorPay = (filters: PayFilters) =>
  apiRequest<Payments<ModeratorPay>>(`${base}/moderators${query({ ...filters })}`);
export const participantPay = (filters: PayFilters) =>
  apiRequest<Payments<ParticipantPay>>(`${base}/participants${query({ ...filters })}`);
/** The tab as a spreadsheet, with a Total line (spreadsheet-safe cells). */
export const downloadPay = (who: Payee, filters: PayFilters) =>
  apiDownload(`${base}/${who}/export${query({ ...filters })}`);
