// Phone calls through TxContact (D-101, D-102, D-103): start, checklist, close, cancel, pick the
// right recording, retry; and the figures, list and spreadsheet of calls.
import { apiDownload, apiRequest, query, type Page } from "./client";

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

/** What the moderator says happened on the call ("A answered", "B answered", D-127); both are
 * needed to close it. Older calls may also carry the two checks that were dropped. */
export type ChecklistItem = "A_JOINED" | "B_JOINED" | "MODERATOR_MUTED" | "QUALITY_OK";

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
  /** Participant B rung into the call by the platform (D-111). */
  b_dial_attempts?: number;
  b_dialled_at?: string | null;
  b_dial_status?: "ACCEPTED" | "REFUSED" | "UNREACHABLE" | null;
  b_phone_hint?: string | null;
  /** The conversation as the moderator marked it (D-113). */
  record_started_at?: string | null;
  record_stopped_at?: string | null;
  candidates: Candidate[];
  events: CallEvent[];
}

/** How the signed-in person's page signs their phone seat in to TxContact's agent manager
 * (D-133): its address, the tenant, their seat and the extension it signs in on. */
export interface SeatLogin {
  url: string;
  tenant_id: string;
  agent_id: string | null;
  extension: string | null;
  has_password: boolean;
}

export interface TelephonyStatus {
  configured: boolean;
  provider: string;
  /** Null (or missing): the seat is made Ready elsewhere, in TxContact's Chirp app. */
  seat_login?: SeatLogin | null;
}

export const telephonyStatus = () => apiRequest<TelephonyStatus>("/api/v1/telephony/status");
export const listCalls = (taskId: string) => apiRequest<Call[]>(`/api/v1/tasks/${taskId}/calls`);
export const startCall = (taskId: string) =>
  apiRequest<Call>(`/api/v1/tasks/${taskId}/calls`, { method: "POST" });
export const tickChecklist = (id: string, item: ChecklistItem, done: boolean) =>
  apiRequest<Call>(`/api/v1/calls/${id}/checklist`, { method: "POST", body: { item, done } });
/** Ring participant B into the call on the moderator's seat (D-111). */
export const callParticipantB = (id: string) =>
  apiRequest<Call>(`/api/v1/calls/${id}/call-b`, { method: "POST" });
/** Mark where the conversation starts or stops (D-113). */
export const markRecording = (id: string, step: "start" | "stop") =>
  apiRequest<Call>(`/api/v1/calls/${id}/recording/${step}`, { method: "POST" });
export const closeCall = (id: string, note: string) =>
  apiRequest<Call>(`/api/v1/calls/${id}/close`, { method: "POST", body: { note } });
export const cancelCall = (id: string, reason: CancelReason, note: string) =>
  apiRequest<Call>(`/api/v1/calls/${id}/cancel`, { method: "POST", body: { reason, note } });
export const chooseMatch = (id: string, key: string) =>
  apiRequest<Call>(`/api/v1/calls/${id}/match`, { method: "POST", body: { key } });
export const retryCall = (id: string) =>
  apiRequest<Call>(`/api/v1/calls/${id}/retry`, { method: "POST" });
/** A moderator's phone seat and whether its password is saved; the password itself is only in
 * a reveal (D-130). */
export interface AgentSeat {
  user_id: string;
  telephony_agent_id: string | null;
  has_password: boolean;
}
/** Save a user's phone seat. `password`: left out keeps the saved one (D-130). */
export const setAgentSeat = (userId: string, agentId: string, password?: string) =>
  apiRequest<AgentSeat>(`/api/v1/users/${userId}/telephony-agent`, {
    method: "PUT",
    body: { agent_id: agentId, ...(password ? { password } : {}) },
  });
/** The saved seat password of a user, for a Super Admin; each showing is audited (D-130). */
export const showSeatPassword = (userId: string) =>
  apiRequest<{ password: string }>(`/api/v1/users/${userId}/telephony-agent/password`);
/** The signed-in user's own seat password, shown on their account page (D-130) or taken by the
 * page to sign the seat in (`line`, D-133); each is audited. */
export const showOwnSeatPassword = (purpose?: "line") =>
  apiRequest<{ password: string }>(`/api/v1/auth/phone-seat/password${query({ purpose })}`);

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

export interface ProviderTraffic {
  available: boolean;
  message: string;
  first_day: string;
  last_day: string;
  data: unknown;
}

export const callAnalytics = (params: { project_id?: string | undefined; days: number }) =>
  apiRequest<CallAnalytics>(`/api/v1/telephony/analytics${query(params)}`);
export const listAllCalls = (params: {
  project_id?: string | undefined;
  state?: string | undefined;
  page: number;
  page_size: number;
}) => apiRequest<Page<CallListItem>>(`/api/v1/calls${query(params)}`);
export const providerTraffic = (days: number) =>
  apiRequest<ProviderTraffic>(`/api/v1/telephony/provider-traffic${query({ days })}`);
/** Every call of the period as a spreadsheet file. */
export const downloadCallsCsv = (params: { project_id?: string | undefined; days: number }) =>
  apiDownload(`/api/v1/calls/export${query(params)}`, "phone_calls.csv");

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
  SEND_BACK_CONSENT: "Sent back for its consent form",
};
