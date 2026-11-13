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
