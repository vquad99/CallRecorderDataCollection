// Coloured status pill. The colour only repeats what the text already says (WCAG 1.4.1).

type Tone = "neutral" | "info" | "progress" | "warning" | "success" | "danger";

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
  RETURNED: "warning",
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

export function StatusBadge({ status, label }: { status: string; label: string }) {
  return (
    <span className={`badge badge--${TONES[status] ?? "neutral"}`}>
      <span className="badge__dot" aria-hidden="true" />
      {label}
    </span>
  );
}
