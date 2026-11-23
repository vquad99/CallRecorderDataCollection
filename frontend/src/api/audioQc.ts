// Audio quality check of a task's recording (D-079): the automatic result, the QC Executive's
// decision with the QC checklist's answers (D-146), assignment and a re-check from storage.
import { apiRequest, seg } from "./client";
import type { ChecklistItem } from "./projects";

export type QcOutcome = "PASS" | "NEEDS_REVIEW" | "FAIL" | "SEND_BACK_CONSENT";
export type CheckState = "PASS" | "FAIL" | "REVIEW" | "INFO" | "NOT_APPLICABLE";
/** Pass, Reject, or (projects that take signed forms) Send back for consent (D-146). */
export type Decision = "PASS" | "FAIL" | "SEND_BACK_CONSENT";
export type Answer = "yes" | "no";
export type Side = "A" | "B";

/** QC checklist answers (D-146): a question left out is not answered. */
export interface Answers {
  conversation: Record<string, Answer>;
  speakers: Partial<Record<Side, Record<string, Answer>>>;
  consent: Partial<Record<Side, Answer>>;
}

/** A decision's answers as given, with the questions as they read then, who and when. */
export interface RecordedAnswers {
  outcome: QcOutcome;
  reason_code: string | null;
  comment: string;
  reviewer_name: string | null;
  decided_at: string;
  items: ChecklistItem[];
  consent_check: boolean;
  conversation: Record<string, Answer>;
  participants: {
    side: Side;
    participant_id: string;
    participant_code: string;
    answers: Record<string, Answer>;
    consent: Answer | null;
    consent_form_id: string | null;
  }[];
  failing: { key: string; side: Side | null; answer: Answer }[];
}

export interface DraftAnswers {
  answers: Answers;
  saved_at: string;
  saved_by_name: string | null;
}

/** The QC checklist of a task (D-146). */
export interface ChecklistView {
  /** The project's checklist now. */
  items: ChecklistItem[];
  /** The project takes signed consent forms: QC checks each one. */
  consent_check: boolean;
  consent_question: string;
  /** The caller decides this task's QC and it waits for the decision. */
  can_answer: boolean;
  /** Answers not yet sent, for the person who decides. */
  draft: DraftAnswers | null;
  /** The newest decision's answers. */
  latest: RecordedAnswers | null;
}

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
  /** A pass approves the task: the project has no admin review (D-138). */
  pass_approves: boolean;
  qc_user_id: string | null;
  qc_name: string | null;
  can_decide: boolean;
  can_assign: boolean;
  can_recheck: boolean;
  reasons: Record<"FAIL", string[]>;
  results: QcResult[];
}

const base = (taskId: string) => `/api/v1/tasks/${seg(taskId)}`;

export const getAudioQc = (taskId: string) => apiRequest<AudioQcView>(`${base(taskId)}/audio-qc`);
export const assignQc = (taskId: string, userId: string, reason: string) =>
  apiRequest<AudioQcView>(`${base(taskId)}/assign-qc`, {
    method: "POST",
    body: { user_id: userId, reason: reason || null },
  });
export const decideQc = (
  taskId: string,
  outcome: Decision,
  reasonCode: string,
  comment: string,
  answers?: Answers,
) =>
  apiRequest<AudioQcView>(`${base(taskId)}/audio-qc/decision`, {
    method: "POST",
    body: { outcome, reason_code: reasonCode || null, comment, ...(answers ? { answers } : {}) },
  });
export const getChecklist = (taskId: string) =>
  apiRequest<ChecklistView>(`${base(taskId)}/audio-qc/checklist`);
export const saveDraft = (taskId: string, answers: Answers) =>
  apiRequest<DraftAnswers>(`${base(taskId)}/audio-qc/draft`, { method: "PUT", body: answers });
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
  // D-148: silences inside the speech longer than the project's limit.
  PAUSES: "Long pauses",
  SNR: "Signal to noise",
  CHANNEL_LEAKAGE: "Channel separation",
  DUPLICATE: "Duplicate",
};

export const OUTCOME_LABELS: Record<QcOutcome, string> = {
  PASS: "Passed",
  NEEDS_REVIEW: "Listen and decide",
  FAIL: "Failed",
  SEND_BACK_CONSENT: "Sent back for its consent form",
};

export const STATE_LABELS: Record<CheckState, string> = {
  PASS: "Pass",
  FAIL: "Fail",
  REVIEW: "Listen",
  INFO: "Shown",
  NOT_APPLICABLE: "Not used",
};
