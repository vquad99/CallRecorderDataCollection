// The six stages a conversation (task) goes through, as the Progress tab counts them (D-148,
// backend projects/progress.py) and the dashboards draw them (D-151): one colour each, in an order
// where neighbouring colours stay apart for colour-blind readers (checked with the dataviz
// validator). The legend beside each chart repeats every number, so colour is never the only key.
import { labelFor, TASK_STATUS_LABELS } from "../../lib/labels";
import type { DonutPart } from "./Charts";

export type StageKey =
  "approved" | "waiting_qc" | "in_progress" | "not_started" | "rejected" | "cancelled";

export interface Stage {
  key: StageKey;
  label: string;
  color: string;
  /** The task statuses counted in this stage. */
  statuses: string[];
}

export const STAGES: Stage[] = [
  { key: "approved", label: "Approved", color: "var(--icon-green)", statuses: ["APPROVED"] },
  {
    key: "waiting_qc",
    label: "Waiting for QC or approval",
    color: "var(--series-waiting)",
    statuses: ["AUDIO_QC", "ADMIN_REVIEW"],
  },
  {
    key: "in_progress",
    label: "In progress",
    color: "var(--icon-blue)",
    statuses: ["IN_PROGRESS", "RECORDED", "ON_HOLD", "CONSENT_FIX"],
  },
  {
    key: "not_started",
    label: "Not started",
    color: "var(--k-400)",
    statuses: ["DRAFT", "ASSIGNED"],
  },
  { key: "rejected", label: "Rejected", color: "var(--icon-rose)", statuses: ["REJECTED"] },
  { key: "cancelled", label: "Cancelled", color: "var(--icon-slate)", statuses: ["CANCELLED"] },
];

/** Tasks counted by status, as the donut's parts: one per stage, its statuses named under it when
 * it holds more than one ("Audio QC 48 · Admin review 12"). Stages with no tasks are left out. */
export function stageParts(byStatus: Record<string, number>): DonutPart[] {
  return STAGES.map((s) => {
    const inside = s.statuses.filter((st) => (byStatus[st] ?? 0) > 0);
    const n = inside.reduce((sum, st) => sum + (byStatus[st] ?? 0), 0);
    const named = inside.map((st) => labelFor(TASK_STATUS_LABELS, st));
    const detail =
      inside.length > 1 || (inside.length === 1 && named[0] !== s.label)
        ? inside.map((st, i) => `${named[i]} ${byStatus[st]}`).join(" · ")
        : undefined;
    return { key: s.key, label: s.label, n, color: s.color, ...(detail ? { detail } : {}) };
  }).filter((p) => p.n > 0);
}
