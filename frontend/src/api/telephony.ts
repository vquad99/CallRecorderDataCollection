// Phone calls through TxContact (D-101, D-102, D-103): start, checklist, close, cancel, pick the
// right recording, retry; and the figures, list and spreadsheet of calls.
import { apiDownload, apiRequest } from "./client";

export type CallState =
  | "DIALLING"
  | "DIAL_FAILED"
  | "CANCELLED"
  | "WAITING_FOR_RECORDING"
  | "NEEDS_MATCH"
  | "FETCH_FAILED"
  | "RECORDED";

export type CancelReason =
  "NO_ANSWER" | "WRONG_NUMBER" | "CALL_DROPPED" | "POOR_QUALITY" | "CONSENT_REFUSED" | "OTHER";

export const CANCEL_REASONS: Record<CancelReason, string> = {
  NO_ANSWER: "No answer",
  WRONG_NUMBER: "Wrong number",
  CALL_DROPPED: "Call dropped",
  POOR_QUALITY: "Poor line quality",
  CONSENT_REFUSED: "Consent refused",
  OTHER: "Other (explain in the note)",
};

export const CALL_STATE_LABELS: Record<CallState, string> = {
  DIALLING: "On the call",
  DIAL_FAILED: "Call could not be placed",
  CANCELLED: "Cancelled",
  WAITING_FOR_RECORDING: "Fetching the recording",
  NEEDS_MATCH: "Needs a person to pick the recording",
  FETCH_FAILED: "Recording could not be fetched",
  RECORDED: "Recording stored",
};

/** What the moderator confirms while on the call. The first two are needed to close it. */
export type ChecklistItem = "A_JOINED" | "B_JOINED" | "MODERATOR_MUTED" | "QUALITY_OK";
export const CHECKLIST: readonly { item: ChecklistItem; label: string; required: boolean }[] = [
  { item: "A_JOINED", label: "Participant A is on the call", required: true },
  { item: "B_JOINED", label: "Participant B is on the call", required: true },
  { item: "MODERATOR_MUTED", label: "I am muted and listening", required: false },
  { item: "QUALITY_OK", label: "Both voices are clear", required: false },
];

export interface Candidate {
  /** Sent back to choose this call; the provider's own names below are shown masked. */
  key: string;
  session_id: string;
  start: string | null;
  duration: string;
  from_hint: string;
  to_hint: string;
  file: string;
}

export interface CallEvent {
  at: string;
  kind: string;
  actor: string | null;
  text: string;
}

export interface Call {
  id: string;
  task_id: string;
  provider: string;
  state: CallState;
  agent_id: string;
  phone_hint: string;
  moderator_id: string;
  moderator_name: string | null;
  dialled_at: string;
  closed_at: string | null;
  cancel_reason: CancelReason | null;
  note: string;
  provider_reference?: string | null;
  provider_session_id: string | null;
  recording_id: string | null;
  fetch_attempts: number;
  next_fetch_at: string | null;
  failure_code: string | null;
  failure_detail: string | null;
  /** Checklist items ticked, each with the time. */
  checklist: Partial<Record<ChecklistItem, string>>;
  candidates: Candidate[];
  events: CallEvent[];
}

export interface TelephonyStatus {
  configured: boolean;
  provider: string;
}

export const telephonyStatus = () => apiRequest<TelephonyStatus>("/api/v1/telephony/status");
export const listCalls = (taskId: string) => apiRequest<Call[]>(`/api/v1/tasks/${taskId}/calls`);
export const startCall = (taskId: string) =>
  apiRequest<Call>(`/api/v1/tasks/${taskId}/calls`, { method: "POST" });
export const tickChecklist = (id: string, item: ChecklistItem, done: boolean) =>
  apiRequest<Call>(`/api/v1/calls/${id}/checklist`, { method: "POST", body: { item, done } });
export const closeCall = (id: string, note: string) =>
  apiRequest<Call>(`/api/v1/calls/${id}/close`, { method: "POST", body: { note } });
export const cancelCall = (id: string, reason: CancelReason, note: string) =>
  apiRequest<Call>(`/api/v1/calls/${id}/cancel`, { method: "POST", body: { reason, note } });
export const chooseMatch = (id: string, key: string) =>
  apiRequest<Call>(`/api/v1/calls/${id}/match`, { method: "POST", body: { key } });
export const retryCall = (id: string) =>
  apiRequest<Call>(`/api/v1/calls/${id}/retry`, { method: "POST" });
export const setAgentSeat = (userId: string, agentId: string) =>
  apiRequest<{ user_id: string; telephony_agent_id: string | null }>(
    `/api/v1/users/${userId}/telephony-agent`,
    { method: "PUT", body: { agent_id: agentId } },
  );

/** States in which the call still moves without anyone clicking: the page keeps refreshing. */
export const MOVING: readonly CallState[] = ["DIALLING", "WAITING_FOR_RECORDING"];
/** States a person can still end by cancelling. */
export const CANCELLABLE: readonly CallState[] = [
  "DIALLING",
  "WAITING_FOR_RECORDING",
  "NEEDS_MATCH",
  "FETCH_FAILED",
];

