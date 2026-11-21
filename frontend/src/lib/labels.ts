// Words for the codes the server sends, in one place, so a code never reaches the screen as
// "AUDIO_QUALITY" or "audio quality" and every page says the same thing.
import type { Tone } from "../components/StatusBadge";

export type TaskStatus =
  | "DRAFT"
  | "ASSIGNED"
  | "IN_PROGRESS"
  | "RECORDED"
  | "AUDIO_QC"
  | "ADMIN_REVIEW"
  | "APPROVED"
  | "REJECTED"
  | "CANCELLED"
  | "ON_HOLD";

export const TASK_STATUS_LABELS: Record<TaskStatus, string> = {
  DRAFT: "Draft",
  ASSIGNED: "Assigned",
  IN_PROGRESS: "In progress",
  RECORDED: "Recorded",
  AUDIO_QC: "Audio QC",
  ADMIN_REVIEW: "Admin review",
  APPROVED: "Approved",
  REJECTED: "Rejected",
  CANCELLED: "Cancelled",
  ON_HOLD: "On hold",
};

export const PROJECT_STATUS_LABELS: Record<string, string> = {
  DRAFT: "Draft",
  ACTIVE: "Active",
  PAUSED: "Paused",
  COMPLETED: "Completed",
  ARCHIVED: "Archived",
};

/** One wording for the two ways of recording, everywhere (filters, tables, forms). */
export const MODE_LABELS = {
  TELEPHONY: "Phone call",
  FACE_TO_FACE: "Face-to-face",
} as const satisfies Record<string, string>;

export const PRIORITY_LABELS: Record<string, string> = {
  LOW: "Low",
  NORMAL: "Normal",
  HIGH: "High",
  URGENT: "Urgent",
};

/** Reasons for putting a task on hold, cancelling or rejecting it (the server's fixed lists). */
export const REASON_LABELS: Record<string, string> = {
  WAITING_FOR_PARTICIPANT: "Waiting for a participant",
  TECHNICAL_PROBLEM: "Technical problem",
  CLIENT_REQUEST: "The client asked",
  PARTICIPANT_UNAVAILABLE: "Participant not available",
  CONSENT_REFUSED: "Consent refused",
  DUPLICATE_TASK: "Task made twice",
  AUDIO_QUALITY: "Poor audio quality",
  CONSENT_PROBLEM: "Problem with the consent",
  WRONG_SPEAKERS: "Wrong speakers",
  OTHER: "Other (explain in the comment)",
};

/** How a consent was given: online on the participant's own page, or (before D-129) noted by the
 * moderator for a session. */
export const CONSENT_METHOD_LABELS: Record<string, string> = {
  VERBAL_RECORDED: "Said yes on the recording",
  VERBAL_NOTED: "Said yes (noted by the moderator)",
  WRITTEN: "Signed a form",
  DIGITAL: "Agreed online",
};

/** A participant's consent: their answer (withdrawn only on answers from before D-129), or their
 * signed form uploaded where the project takes uploads (D-144). */
export const CONSENT_ANSWER: Record<string, { label: string; tone: Tone }> = {
  GIVEN: { label: "Agreed", tone: "success" },
  UPLOADED: { label: "Form uploaded", tone: "success" },
  REFUSED: { label: "Did not agree", tone: "danger" },
  WITHDRAWN: { label: "Withdrawn", tone: "warning" },
  NONE: { label: "No answer yet", tone: "neutral" },
};
/** Nothing yet in a project that takes signed forms (D-144). */
export const FORM_MISSING = { label: "Consent form missing", tone: "warning" } as const;

/** The consent that lets a person be put on a task, called and recorded (D-129, D-144). */
export const consentCounts = (status: string | null | undefined) =>
  status === "GIVEN" || status === "UPLOADED";

/** The words for a code, or the code in plain words when no label is known yet. */
export function labelFor(labels: Record<string, string>, code: string | null | undefined): string {
  if (!code) return "-";
  const known = labels[code];
  if (known) return known;
  const text = code.toLowerCase().replace(/_/g, " ");
  return text.charAt(0).toUpperCase() + text.slice(1);
}

/** The chip for a consent status; null and unknown codes read "No answer yet", or "Consent form
 * missing" in a project that takes signed forms (`mode` UPLOAD, D-144). */
export function consentAnswer(
  status: string | null | undefined,
  mode?: string | null,
): { label: string; tone: Tone } {
  const known = CONSENT_ANSWER[status ?? "NONE"];
  if (mode === "UPLOAD" && (!known || status === "NONE" || !status)) return FORM_MISSING;
  return known ?? (CONSENT_ANSWER.NONE as { label: string; tone: Tone });
}

/** The server's reason codes for a choice list: code to words. */
export const reasonChoices = (codes: readonly string[] | undefined): Record<string, string> =>
  Object.fromEntries((codes ?? []).map((code) => [code, labelFor(REASON_LABELS, code)]));
