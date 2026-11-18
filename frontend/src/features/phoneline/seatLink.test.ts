// The phone seat signed in to TxContact's agent manager by the portal (D-133), against a fake
// WebSocket: sign-in and Ready, a wrong password, an address that cannot be reached, TxContact's
// 5-minute close and RECONNECT, Ready again after each call without signing in again, Offline
// and signed out at the end, and the password never in the technical log or browser storage.
// Requirements: TEL-004, TEL-011, TEL-036
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { FakeAgentManager, FakeSocket } from "../../test/fakeWebSocket";
import { READY, SeatLink, seatLog, TIMING, type SeatView } from "./seatLink";

const LOGIN = {
  url: "wss://agents.example.org/txagentmanager/",
  tenant_id: "desicrew",
  agent_id: "70001",
  extension: "70001",
};
const PLUGINS = ["PHONE", "CHAT", "BROWSER"];
const AUTH = { AGENT_ID: "70001", TENANT_ID: "desicrew", PASSWORD: "seat-pass" };
const agent = (name: string, DATA: Record<string, unknown>) => ({
  EVENT_NAME: name,
  EVENT_CLASS: "AGENT",
  SESSION_ID: "session-1",
  DATA,
});

let manager: FakeAgentManager;
let views: SeatView[];
const last = () => views[views.length - 1];
const socket = (n: number) => FakeSocket.sockets[n] as FakeSocket;
/** Lets the fake server's answers (each a microtask away) arrive. */
async function settle() {
  for (let i = 0; i < 30; i++) await Promise.resolve();
}

function signIn(password = "seat-pass") {
  return new SeatLink(LOGIN, password, (view) => views.push(view));
}

beforeEach(() => {
  vi.useFakeTimers();
  vi.stubGlobal("WebSocket", FakeSocket);
  manager = new FakeAgentManager();
  FakeSocket.reset(manager);
  views = [];
});

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
  FakeSocket.reset();
});

