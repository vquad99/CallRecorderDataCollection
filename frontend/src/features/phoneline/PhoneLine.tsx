// The moderator's phone line (D-133). While a moderator with a phone seat and its saved password
// is signed in, the portal holds the seat at TxContact and keeps it Ready for calls: no click,
// no Chirp app. It goes offline when they sign out (also the idle sign-out) and when the tab
// closes. The code that talks to TxContact (line.ts, seatLink.ts) loads only for such people,
// so the first screen stays small; this file holds what every page shares.
import { createContext, useContext, useEffect, useState, type ReactNode } from "react";

import { useAuth } from "../../auth/AuthContext";

export interface PhoneLine {
  /** connecting: signing in, or connecting again; ready: Ready for a call; busy: signed in but
   * not Ready (on a call, or a state TxContact put the seat in); failed: not connected. */
  status: "connecting" | "ready" | "busy" | "failed";
  /** The line in plain words, for the top bar. */
  words: string;
  /** The portal call the line is on, or null. */
  call: string | null;
  /** A call starts (its id, or any placeholder while it is placed) or is over (null): while one
   * is open TxContact's state of the seat is left alone; after it the seat is made Ready again. */
  onCall: (call: string | null) => void;
  /** Sign in again after a failure. */
  retry: () => void;
}

const PhoneLineContext = createContext<PhoneLine | null>(null);

/** The line; null for people without one (no seat, no saved password, or the seat is made
 * Ready in TxContact's Chirp app). */
export const usePhoneLine = () => useContext(PhoneLineContext);

export function PhoneLineProvider({ children }: { children: ReactNode }) {
  const { user } = useAuth();
  const [line, setLine] = useState<PhoneLine | null>(null);
  // The person themselves only: not while a Super Admin views the app as them (D-100).
  const seat =
    user && !user.viewer && !user.mfa_setup_required && user.telephony_has_password
      ? (user.telephony_agent_id ?? "")
      : "";
  useEffect(() => {
    if (!seat) return;
    let stop: (() => void) | undefined;
    let gone = false;
    import("./line")
      .then((m) => {
        if (!gone) stop = m.startLine(setLine);
      })
      .catch(() => undefined); // a stale build reloads itself (D-089)
    return () => {
      gone = true;
      stop?.();
      setLine(null);
    };
  }, [seat]);
  return <PhoneLineContext.Provider value={line}>{children}</PhoneLineContext.Provider>;
}

const LABEL = "Phone line: ";

/** The line's state in the top bar, with Try again after a failure; nothing without a line. */
export function PhoneLineStatus() {
  const line = usePhoneLine();
  if (!line) return null;
  return (
    <p className="phone-line" data-status={line.status} role="status">
      <span className="phone-line__words" title={line.words}>
        {line.words}
      </span>
      {/* A phone's narrow top bar shows only the state beside the dot ("Ready"). */}
      {line.words.startsWith(LABEL) ? (
        <span className="phone-line__short" aria-hidden="true">
          {line.words.slice(LABEL.length)}
        </span>
      ) : null}
      {line.status === "failed" ? (
        <button type="button" className="phone-line__retry" onClick={line.retry}>
          Try again
        </button>
      ) : null}
    </p>
  );
}
