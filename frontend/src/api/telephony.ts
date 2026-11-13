// Phone calls through TxContact (D-101): start, close, cancel, pick the right recording, retry.
import { apiRequest } from "./client";

export type CallState =
  | "DIALLING"
  | "DIAL_FAILED"
  | "CANCELLED"
  | "WAITING_FOR_RECORDING"
  | "NEEDS_MATCH"
  | "FETCH_FAILED"
  | "RECORDED";

export type CancelReason =
  "NO_ANSWER" | "WRONG_NUMBER" | "CALL_DROPPED" | "CONSENT_REFUSED" | "OTHER";

export const CANCEL_REASONS: Record<CancelReason, string> = {
  NO_ANSWER: "No answer",
  WRONG_NUMBER: "Wrong number",
  CALL_DROPPED: "Call dropped",
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

export interface Candidate {
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
export const closeCall = (id: string, note: string) =>
  apiRequest<Call>(`/api/v1/calls/${id}/close`, { method: "POST", body: { note } });
export const cancelCall = (id: string, reason: CancelReason, note: string) =>
  apiRequest<Call>(`/api/v1/calls/${id}/cancel`, { method: "POST", body: { reason, note } });
export const chooseMatch = (id: string, sessionId: string) =>
  apiRequest<Call>(`/api/v1/calls/${id}/match`, {
    method: "POST",
    body: { session_id: sessionId },
  });
export const retryCall = (id: string) =>
  apiRequest<Call>(`/api/v1/calls/${id}/retry`, { method: "POST" });
export const setAgentSeat = (userId: string, agentId: string) =>
  apiRequest<{ user_id: string; telephony_agent_id: string | null }>(
    `/api/v1/users/${userId}/telephony-agent`,
    { method: "PUT", body: { agent_id: agentId } },
  );

/** States in which the call still moves without anyone clicking: the page keeps refreshing. */
export const MOVING: readonly CallState[] = ["DIALLING", "WAITING_FOR_RECORDING"];

// ------------------------------------------------------------------ analytics (D-102)

export interface CallDay {
  day: string;
  calls: number;
  recorded: number;
  failed: number;
  open: number;
}

export interface ModeratorCalls {
  moderator_id: string;
  name: string;
  calls: number;
  recorded: number;
  failed: number;
  avg_call_minutes: number | null;
}

export interface CallAnalytics {
  days: number;
  calls: number;
  in_call: number;
  recorded: number;
  dial_failed: number;
  cancelled: number;
  waiting_for_recording: number;
  needs_person: number;
  success_pct: number | null;
  avg_call_minutes: number | null;
  avg_fetch_minutes: number | null;
  recorded_minutes: number;
  by_day: CallDay[];
  by_hour: number[];
  by_moderator: ModeratorCalls[];
  cancel_reasons: Record<string, number>;
  problems: Record<string, number>;
}

export interface CallListItem {
  id: string;
  task_id: string;
  task_code: string;
  project_code: string;
  state: CallState;
  agent_id: string;
  phone_hint: string;
  moderator_name: string;
  dialled_at: string;
  closed_at: string | null;
  cancel_reason: CancelReason | null;
  failure_code: string | null;
  recording_id: string | null;
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

export const FAILURE_LABELS: Record<string, string> = {
  PROVIDER_REFUSED: "TxContact refused the call",
  PROVIDER_UNREACHABLE: "TxContact could not be reached",
  SEVERAL_CALLS: "Several TxContact calls fit",
  NUMBER_NOT_CONFIRMED: "Number not shown by TxContact",
  RECORDING_NOT_FOUND: "Recording not found",
  DOWNLOAD_FAILED: "Download failed",
  SESSION_GONE: "Chosen call no longer listed",
};
