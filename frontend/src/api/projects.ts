import { apiRequest } from "./client";
import { query, type Page } from "./admin";

export type ProjectStatus = "DRAFT" | "ACTIVE" | "PAUSED" | "COMPLETED" | "ARCHIVED";
export type Mode = "TELEPHONY" | "FACE_TO_FACE";

export interface AudioRule {
  mode: Mode;
  sample_rate: number;
  bit_depth: 16 | 24 | 32;
  channels: 1 | 2;
  max_silence_pct: string;
  max_clipping_pct: string | null;
  min_duration_seconds: number;
  max_duration_seconds: number | null;
}

export interface Language {
  language_code: string;
  dialect: string;
}

export interface RetentionRule {
  asset_kind: string;
  retain_days: number;
}

export interface ProjectSummary {
  id: string;
  code: string;
  name: string;
  status: ProjectStatus;
  allows_telephony: boolean;
  allows_face_to_face: boolean;
  target_telephony_hours_per_day: string;
  target_face_to_face_hours_per_day: string;
  created_at: string;
}

export interface Project extends ProjectSummary {
  description: string;
  phone_visibility_policy: "ADMINS_ONLY" | "ASSIGNED_MODERATOR";
  consent_policy_version: string;
  consent_text: string;
  status_reason: string | null;
  status_changed_at: string | null;
  languages: Language[];
  audio_rules: AudioRule[];
  retention_rules: RetentionRule[];
  accepts_new_work: boolean;
}

export interface ProjectFields {
  name: string;
  description: string;
  allows_telephony: boolean;
  allows_face_to_face: boolean;
  target_telephony_hours_per_day: string;
  target_face_to_face_hours_per_day: string;
  phone_visibility_policy: "ADMINS_ONLY" | "ASSIGNED_MODERATOR";
  consent_policy_version: string;
  consent_text: string;
}

export interface Member {
  user_id: string;
  email: string | null; // shown only to people who manage the team
  display_name: string;
  roles: string[];
  status: string;
  added_at: string;
}

export interface Candidate {
  user_id: string;
  email: string;
  display_name: string;
  roles: string[];
}

export const ASSET_KINDS = [
  "PROVIDER_ORIGINAL_TRACK",
  "PROVIDER_ORIGINAL_MIXED",
  "TELEPHONY_FINAL_STEREO",
  "CONSENT_RECORDING",
  "BROWSER_ORIGINAL",
  "FTF_DERIVED_PCM",
  "TELEPHONY_DERIVED_PCM",
  "TRANSCRIPT_FILE",
  "EXPORT_PACKAGE",
] as const;

/** Allowed next statuses, mirroring the backend rule (the backend still decides). */
export const NEXT_STATUSES: Record<ProjectStatus, ProjectStatus[]> = {
  DRAFT: ["ACTIVE", "ARCHIVED"],
  ACTIVE: ["PAUSED", "COMPLETED", "ARCHIVED"],
  PAUSED: ["ACTIVE", "ARCHIVED"],
  COMPLETED: ["ACTIVE", "ARCHIVED"],
  ARCHIVED: ["ACTIVE"],
};

const base = (id: string) => `/api/v1/projects/${id}`;

export const listProjects = (params: Record<string, string | number | undefined>) =>
  apiRequest<Page<ProjectSummary>>(`/api/v1/projects${query(params)}`);
export const getProject = (id: string) => apiRequest<Project>(base(id));
export const createProject = (body: ProjectFields & { code?: string }) =>
  apiRequest<Project>("/api/v1/projects", { method: "POST", body });
export const updateProject = (id: string, body: ProjectFields) =>
  apiRequest<Project>(base(id), { method: "PATCH", body });
export const changeProjectStatus = (id: string, status: ProjectStatus, reason: string) =>
  apiRequest<Project>(`${base(id)}/status`, {
    method: "POST",
    body: { status, reason: reason || null },
  });
export const setLanguages = (id: string, languages: Language[]) =>
  apiRequest<Project>(`${base(id)}/languages`, { method: "PUT", body: { languages } });
