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
}

export interface Consent {
  id: string;
  task_id: string | null;
  status: "GIVEN" | "REFUSED" | "WITHDRAWN";
  method: string;
  policy_version: string;
  captured_by: string;
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
