// Small pieces shared by the task page's call card and the Phone calls page (D-103).
import * as tel from "../../api/telephony";
import "./calls.css";

const TONES: Record<tel.CallState, string> = {
  DIALLING: "progress",
  DIAL_FAILED: "danger",
  CANCELLED: "neutral",
  WAITING_FOR_RECORDING: "info",
  NEEDS_MATCH: "warning",
  FETCH_FAILED: "danger",
  RECORDED: "success",
};

/** A call's state as a coloured pill; the colour only repeats what the text says. */
export function CallBadge({ state, stale = false }: { state: tel.CallState; stale?: boolean }) {
  return (
    <span className={`badge badge--${stale ? "warning" : TONES[state]}`}>
      <span className="badge__dot" aria-hidden="true" />
      {stale ? "Left open" : tel.CALL_STATE_LABELS[state]}
    </span>
  );
}

/** A length for people: seconds under a minute, then minutes, then hours. */
export function span(seconds: number | null): string {
  if (seconds === null || !Number.isFinite(seconds)) return "-";
  if (seconds < 60) return `${Math.round(seconds)} s`;
  if (seconds < 3600) return `${(seconds / 60).toFixed(1)} min`;
  return `${(seconds / 3600).toFixed(1)} h`;
}

export const when = (at: string | null): string => (at ? new Date(at).toLocaleString() : "-");
export const words = (s: string): string => s.toLowerCase().replace(/_/g, " ");
