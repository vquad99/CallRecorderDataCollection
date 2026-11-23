// The project's Progress tab (D-148): completed minutes, conversations and speakers against the
// project's targets, and what is still needed to finish (D-153); and its download as Excel or
// CSV. Its own module, so only the Progress tab's chunk (and the Participants page's "Still
// needed" line) loads it (the first screen is near its budget).
import { apiRequest, seg } from "./client";
import type { ProgressCounts } from "./projects";

/** One row of a share on the Progress tab: actual count and percent, the target percent and the
 * variance (actual minus target, percentage points); no target for "Other" and "Not given". */
export interface ShareRow {
  key: string;
  label: string;
  count: number;
  percent: number;
  target_percent: number | null;
  variance: number | null;
}

export interface Share {
  /** What the percents are of: the speakers with an approved conversation, or the approved
   * conversations. */
  basis: "speakers" | "conversations";
  total: number;
  has_target: boolean;
  rows: ShareRow[];
}

/** Speakers wanted in one group, and how far it is (D-153). `registered`: people registered in the
 * project with no approved conversation yet. `still_needed`: target - done - registered, at least
 * 0 (a total adds up its groups'); null without a target. */
export interface Need {
  target: number | null;
  done: number;
  registered: number;
  still_needed: number | null;
}

/** One row of the age band x gender matrix: an age band, "Other ages", "Not given", "All ages"
 * (no age bands), or the total. */
export interface AgeGenderNeed {
  key: string;
  label: string;
  male: Need;
  female: Need;
  total: Need;
}

export interface DistrictNeed extends Need {
  key: string;
  label: string;
}

export interface ConversationNeed {
  /** ALL, then FACE_TO_FACE and TELEPHONY for a project made before D-153 that records both. */
  key: string;
  label: string;
  target: number | null;
  approved: number;
  /** Open tasks: not started, in progress, waiting for QC or approval. */
  in_pipeline: number;
  still_to_make: number | null;
}

/** What is still needed to reach the targets (D-153). */
export interface StillNeeded {
  speakers: {
    target: number | null;
    by_age: boolean;
    by_gender: boolean;
    rows: AgeGenderNeed[];
    total: AgeGenderNeed;
  };
  districts: { has_target: boolean; rows: DistrictNeed[]; total: DistrictNeed | null };
  conversations: ConversationNeed[];
  /** Whether the registered people can give the conversations still to make (D-143 rules). */
  capacity: {
    /** Conversations per speaker; null = no limit. */
    limit: number | null;
    /** Each pair of speakers only once. */
    unique_pairs: boolean;
    registered: number;
    /** Conversations the registered people may still take part in, added up (two a
     * conversation); null without a limit. */
    places_left: number | null;
    conversations_to_make: number | null;
    /** The fewest more people with whom the registered ones could give the conversations still
     * to make (their places, and with unique pairs the pairs left); 0 when they can; null without
     * a conversations target. */
    more_speakers_needed: number | null;
  };
}

/** The project's Progress tab (D-148), GET /projects/{id}/progress. Lengths in milliseconds. */
export interface ProjectProgress {
  project_id: string;
  pause_limit_seconds: number;
  /** The project's one recording type (D-153); null for a project made before it that records
   * both. */
  recording_mode: "FACE_TO_FACE" | "TELEPHONY" | null;
  completed: {
    counts: ProgressCounts;
    completed_ms: number;
    target_hours: number | null;
    percent_of_target: number | null;
    approved_conversations: number;
    approved_ms: number;
    approved_effective_ms: number;
    /** Approved conversations whose effective speech is not measured yet (counted as none). */
    not_measured: number;
    recorded_conversations: number;
    recorded_ms: number;
    recorded_effective_ms: number;
    effective_share_pct: number | null;
  };
  conversations: {
    approved: number;
    target: number | null;
    percent_of_target: number | null;
    not_started: number;
    in_progress: number;
    waiting_qc: number;
    rejected: number;
    cancelled: number;
    by_status: Record<string, number>;
  };
  speakers: {
    with_approved: number;
    target: number | null;
    percent_of_target: number | null;
    registered: number;
    limit: number | null;
    at_limit: number | null;
  };
  age_bands: Share;
  gender: Share;
  /** Null for a project that records one type: the split means nothing there (D-153). */
  modes: Share | null;
  districts: Share;
  still_needed: StillNeeded;
}

/** The Progress tab (and the Participants page's "Still needed" line): for the people who manage
 * the project. */
export const getProgress = (id: string) =>
  apiRequest<ProjectProgress>(`/api/v1/projects/${seg(id)}/progress`);

/** The Progress tab as a file: an Excel workbook with a sheet per table, or one long CSV table. */
export type ProgressExportFormat = "xlsx" | "csv";

/** Where the Progress tab's download is (the same people as the tab; audited), for apiDownload. */
export const progressExportPath = (id: string, format: ProgressExportFormat) =>
  `/api/v1/projects/${seg(id)}/progress/export?format=${format}`;
