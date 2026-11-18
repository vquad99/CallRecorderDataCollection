// The signed-in moderator's phone line (D-133), loaded only for people with a phone seat: reads
// how the seat signs in (GET /telephony/status), takes its password (audited as a sign-in, never
// kept anywhere but this page's memory) and holds one SeatLink for the whole session.
import { ApiError } from "../../api/client";
import * as tel from "../../api/telephony";
import type { PhoneLine } from "./PhoneLine";
import { READY, SeatLink, type SeatView } from "./seatLink";

const SIGNING_IN: SeatView = { connecting: true, state: "", label: "", problem: "" };

function described(view: SeatView, call: string | null): Pick<PhoneLine, "status" | "words"> {
  if (view.problem) return { status: "failed", words: `Phone line not connected: ${view.problem}` };
  if (view.connecting) return { status: "connecting", words: "Phone line: Connecting…" };
  if (call) return { status: "busy", words: "Phone line: On a call" };
  if (view.state === READY) return { status: "ready", words: "Phone line: Ready" };
  return { status: "busy", words: `Phone line: ${view.label || view.state || "not Ready"}` };
}

/** Signs the seat in and keeps it so; `show` gets every change (null: this person has no line).
 * Returns the function that takes the line offline. */
export function startLine(show: (line: PhoneLine | null) => void): () => void {
  let link: SeatLink | null = null;
  let view = SIGNING_IN;
  let call: string | null = null;
  let attempt = 0;

  const publish = () => show({ ...described(view, call), call, onCall, retry });
  const onCall = (next: string | null) => {
    if (next === call) return;
    call = next;
    link?.setBusy(call !== null);
    publish();
  };
  const connect = async () => {
    const mine = ++attempt;
    link?.close();
    link = null;
    view = SIGNING_IN;
    publish();
    try {
      const seat = (await tel.telephonyStatus()).seat_login;
      if (mine !== attempt) return;
      if (!seat?.agent_id || !seat.extension || !seat.has_password) {
        show(null); // the seat is made Ready in the Chirp app, or there is no seat to sign in
        return;
      }
      const { password } = await tel.showOwnSeatPassword("line");
      if (mine !== attempt) return;
      const login = { ...seat, agent_id: seat.agent_id, extension: seat.extension };
      link = new SeatLink(login, password, (next) => {
        view = next;
        publish();
      });
      if (call !== null) link.setBusy(true);
    } catch (error) {
      if (mine !== attempt) return;
      const why = error instanceof ApiError ? error.message : "the portal did not answer";
      view = { ...SIGNING_IN, connecting: false, problem: why };
      publish();
    }
  };
  const retry = () => void connect();

  void connect();
  return () => {
    attempt += 1;
    link?.close();
    link = null;
  };
}
