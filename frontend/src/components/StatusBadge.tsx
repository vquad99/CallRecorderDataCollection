// Coloured status pill. The colour only repeats what the text already says (WCAG 1.4.1).

export type Tone = "neutral" | "info" | "progress" | "warning" | "success" | "danger";

/** Tones for the statuses of tasks, projects and accounts. */
const TONES: Record<string, Tone> = {
  // tasks
  DRAFT: "neutral",
  ASSIGNED: "info",
  IN_PROGRESS: "progress",
  RECORDED: "progress",
  AUDIO_QC: "warning",
  ADMIN_REVIEW: "info",
  APPROVED: "success",
  REJECTED: "danger",
  CANCELLED: "neutral",
  ON_HOLD: "warning",
  // projects and accounts
  ACTIVE: "success",
  PAUSED: "warning",
  COMPLETED: "info",
  ARCHIVED: "neutral",
  INVITED: "info",
  DISABLED: "neutral",
  LOCKED: "danger",
};

/** A pill for a task, project or account status, or for anything else with its own tone. */
export function StatusBadge({
  label,
  status,
  tone,
}: {
  label: string;
  status?: string;
  tone?: Tone;
}) {
  return (
    <span className={`badge badge--${tone ?? TONES[status ?? ""] ?? "neutral"}`}>{label}</span>
  );
}
