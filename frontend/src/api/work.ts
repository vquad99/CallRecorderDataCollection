// Participants, tasks and audit-log API calls (Phase 3).
import { query, type Page } from "./admin";
import { apiRequest } from "./client";

export interface Participant {
  id: string;
  participant_code: string;
  language_code: string;
  dialect: string;
  display_label: string | null;
  phone: string | null;
  has_phone: boolean;
  /** Whether this user may open the person's consent history (managers, assigned moderator). */
  consent_visible: boolean;
  email: string | null; // only for people who may see contact details
  has_email: boolean;
  /** The participant's own answer on the consent form; "NONE" = not answered yet. */
  consent_status: "GIVEN" | "REFUSED" | "WITHDRAWN" | "NONE" | null;
  consent_review: "PENDING" | "APPROVED" | "REJECTED" | null;
  link_active: boolean | null;
  notes: string | null;
  deleted: boolean;
  created_at: string;
}

export interface ParticipantFields {
  display_label: string;
  phone: string | null;
  language_code: string;
  dialect: string;
  notes: string;
  /** Not sent = keep the stored address; empty = remove it. */
  email?: string | undefined;
}

export interface Consent {
  id: string;
  task_id: string | null;
  status: "GIVEN" | "REFUSED" | "WITHDRAWN";
  method: string;
  policy_version: string;
  captured_by: string | null; // null: the participant answered the form themselves
  note: string;
  created_at: string;
}

export type TaskStatus =
  | "DRAFT"
  | "ASSIGNED"
  | "IN_PROGRESS"
  | "RECORDED"
  | "AUDIO_QC"
  | "APPROVED"
  | "REJECTED"
  | "RETURNED"
  | "CANCELLED"
  | "ON_HOLD";

export const TASK_STATUS_LABELS: Record<TaskStatus, string> = {
  DRAFT: "Draft",
  ASSIGNED: "Assigned",
  IN_PROGRESS: "In progress",
  RECORDED: "Recorded",
  AUDIO_QC: "Audio QC",
  APPROVED: "Approved",
  REJECTED: "Rejected",
  RETURNED: "Returned",
  CANCELLED: "Cancelled",
  ON_HOLD: "On hold",
};

export interface TaskSummary {
  id: string;
  task_code: string;
  project_id: string;
  recording_mode: "TELEPHONY" | "FACE_TO_FACE";
  status: TaskStatus;
  priority: "LOW" | "NORMAL" | "HIGH" | "URGENT";
  due_at: string | null;
  created_at: string;
}

export interface Party {
  id: string;
  participant_code: string;
  consent_status: string | null;
  consent_at: string | null;
}

export interface TaskDetail extends TaskSummary {
  held_from: TaskStatus | null;
  reason_code: string | null;
  participant_a: Party;
  participant_b: Party;
  moderator_id: string | null;
  moderator_name: string | null;
  allowed_transitions: TaskStatus[];
  reasons: Record<string, string[]>;
  can_assign: boolean;
  is_moderator: boolean;
}

export interface TimelineEntry {
  at: string;
  kind: "status" | "assignment" | "comment";
  actor: string | null;
  text: string;
}

export interface AuditEntry {
  id: string;
  created_at: string;
  actor_email: string | null;
  action: string;
  entity_type: string;
  entity_id: string | null;
  project_id: string | null;
  before: unknown;
  after: unknown;
  ip: string | null;
  request_id: string | null;
}

type Params = Record<string, string | number | undefined>;
const pp = (projectId: string) => `/api/v1/projects/${projectId}/participants`;

export const listParticipants = (projectId: string, params: Params) =>
  apiRequest<Page<Participant>>(`${pp(projectId)}${query(params)}`);
export const createParticipant = (projectId: string, body: ParticipantFields) =>
  apiRequest<Participant>(pp(projectId), { method: "POST", body });
export const correctParticipant = (projectId: string, id: string, body: ParticipantFields) =>
  apiRequest<Participant>(`${pp(projectId)}/${id}`, { method: "PATCH", body });
export const deleteParticipant = (projectId: string, id: string, reason: string) =>
  apiRequest<Participant>(`${pp(projectId)}/${id}/delete`, { method: "POST", body: { reason } });