describe("the phone seat's sign-in (D-133)", () => {
  it("connects with the seat, tenant and password, logs in on the extension and asks for Ready", async () => {
    signIn();
    await settle();
    expect(socket(0).url).toBe(LOGIN.url);
    expect(socket(0).sent).toEqual([
      { EVENT_NAME: "CONNECT", EVENT_CLASS: "AGENT", PLUGINS, AUTH },
      agent("LOGIN", { EXTENSION: "70001" }),
      agent("CHANGE_AGENT_STATE", { STATE: READY, EXTENSION: "70001" }),
    ]);
    // TxContact's answer to LOGIN (On Break) comes first; Ready ends the sign-in.
    expect(views[0]).toEqual({
      connecting: true,
      state: "ONBREAK",
      label: "On Break",
      problem: "",
    });
    expect(last()).toEqual({
      connecting: false,
      state: READY,
      label: "Ready For Call",
      problem: "",
    });
  });

  it("asks for Ready a moment after LOGIN when TxContact says nothing to it", async () => {
    FakeSocket.reset(); // the test plays TxContact
    signIn();
    socket(0).accept();
    socket(0).emit({ EVENT_NAME: "CONNECTED", SESSION_ID: "s9", DATA: {} });
    const names = () => socket(0).sent.map((f) => f.EVENT_NAME);
    expect(names()).toEqual(["CONNECT", "LOGIN"]);
    await vi.advanceTimersByTimeAsync(TIMING.loginAnswerMs);
    expect(names()).toEqual(["CONNECT", "LOGIN", "CHANGE_AGENT_STATE"]);
    expect(socket(0).sent[2]?.SESSION_ID).toBe("s9");
    // Keys in another case are read all the same; another seat's change is not this one's.
    socket(0).emit({
      event_name: "AGENT_STATE_CHANGED",
      data: { agent_id: "70002", state: READY },
    });
    expect(last()).toBeUndefined();
    socket(0).emit({
      event_name: "AGENT_STATE_CHANGED",
      data: { agent_id: "70001", state: READY },
    });
    expect(last()).toMatchObject({ connecting: false, state: READY });
  });

  it("a wrong password ends with TxContact's alert in its own words, and no second try", async () => {
    signIn("not-the-password");
    await settle();
    expect(last()).toEqual({
      connecting: false,
      state: "",
      label: "",
      problem: "Invalid agent credentials",
    });
    expect(FakeSocket.names()).toEqual(["CONNECT"]);
    expect(socket(0).readyState).toBe(3);
    await vi.advanceTimersByTimeAsync(60_000);
    expect(FakeSocket.sockets).toHaveLength(1);
  });

  it("says so when TxContact cannot be reached, or does not make the seat Ready", async () => {
    FakeSocket.reset();
    signIn();
    socket(0).drop(1006);
    expect(last()?.problem).toBe("TxContact could not be reached");

    views = [];
    signIn();
    socket(1).accept();
    socket(1).emit({ EVENT_NAME: "CONNECTED", SESSION_ID: "s9", DATA: {} });
    socket(1).emit({
      EVENT_NAME: "AGENT_STATE_CHANGED",
      DATA: { STATE: "ONBREAK", STATE_DESC: "On Break" },
    });
    await vi.advanceTimersByTimeAsync(3 * TIMING.readyAnswerMs);
    expect(last()?.problem).toBe("TxContact kept it On Break");
    const sent = socket(1).sent.map((f) => f.EVENT_NAME);
    expect(sent.filter((n) => n === "CHANGE_AGENT_STATE")).toHaveLength(3 + 1); // + Offline
    expect(sent.slice(-2)).toEqual(["LOGOUT", "DISCONNECT"]);
  });

  it("connects again with the same session after TxContact closes the connection", async () => {
    signIn();
    await settle();
    socket(0).drop(1000); // TxContact's 5-minute close
    expect(last()).toMatchObject({ connecting: true, state: READY, problem: "" });
    await vi.advanceTimersByTimeAsync(TIMING.againMs);
    await settle();
    expect(socket(1).sent).toEqual([
      { EVENT_NAME: "RECONNECT", EVENT_CLASS: "AGENT", SESSION_ID: "session-1", PLUGINS, AUTH },
    ]);
    expect(last()).toEqual({
      connecting: false,
      state: READY,
      label: "Ready For Call",
      problem: "",
    });
    expect(FakeSocket.names().filter((n) => n === "LOGIN")).toHaveLength(1);

    // TxContact gone for good: three tries, then the reason.
    FakeSocket.manager = null;
    for (let n = 1; n <= 4; n++) {
      socket(n).drop(1006);
      await vi.advanceTimersByTimeAsync(TIMING.againMs);
    }
    expect(FakeSocket.sockets).toHaveLength(5);
    expect(last()?.problem).toBe("the connection to TxContact was lost");
  });

  it("is made Ready again after each call, without signing in again", async () => {
    const link = signIn();
    await settle();
    const asks = () => FakeSocket.names().filter((n) => n === "CHANGE_AGENT_STATE").length;
    for (const call of [1, 2]) {
      link.setBusy(true);
      manager.change("ON_CALL"); // the call reaches the seat
      await settle();
      expect(last()?.state).toBe("ON_CALL");
      expect(asks()).toBe(call); // TxContact's state is left alone during the call
      link.setBusy(false); // the call is closed in the portal
      await settle();
      expect(last()?.state).toBe(READY);
    }
    // A state TxContact puts the seat in after a call (wrap-up) is turned back to Ready too.
    manager.change("WRAP_UP");
    await settle();
    expect(last()?.state).toBe(READY);
    expect(FakeSocket.sockets).toHaveLength(1);
    expect(FakeSocket.names()).toEqual([
      "CONNECT",
      "LOGIN",
      "CHANGE_AGENT_STATE",
      "CHANGE_AGENT_STATE",
      "CHANGE_AGENT_STATE",
      "CHANGE_AGENT_STATE",
    ]);
  });

  it("takes the seat Offline, signs it out and disconnects at the end", async () => {
    const link = signIn();
    await settle();
    link.close();
    await settle();
    expect(socket(0).sent.slice(-3)).toEqual([
      agent("CHANGE_AGENT_STATE", { STATE: "OFFLINE", EXTENSION: "70001" }),
      agent("LOGOUT", { EXTENSION: "70001" }),
      agent("DISCONNECT", {}),
    ]);
    expect(manager.state).toBe("OFFLINE");
    expect(socket(0).readyState).toBe(3);
    link.close(); // twice is harmless
    expect(socket(0).sent).toHaveLength(6);
  });

  it("keeps every frame in the technical log, never the password", async () => {
    manager.password = "s3cret-seat";
    const link = signIn("s3cret-seat");
    await settle();
    socket(0).emit({ EVENT_NAME: "NOTIFY", DATA: { MESSAGE: "echo s3cret-seat" } });
    link.close();
    const text = seatLog
      .entries()
      .map((e) => `${e.kind} ${e.text}`)
      .join("\n");
    expect(text).toContain('sent {"EVENT_NAME":"CONNECT"');
    expect(text).toContain('received {"EVENT_NAME":"AGENT_STATE_CHANGED"');
    expect(text).toContain("(hidden)");
    expect(text).not.toContain("s3cret-seat");
    expect(localStorage.length + sessionStorage.length).toBe(0);
  });
});
