// A call's state as a coloured pill, shared by the task page's call card and the Phone calls page.
import * as tel from "../../api/telephony";
import { StatusBadge, type Tone } from "../../components/StatusBadge";
import "./calls.css";

const TONES: Record<tel.CallState, Tone> = {
  DIALLING: "progress",
  DIAL_FAILED: "danger",
  CANCELLED: "neutral",
  WAITING_FOR_RECORDING: "info",
  NEEDS_MATCH: "warning",
  FETCH_FAILED: "danger",
  RECORDED: "success",
};

/** "Left open" when a call stayed on "on the call" far longer than any call lasts. */
export function CallBadge({ state, stale = false }: { state: tel.CallState; stale?: boolean }) {
  return stale ? (
    <StatusBadge tone="warning" label="Left open" />
  ) : (
    <StatusBadge tone={TONES[state]} label={tel.CALL_STATE_LABELS[state]} />
  );
}
