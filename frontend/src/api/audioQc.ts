// Audio quality check of a task's recording (D-079): the automatic result, the QC Executive's
// decision, assignment and a re-check from storage.
import { apiRequest } from "./client";

export type QcOutcome = "PASS" | "NEEDS_REVIEW" | "FAIL" | "RETURN";
export type CheckState = "PASS" | "FAIL" | "REVIEW" | "INFO" | "NOT_APPLICABLE";
export type Decision = "PASS" | "FAIL" | "RETURN";

export interface QcCheck {
  code: string;
  state: CheckState;
  measured: string;
  expected: string;
  message: string;
}

export interface QcResult {
  id: string;
  recording_id: string;
  asset_id: string | null;
  automated: boolean;
  outcome: QcOutcome;
  reason_code: string | null;
  comment: string;
  reviewer_name: string | null;
  created_at: string;
  duration_ms: number | null;
  silence_pct: number | null;
  clip_pct: number | null;
  peak_dbfs: number | null;
  rms_dbfs: number | null;
  dynamic_range_db: number | null;
  duplicate_of_recording_id: string | null;
  checks: QcCheck[];
}

export interface AudioQcView {
  task_status: string;
  qc_user_id: string | null;
  qc_name: string | null;
  can_decide: boolean;
  can_assign: boolean;
  can_recheck: boolean;
  reasons: Record<"FAIL" | "RETURN", string[]>;
  results: QcResult[];
}

const base = (taskId: string) => `/api/v1/tasks/${taskId}`;

export const getAudioQc = (taskId: string) => apiRequest<AudioQcView>(`${base(taskId)}/audio-qc`);
export const assignQc = (taskId: string, userId: string, reason: string) =>
  apiRequest<AudioQcView>(`${base(taskId)}/assign-qc`, {
    method: "POST",
    body: { user_id: userId, reason: reason || null },
  });
export const decideQc = (taskId: string, outcome: Decision, reasonCode: string, comment: string) =>
  apiRequest<AudioQcView>(`${base(taskId)}/audio-qc/decision`, {
    method: "POST",
    body: { outcome, reason_code: reasonCode || null, comment },
  });
export const recheckQc = (taskId: string) =>
  apiRequest<AudioQcView>(`${base(taskId)}/audio-qc/recheck`, { method: "POST" });

export const CHECK_LABELS: Record<string, string> = {
  AUDIO_PRESENT: "Audio file",
  DECODES: "File reads",
  CHECKSUM: "File fingerprint",
  FORMAT: "Format",
  FILE_SIZE: "File size",
  PROJECT_RULE: "Project rule",
  SAMPLE_RATE: "Sample rate",
  BIT_DEPTH: "Bit depth",
  CHANNELS: "Channels",
  DURATION: "Length",
  SIGNAL: "Sound present",
  SILENCE: "Silence",
  CLIPPING: "Clipping",
  LEVELS: "Loudness",
  DYNAMIC_RANGE: "Dynamic range",
  SNR: "Signal to noise",
  CHANNEL_LEAKAGE: "Channel separation",
  DUPLICATE: "Duplicate",
};

export const OUTCOME_LABELS: Record<QcOutcome, string> = {
  PASS: "Passed",
  NEEDS_REVIEW: "Listen and decide",
  FAIL: "Failed",
  RETURN: "Returned",
};

export const STATE_LABELS: Record<CheckState, string> = {
  PASS: "Pass",
  FAIL: "Fail",
  REVIEW: "Listen",
  INFO: "Shown",
  NOT_APPLICABLE: "Not used",
};
