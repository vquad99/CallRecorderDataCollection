// Test-only: a WebSocket the tests control, and TxContact's agent manager answering on it the way
// backend/tests/fake_txcontact.py does for the browser journeys (D-133). What the server sends
// arrives a moment later (a microtask), as on a real connection.
type Frame = Record<string, unknown>;

const WORDS: Record<string, string> = {
  READY_FOR_CALL: "Ready For Call",
  ONBREAK: "On Break",
  OFFLINE: "Offline",
  ON_CALL: "On Call",
};

export class FakeSocket {
  static sockets: FakeSocket[] = [];
  /** Answers every connection when set; otherwise the test plays the server by hand. */
  static manager: FakeAgentManager | null = null;

  readyState = 0;
  readonly sent: Frame[] = [];
  onopen: (() => void) | null = null;
  onmessage: ((event: { data: string }) => void) | null = null;
  onclose: ((event: { code: number; reason: string }) => void) | null = null;

  constructor(readonly url: string) {
    FakeSocket.sockets.push(this);
    if (FakeSocket.manager) queueMicrotask(() => this.accept());
  }

  /** Every event sent so far, on every connection, by name. */
  static names(): string[] {
    return FakeSocket.sockets.flatMap((s) => s.sent.map((f) => String(f.EVENT_NAME)));
  }

  static reset(manager: FakeAgentManager | null = null): void {
    FakeSocket.sockets = [];
    FakeSocket.manager = manager;
  }

  /** The server accepts the connection. */
  accept(): void {
    this.readyState = 1;
    this.onopen?.();
  }

  /** The server sends an event. */
  emit(frame: Frame): void {
    if (this.readyState === 1) this.onmessage?.({ data: JSON.stringify(frame) });
  }

  /** The server closes the connection (TxContact does every 5 minutes). */
  drop(code = 1000): void {
    if (this.readyState === 3) return;
    this.readyState = 3;
    this.onclose?.({ code, reason: "" });
  }

  send(text: string): void {
    const frame = JSON.parse(text) as Frame;
    this.sent.push(frame);
    FakeSocket.manager?.receive(this, frame);
  }

  close(code = 1000): void {
    queueMicrotask(() => this.drop(code));
  }
}

/** TxContact's agent manager: CONNECT with the right password is CONNECTED (otherwise ALERT,
 * DISCONNECTED and the end of the connection), LOGIN puts the seat On Break, and every state
 * change is told with AGENT_STATE_CHANGED. */
export class FakeAgentManager {
  password = "seat-pass";
  state = "OFFLINE";
  agent = "";
  readonly session = "session-1";
  private socket: FakeSocket | null = null;

  receive(socket: FakeSocket, frame: Frame): void {
    const reply = (event: Frame) => queueMicrotask(() => socket.emit(event));
    const auth = (frame.AUTH ?? {}) as Frame;
    const data = (frame.DATA ?? {}) as Frame;
    switch (frame.EVENT_NAME) {
      case "CONNECT":
      case "RECONNECT":
        if (auth.PASSWORD !== this.password) {
          reply({ EVENT_NAME: "ALERT", DATA: { MESSAGE: "Invalid agent credentials" } });
          reply({ EVENT_NAME: "DISCONNECTED", DATA: {} });
          queueMicrotask(() => socket.drop());
          return;
        }
        this.socket = socket;
        this.agent = String(auth.AGENT_ID);
        reply({ EVENT_NAME: "CONNECTED", SESSION_ID: this.session, DATA: {} });
        return;
      case "LOGIN":
        return this.change("ONBREAK");
      case "CHANGE_AGENT_STATE":
        return this.change(String(data.STATE));
      case "LOGOUT":
        return this.change("OFFLINE");
      case "DISCONNECT":
        reply({ EVENT_NAME: "DISCONNECTED", SESSION_ID: this.session, DATA: {} });
        queueMicrotask(() => socket.drop());
    }
  }

  /** TxContact puts the seat in a state and says so (ON_CALL when a call reaches it). */
  change(state: string): void {
    this.state = state;
    const socket = this.socket;
    const event = {
      EVENT_NAME: "AGENT_STATE_CHANGED",
      SESSION_ID: this.session,
      DATA: { AGENT_ID: this.agent, TENANT_ID: "desicrew", STATE: state, STATE_DESC: WORDS[state] },
    };
    queueMicrotask(() => socket?.emit(event));
  }
}