export const setAudioRules = (id: string, rules: AudioRule[]) =>
  apiRequest<Project>(`${base(id)}/audio-rules`, { method: "PUT", body: { rules } });
export const setRetention = (id: string, rules: RetentionRule[]) =>
  apiRequest<Project>(`${base(id)}/retention`, { method: "PUT", body: { rules } });
export const listMembers = (id: string) => apiRequest<Member[]>(`${base(id)}/members`);

export type BundleContent = "audio" | "metadata" | "both";
export type ReportContent = "progress" | "participants";
export type ExportScope = "approved" | "finished";
export type TableFormat = "csv" | "tsv";
export type ExportState = "QUEUED" | "RUNNING" | "READY" | "FAILED" | "EXPIRED";
/** What goes into a bundle of recordings (D-105). */
export interface ExportChoice {
  content: BundleContent;
  scope: ExportScope;
  table_format: TableFormat;
  mode: "FACE_TO_FACE" | "TELEPHONY" | null;
  language: string | null;
  recorded_from: string | null; // YYYY-MM-DD, counted in India Standard Time
  recorded_to: string | null;
  originals: boolean; // what was recorded before processing; project managers only
  contact: boolean; // names, phone numbers, email addresses; needs participants.export
}
export interface ExportSummary {
  recordings: number;
  face_to_face: number;
  telephony: number;
  audio_bytes: number;
  file_name: string;
}
export interface ExportJob {
  id: string;
  state: ExportState;
  content: BundleContent;
  scope: ExportScope;
  table_format: TableFormat;
  filters: Partial<ExportChoice>;
  file_name: string;
  recordings: number;
  files: number;
  size_bytes: number;
  sha256: string | null;
  error: string | null;
  requested_by: string | null;
  created_at: string;
  finished_at: string | null;
  expires_at: string | null;
  downloads: number;
  last_downloaded_at: string | null;
}
/** What a bundle would hold, before asking for it. */
export const exportSummary = (id: string, choice: ExportChoice) =>
  apiRequest<ExportSummary>(
    `${base(id)}/export/summary${query({
      content: choice.content,
      scope: choice.scope,
      mode: choice.mode ?? undefined,
      language: choice.language ?? undefined,
      recorded_from: choice.recorded_from ?? undefined,
      recorded_to: choice.recorded_to ?? undefined,
      originals: choice.originals ? "true" : undefined,
    })}`,
  );
/** A report is a plain link: one table, as CSV or TSV. */
export const reportPath = (id: string, content: ReportContent, format: TableFormat) =>
  `${base(id)}/export${query({ content, format })}`;
/** Ask for a bundle; it is prepared in the background and appears in the list of exports. */
export const requestExport = (id: string, choice: ExportChoice) =>
  apiRequest<ExportJob>(`${base(id)}/exports`, { method: "POST", body: choice });
export const listExports = (id: string) =>
  apiRequest<Page<ExportJob>>(`${base(id)}/exports${query({ page_size: 20 })}`);
/** A link to a prepared bundle that works for a few minutes; every link is audited. */
export const exportLink = (id: string, jobId: string) =>
  apiRequest<{ url: string; valid_seconds: number; file_name: string; sha256: string | null }>(
    `${base(id)}/exports/${jobId}/download-link`,
    { method: "POST" },
  );
export const removeExport = (id: string, jobId: string) =>
  apiRequest<ExportJob>(`${base(id)}/exports/${jobId}`, { method: "DELETE" });
export const listCandidates = (id: string, search: string) =>
  apiRequest<Candidate[]>(`${base(id)}/member-candidates${query({ search })}`);
export const addMember = (id: string, userId: string) =>
  apiRequest<null>(`${base(id)}/members`, { method: "POST", body: { user_id: userId } });
export const removeMember = (id: string, userId: string) =>
  apiRequest<null>(`${base(id)}/members/${userId}`, { method: "DELETE" });
