// The project's Progress tab (D-148): completed minutes, conversations and speakers against the
// project's targets. Its own module, so only the Progress tab's chunk loads it (the first screen is
// near its budget).
import { apiRequest } from "./client";
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

/** The project's Progress tab (D-148), GET /projects/{id}/progress. Lengths in milliseconds. */
export interface ProjectProgress {
  project_id: string;
  pause_limit_seconds: number;
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
  modes: Share;
  districts: Share;
}

/** The Progress tab: for the people who manage the project. */
export const getProgress = (id: string) =>
  apiRequest<ProjectProgress>(`/api/v1/projects/${id}/progress`);
