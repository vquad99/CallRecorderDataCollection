// The moderator's phone seat signed in to TxContact by the portal itself (D-133), as TxContact's
// Chirp app does it: TxContact's agent manager (TxAgentManager) over a WebSocket, with the events
// of its API document and their upper-case keys. One SeatLink is one sign-in: it connects
// (CONNECT, then LOGIN on the seat's extension), asks for READY_FOR_CALL and keeps the seat so:
// it RECONNECTs with the same session when TxContact closes the connection (every 5 minutes),
// and makes the seat Ready again when a call is over. close() takes it Offline and signs it out.
// Every frame sent and received is kept in `seatLog`, in this page's memory only, for the Super
// Admin's technical log; the password never is.

export const READY = "READY_FOR_CALL";
const PLUGINS = ["PHONE", "CHAT", "BROWSER"];
const OPEN = 1; // WebSocket.OPEN

/** How long the first sign-in may take, how long TxContact's answer to LOGIN is waited for before
 * asking for Ready, how long an ask for Ready waits for its answer, and the pause before
 * connecting again (the Chirp app waits 2 seconds). */
export const TIMING = {
  signInMs: 20_000,
  loginAnswerMs: 2_000,
  readyAnswerMs: 5_000,
  againMs: 2_000,
};
const TRIES = 3; // connecting again, or asking for Ready, before giving up

/** Where and as whom the seat signs in (GET /telephony/status, D-133). */
export interface SeatLogin {
  url: string;
  tenant_id: string;
  agent_id: string;
  extension: string;
}

/** What the page shows of the seat. */
export interface SeatView {
  /** Signing in, or connecting again after TxContact closed the connection. */
  connecting: boolean;
  /** TxContact's state of the seat (READY_FOR_CALL, ONBREAK, OFFLINE, ...); "" before it says. */
  state: string;
  /** TxContact's own words for the state (STATE_DESC), when it sends them. */
  label: string;
  /** Why the seat is not signed in, in plain words; "" while it is. Final: sign in again with a
   * new SeatLink. */
  problem: string;
}

export interface SeatLogEntry {
  at: string;
  kind: "sent" | "received" | "note";
  text: string;
}

const LOG_SIZE = 300;
let entries: readonly SeatLogEntry[] = [];
const listeners = new Set<() => void>();

/** The frames of this page's seat sign-ins, newest last: memory only, never the password. */
export const seatLog = {
  entries: () => entries,
  subscribe(listener: () => void): () => void {
    listeners.add(listener);
    return () => listeners.delete(listener);
  },
};

function log(kind: SeatLogEntry["kind"], text: string): void {
  entries = [...entries.slice(1 - LOG_SIZE), { at: new Date().toISOString(), kind, text }];
  listeners.forEach((listener) => listener());
}

type Frame = Record<string, unknown>;

/** An object's keys in upper case, as TxContact's document writes them. */
function upper(value: unknown): Frame {
  if (!value || typeof value !== "object" || Array.isArray(value)) return {};
  return Object.fromEntries(Object.entries(value).map(([k, v]) => [k.toUpperCase(), v]));
}

export class SeatLink {
  private socket: WebSocket | null = null;
  private session = "";
  private loggedIn = false;
  /** Ready at least once: from then on a lost connection is connected again. */
  private signedIn = false;
  /** A call is open in the portal: TxContact's state is left as it is. */
  private busy = false;
  private asks = 0;
  private reconnects = 0;
  private closed = false;
  private lastAlert = "";
  private readonly timers = new Map<string, number>();
  private view: SeatView = { connecting: true, state: "", label: "", problem: "" };

  constructor(
    private readonly login: SeatLogin,
    private readonly password: string,
    private readonly onView: (view: SeatView) => void,
  ) {
    this.later("signIn", TIMING.signInMs, () =>
      this.fail(`TxContact did not make it Ready within ${TIMING.signInMs / 1000} seconds`),
    );
    this.open("CONNECT");
  }

  /** True while a call is open in the portal: TxContact's state is left as it is. False once
   * it is over: the seat is made Ready again for the next call, without signing in again. */
  setBusy(busy: boolean): void {
    this.busy = busy;
    this.asks = 0;
    this.stop("ready");
    this.askReady();
  }

  /** Offline, signed out and disconnected (as far as the connection allows), then closed. */
  close(): void {
    if (this.closed) return;
    this.closed = true;
    this.timers.forEach((timer) => window.clearTimeout(timer));
    this.timers.clear();
    if (this.loggedIn) {
      this.send(
        this.event("CHANGE_AGENT_STATE", { STATE: "OFFLINE", EXTENSION: this.login.extension }),
      );
      this.send(this.event("LOGOUT", { EXTENSION: this.login.extension }));
    }
    if (this.session) this.send(this.event("DISCONNECT", {}));
    this.socket?.close(1000);
    this.socket = null;
  }

