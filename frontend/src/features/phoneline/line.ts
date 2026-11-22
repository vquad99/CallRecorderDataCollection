// The signed-in moderator's phone line (D-133), loaded only for people with a phone seat: reads
// how the seat signs in (GET /telephony/status), takes its password (audited as a sign-in, never
// kept anywhere but this page's memory) and holds one SeatLink for the whole session. While it is
// on a call it checks that the call is still on, so a call ended elsewhere frees it (FEW-07).
import { ApiError } from "../../api/client";
import * as tel from "../../api/telephony";
import type { PhoneLine } from "./PhoneLine";
import { READY, SeatLink, type SeatView } from "./seatLink";

const SIGNING_IN: SeatView = { connecting: true, state: "", label: "", problem: "" };
/** A call the line is on is looked at this often: one that ended elsewhere (cancelled on the Phone
 * calls page, or closed in another tab) frees the line, so Start call works again on every task
 * (FEW-07). */
export const CALL_CHECK_MS = 15_000;
/** What the task page holds the line with while a call is placed, before the call has an id. */
const PLACING = "starting";

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
  let checking: ReturnType<typeof setInterval> | null = null;

  const publish = () => show({ ...described(view, call), call, onCall, retry });
  const stopChecking = () => {
    if (checking !== null) clearInterval(checking);
    checking = null;
  };
  /** While the line is on a real call, ask now and then whether it is still on: once an answer no
   * longer lists it, the call is over and the line is made Ready again. A look that fails changes
   * nothing; the next one asks again. */
  const checkCall = () => {
    stopChecking();
    const held = call;
    if (held === null || held === PLACING) return;
    let asking = false;
    checking = setInterval(() => {
      if (asking) return;
      asking = true;
      tel
        .listAllCalls({ state: "DIALLING", page: 1, page_size: 100 })
        .then((open) => {
          if (call === held && !open.items.some((c) => c.id === held)) onCall(null);
        })
        .catch(() => undefined)
        .finally(() => {
          asking = false;
        });
    }, CALL_CHECK_MS);
  };
  const onCall = (next: string | null) => {
    if (next === call) return;
    call = next;
    link?.setBusy(call !== null);
    checkCall();
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
    stopChecking();
    link?.close();
    link = null;
  };
}