export const consentHistory = (projectId: string, id: string) =>
  apiRequest<Consent[]>(`${pp(projectId)}/${id}/consent`);

export const listTasks = (params: Params) =>
  apiRequest<Page<TaskSummary>>(`/api/v1/tasks${query(params)}`);
export const getTask = (id: string) => apiRequest<TaskDetail>(`/api/v1/tasks/${id}`);
export const createTask = (body: {
  project_id: string;
  recording_mode: string;
  participant_a_id: string;
  participant_b_id: string;
  priority: string;
  due_at: string | null;
}) => apiRequest<TaskDetail>("/api/v1/tasks", { method: "POST", body });
export const assignModerator = (id: string, userId: string, reason: string) =>
  apiRequest<TaskDetail>(`/api/v1/tasks/${id}/assign`, {
    method: "POST",
    body: { user_id: userId, reason: reason || null },
  });
export const transitionTask = (id: string, to: TaskStatus, reasonCode: string, comment: string) =>
  apiRequest<TaskDetail>(`/api/v1/tasks/${id}/transition`, {
    method: "POST",
    body: { to, reason_code: reasonCode || null, comment },
  });
export const captureConsent = (id: string, participantId: string, status: string, method: string) =>
  apiRequest<TaskDetail>(`/api/v1/tasks/${id}/consent`, {
    method: "POST",
    body: { participant_id: participantId, status, method },
  });
export const addComment = (id: string, body: string) =>
  apiRequest<TimelineEntry>(`/api/v1/tasks/${id}/comments`, { method: "POST", body: { body } });
export const getTimeline = (id: string) =>
  apiRequest<TimelineEntry[]>(`/api/v1/tasks/${id}/timeline`);

export const listAudit = (params: Params) =>
  apiRequest<Page<AuditEntry>>(`/api/v1/audit-logs${query(params)}`);

export const createPortalLink = (projectId: string, participantId: string) =>
  apiRequest<{ url: string; expires_at: string }>(`${pp(projectId)}/${participantId}/portal-link`, {
    method: "POST",
  });
export const emailPortalLink = (projectId: string, participantId: string) =>
  apiRequest<{ sent: boolean; expires_at: string }>(
    `${pp(projectId)}/${participantId}/portal-link/email`,
    { method: "POST" },
  );

export interface ImportResult {
  rows: {
    line: number;
    name: string;
    ok: boolean;
    message: string;
    participant_code: string | null;
  }[];
  ready: number;
  created: number;
}
export const importParticipants = (projectId: string, csv: string, confirm: boolean) =>
  apiRequest<ImportResult>(`${pp(projectId)}/import`, { method: "POST", body: { csv, confirm } });

export interface BulkResult {
  results: { participant_id: string; participant_code: string; ok: boolean; message: string }[];
  done: number;
  failed: number;
}
export const bulkParticipants = (
  projectId: string,
  body: {
    action: "assign" | "remove" | "send_consent";
    participant_ids: string[];
    target_project_id?: string;
    reason?: string;
  },
) => apiRequest<BulkResult>(`${pp(projectId)}/bulk`, { method: "POST", body });
export const reviewConsent = (
  projectId: string,
  participantId: string,
  decision: "APPROVED" | "REJECTED",
  note = "",
) =>
  apiRequest<Consent>(`${pp(projectId)}/${participantId}/consent-review`, {
    method: "POST",
    body: { decision, note },
  });

export interface ConsentAnswer {
  status: "GIVEN" | "REFUSED" | "WITHDRAWN";
  answered_at: string;
  policy_version: string;
  review_status: "PENDING" | "APPROVED" | "REJECTED" | null;
  review_note: string;
  reviewed_at: string | null;
}
export interface ConsentFormView {
  participant_code: string;
  project_code: string;
  project_name: string;
  form_text: string;
  form_version: string;
  answered: boolean;
  current: ConsentAnswer | null;
  earlier: ConsentAnswer[];
}
export const consentForm = (projectId: string, participantId: string) =>
  apiRequest<ConsentFormView>(`${pp(projectId)}/${participantId}/consent-form`);
export const consentFormFileUrl = (projectId: string, participantId: string) =>
  `${pp(projectId)}/${participantId}/consent-form/file`;