  private open(kind: "CONNECT" | "RECONNECT"): void {
    let socket: WebSocket;
    try {
      socket = new WebSocket(this.login.url);
    } catch (error) {
      this.fail(`its address was refused (${error instanceof Error ? error.message : "unknown"})`);
      return;
    }
    this.socket = socket;
    let opened = false;
    socket.onopen = () => {
      opened = true;
      log("note", `connected to ${this.login.url}`);
      const auth = {
        AGENT_ID: this.login.agent_id,
        TENANT_ID: this.login.tenant_id,
        PASSWORD: this.password,
      };
      this.send(
        kind === "CONNECT"
          ? { EVENT_NAME: "CONNECT", EVENT_CLASS: "AGENT", PLUGINS, AUTH: auth }
          : {
              EVENT_NAME: "RECONNECT",
              EVENT_CLASS: "AGENT",
              SESSION_ID: this.session,
              PLUGINS,
              AUTH: auth,
            },
      );
    };
    socket.onmessage = (message: MessageEvent) => {
      if (socket === this.socket) this.receive(String(message.data));
    };
    socket.onclose = (event: CloseEvent) => {
      if (socket === this.socket) this.lost(opened, event.code, event.reason);
    };
  }

  private receive(text: string): void {
    log("received", this.password ? text.split(this.password).join("(hidden)") : text);
    let frame: Frame;
    try {
      frame = upper(JSON.parse(text));
    } catch {
      return; // not JSON: kept in the log only
    }
    const data = upper(frame.DATA);
    const name = String(frame.EVENT_NAME ?? "").toUpperCase();
    if (name === "CONNECTED") this.connected(String(frame.SESSION_ID ?? ""));
    else if (name === "AGENT_STATE_CHANGED") this.stateChanged(data);
    else if (name === "ALERT") this.alert(String(data.MESSAGE ?? "") || "TxContact sent an alert");
    else if (name === "DISCONNECTED" && !this.signedIn)
      this.fail(this.lastAlert || "TxContact ended the connection");
    else if (name === "DISCONNECTED") this.socket?.close(); // connected again by lost()
  }

  private connected(session: string): void {
    if (session) this.session = session;
    this.reconnects = 0;
    if (this.loggedIn) {
      // Connected again after TxContact closed the connection: the session is the same one.
      this.show({ connecting: false });
      this.askReady();
      return;
    }
    this.send(this.event("LOGIN", { EXTENSION: this.login.extension }));
    this.loggedIn = true;
    // TxContact may answer LOGIN with a state change; Ready is asked for then, or after a while.
    this.later("login", TIMING.loginAnswerMs, () => this.askReady());
  }

  private stateChanged(data: Frame): void {
    const agent = String(data.AGENT_ID ?? "");
    if (agent && agent !== this.login.agent_id) return; // another seat's
    const state = String(data.STATE ?? "").toUpperCase();
    this.lastAlert = "";
    if (state === READY) {
      this.asks = 0;
      this.stop("ready");
      if (!this.signedIn) {
        this.signedIn = true;
        this.stop("signIn");
      }
      this.show({ connecting: false, state, label: String(data.STATE_DESC ?? "") });
      return;
    }
    this.show({ state, label: String(data.STATE_DESC ?? "") });
    this.askReady();
  }

  /** Asks TxContact for Ready unless the seat is Ready, an earlier ask still waits for its
   * answer, or a call is open (a fresh sign-in, after a page reload, asks all the same); after
   * TRIES asks without Ready the sign-in has failed. */
  private askReady(): void {
    const waiting = this.timers.has("ready") || this.view.state === READY;
    if (this.closed || !this.loggedIn || (this.busy && this.signedIn) || waiting) return;
    this.stop("login");
    if (this.asks >= TRIES) {
      this.fail(`TxContact kept it ${this.view.label || this.view.state || "not Ready"}`);
      return;
    }
    this.asks += 1;
    this.send(this.event("CHANGE_AGENT_STATE", { STATE: READY, EXTENSION: this.login.extension }));
    this.later("ready", TIMING.readyAnswerMs, () => this.askReady());
  }

  private alert(message: string): void {
    this.lastAlert = message;
    if (!this.signedIn) this.fail(message);
  }

  private lost(opened: boolean, code: number, reason: string): void {
    this.socket = null;
    log("note", `connection closed (code ${code}${reason ? `, ${reason}` : ""})`);
    if (this.closed) return;
    if (!this.signedIn) {
      this.fail(
        this.lastAlert ||
          (opened ? "TxContact closed the connection" : "TxContact could not be reached"),
      );
    } else if (this.reconnects >= TRIES) {
      this.fail(this.lastAlert || "the connection to TxContact was lost");
    } else {
      this.reconnects += 1;
      this.show({ connecting: true });
      this.later("again", TIMING.againMs, () => this.open("RECONNECT"));
    }
  }

  private fail(problem: string): void {
    if (this.closed) return;
    log("note", `not connected: ${problem}`);
    this.close();
    this.view = { ...this.view, connecting: false, problem };
    this.onView(this.view);
  }

  private show(change: Partial<SeatView>): void {
    this.view = { ...this.view, ...change };
    if (!this.closed) this.onView(this.view);
  }

  private event(name: string, data: Frame): Frame {
    return { EVENT_NAME: name, EVENT_CLASS: "AGENT", SESSION_ID: this.session, DATA: data };
  }

  private send(frame: Frame): void {
    if (this.socket?.readyState !== OPEN) return;
    log(
      "sent",
      JSON.stringify(frame, (key, value: unknown) => (key === "PASSWORD" ? "(hidden)" : value)),
    );
    this.socket.send(JSON.stringify(frame));
  }

  private later(name: string, ms: number, run: () => void): void {
    this.stop(name);
    this.timers.set(
      name,
      window.setTimeout(() => {
        this.timers.delete(name);
        run();
      }, ms),
    );
  }

  private stop(name: string): void {
    window.clearTimeout(this.timers.get(name));
    this.timers.delete(name);
  }
}