// ------------------------------------------------------------- analytics (D-102, D-103)

export interface CallDay {
  day: string;
  calls: number;
  recorded: number;
  failed: number;
  open: number;
  recorded_minutes: number;
}

export interface ModeratorCalls {
  moderator_id: string;
  name: string;
  calls: number;
  recorded: number;
  failed: number;
  recorded_minutes: number;
  avg_call_minutes: number | null;
}

export interface ProjectCalls {
  project_id: string;
  code: string;
  name: string;
  calls: number;
  recorded: number;
  failed: number;
  recorded_minutes: number;
}

export interface CallFunnel {
  dialled: number;
  accepted: number;
  closed: number;
  recorded: number;
  sent_to_qc: number;
  approved: number;
}

export interface CallAnalytics {
  days: number;
  truncated: boolean;
  calls: number;
  in_call: number;
  stale_calls: number;
  recorded: number;
  dial_failed: number;
  cancelled: number;
  waiting_for_recording: number;
  needs_person: number;
  success_pct: number | null;
  avg_call_minutes: number | null;
  avg_fetch_minutes: number | null;
  recorded_minutes: number;
  today_recorded_minutes: number;
  /** The projects' telephony target for a day; null for people who see only their own calls. */
  target_minutes_per_day: number | null;
  funnel: CallFunnel;
  tasks_called: number;
  tasks_called_again: number;
  calls_per_task: number | null;
  tasks_by_status: Record<string, number>;
  tasks_not_called: number;
  automatic_checks: Record<string, number>;
  qc_decisions: Record<string, number>;
  checklist: Record<string, number>;
  by_day: CallDay[];
  by_hour: number[];
  by_moderator: ModeratorCalls[];
  by_project: ProjectCalls[];
  cancel_reasons: Record<string, number>;
  problems: Record<string, number>;
}

export interface CallListItem {
  id: string;
  task_id: string;
  task_code: string;
  project_code: string;
  state: CallState;
  /** Still "on the call" long after any call can last: left open. */
  stale: boolean;
  agent_id: string;
  phone_hint: string;
  moderator_name: string;
  dialled_at: string;
  closed_at: string | null;
  cancel_reason: CancelReason | null;
  failure_code: string | null;
  recording_id: string | null;
  recording_seconds: number | null;
}

export interface CallPage {
  items: CallListItem[];
  total: number;
  page: number;
  page_size: number;
}

export interface ProviderTraffic {
  available: boolean;
  message: string;
  first_day: string;
  last_day: string;
  data: unknown;
}

const qs = (params: Record<string, string | number | undefined>) => {
  const parts = Object.entries(params).filter(([, v]) => v !== undefined && v !== "");
  return parts.length
    ? `?${parts.map(([k, v]) => `${k}=${encodeURIComponent(String(v))}`).join("&")}`
    : "";
};

export const callAnalytics = (params: { project_id?: string | undefined; days: number }) =>
  apiRequest<CallAnalytics>(`/api/v1/telephony/analytics${qs(params)}`);
export const listAllCalls = (params: {
  project_id?: string | undefined;
  state?: string | undefined;
  page: number;
  page_size: number;
}) => apiRequest<CallPage>(`/api/v1/calls${qs(params)}`);
export const providerTraffic = (days: number) =>
  apiRequest<ProviderTraffic>(`/api/v1/telephony/provider-traffic${qs({ days })}`);
/** Every call of the period as a spreadsheet file. */
export const downloadCallsCsv = (params: { project_id?: string | undefined; days: number }) =>
  apiDownload(`/api/v1/calls/export${qs(params)}`, "phone_calls.csv");

export const FAILURE_LABELS: Record<string, string> = {
  PROVIDER_REFUSED: "TxContact refused the call",
  PROVIDER_UNREACHABLE: "TxContact did not answer",
  PHONE_NOT_SUPPORTED: "Number cannot be called",
  SEVERAL_CALLS: "Several TxContact calls fit",
  NUMBER_NOT_CONFIRMED: "Number not shown by TxContact",
  RECORDING_NOT_FOUND: "Recording not found",
  SEARCH_FAILED: "TxContact could not be searched",
  DOWNLOAD_FAILED: "Download failed",
  UNREADABLE_AUDIO: "File is not readable audio",
  SESSION_GONE: "Chosen call no longer listed",
  UNEXPECTED_ERROR: "Unexpected problem",
};

export const AUTOMATIC_CHECK_LABELS: Record<string, string> = {
  PASS: "All checks passed",
  NEEDS_REVIEW: "Listen and decide",
  FAIL: "Failed a check",
};
export const QC_DECISION_LABELS: Record<string, string> = {
  PASS: "Passed",
  FAIL: "Rejected",
  RETURN: "Returned",
};
