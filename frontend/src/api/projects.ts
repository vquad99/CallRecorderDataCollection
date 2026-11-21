import { apiRequest, query, type Page } from "./client";

export type ProjectStatus = "DRAFT" | "ACTIVE" | "PAUSED" | "COMPLETED" | "ARCHIVED";
export type Mode = "TELEPHONY" | "FACE_TO_FACE";
/** How participants give consent (D-144): ONLINE on their personal page, or UPLOAD, a scanned
 * signed form that staff upload. */
export type ConsentMode = "ONLINE" | "UPLOAD";

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

/** What the project's Overview form edits. */
export interface ProjectSettings {
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

/** One question of the QC checklist (D-146). `fails_on`: the answer that fails the recording;
 * null = an observation, recorded and never failing. */
export interface ChecklistItem {
  key: string;
  question: string;
  scope: "conversation" | "speaker";
  fails_on: "yes" | "no" | null;
  required: boolean;
}

/** What the project's Rules tab edits (D-145). Every client rule is the project's own setting;
 * a new project starts with the server's defaults. */
export interface ProjectRules {
  /** The ages the project takes (any person is 1 to 120); 20 and 60 at the start. */
  speaker_min_age: number;
  speaker_max_age: number;
  /** The speaker details a person needs before a task (names from lib/speakers SPEAKER_FIELDS);
   * all of them at the start. */
  required_speaker_details: string[];
  /** At most this many conversations per speaker in the project; null = no limit (D-143). */
  max_conversations_per_speaker: number | null;
  /** The same two speakers never share a second task (D-143). */
  unique_pairs: boolean;
  /** Consent online, or a scanned signed form uploaded by staff (D-144). */
  consent_mode: ConsentMode;
  /** A QC pass approves the task, with no admin review (D-138). */
  qc_final_approval: boolean;
  /** What the QC Executive answers Yes or No for each recording (D-146); the first client's list
   * at the start. */
  qc_checklist: ChecklistItem[];
}

/** Everything the project's PATCH takes: a field left out would go back to its default, so the
 * Overview and Rules tabs each send the other's part as it is. */
export type ProjectFields = ProjectSettings & ProjectRules;

export interface Project extends ProjectSummary, ProjectFields {
  status_reason: string | null;
  status_changed_at: string | null;
  languages: Language[];
  audio_rules: AudioRule[];
  retention_rules: RetentionRule[];
  accepts_new_work: boolean;
}

export const projectSettings = (p: Project): ProjectSettings => ({
  name: p.name,
  description: p.description,
  allows_telephony: p.allows_telephony,
  allows_face_to_face: p.allows_face_to_face,
  target_telephony_hours_per_day: p.target_telephony_hours_per_day,
  target_face_to_face_hours_per_day: p.target_face_to_face_hours_per_day,
  phone_visibility_policy: p.phone_visibility_policy,
  consent_policy_version: p.consent_policy_version,
  consent_text: p.consent_text,
});

export const projectRules = (p: Project): ProjectRules => ({
  speaker_min_age: p.speaker_min_age,
  speaker_max_age: p.speaker_max_age,
  required_speaker_details: p.required_speaker_details,
  max_conversations_per_speaker: p.max_conversations_per_speaker,
  unique_pairs: p.unique_pairs,
  consent_mode: p.consent_mode,
  qc_final_approval: p.qc_final_approval,
  qc_checklist: p.qc_checklist,
});

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

/** Moves that need a reason in words: archiving an active or paused project, and reopening a
 * completed or archived one (mirrors the backend, which still decides). */
export const needsStatusReason = (from: ProjectStatus, to: ProjectStatus) =>
  (to === "ARCHIVED" && (from === "ACTIVE" || from === "PAUSED")) ||
  (to === "ACTIVE" && (from === "COMPLETED" || from === "ARCHIVED"));

const base = (id: string) => `/api/v1/projects/${id}`;

export const listProjects = (params: Record<string, string | number | undefined>) =>
  apiRequest<Page<ProjectSummary>>(`/api/v1/projects${query(params)}`);
export const getProject = (id: string) => apiRequest<Project>(base(id));
/** A new project gets the server's default rules unless they are given (D-145). */
export const createProject = (body: ProjectSettings & Partial<ProjectRules> & { code?: string }) =>
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
