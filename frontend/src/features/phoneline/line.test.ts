// The phone line follows the call it is on (FEW-07): a call that ends elsewhere (cancelled on the
// Phone calls page, closed in another tab) frees the line within 15 seconds, so Start call works
// again on every task; a look that fails changes nothing, and the line stops looking once it is
// free or taken offline.
// Requirements: TEL-011, TEL-018, TEL-036
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { CALL_CHECK_MS, startLine } from "./line";
import type { PhoneLine } from "./PhoneLine";

// vi.mock and vi.hoisted run before the imports above.
const tel = vi.hoisted(() => ({
  telephonyStatus: vi.fn(),
  showOwnSeatPassword: vi.fn(),
  listAllCalls: vi.fn(),
}));
/** What the line asked of the seat: busy (on a call) or not, and how often it was closed. */
const seat = vi.hoisted(() => ({ busy: [] as boolean[], closed: 0 }));

vi.mock("../../api/telephony", () => tel);
vi.mock("./seatLink", () => ({
  READY: "READY_FOR_CALL",
  // Signed in and Ready at once: TxContact's agent manager itself is tested in seatLink.test.ts.
  SeatLink: class {
    constructor(_login: unknown, _password: string, onView: (view: unknown) => void) {
      onView({ connecting: false, state: "READY_FOR_CALL", label: "Ready", problem: "" });
    }
    setBusy(busy: boolean) {
      seat.busy.push(busy);
    }
    close() {
      seat.closed += 1;
    }
  },
}));

const SEAT = {
  url: "wss://agents.example.org/txagentmanager/",
  tenant_id: "desicrew",
  agent_id: "70001",
  extension: "70001",
  has_password: true,
};
/** The calls still on the call, as GET /calls?state=DIALLING lists them. */
const dialling = (...ids: string[]) => ({
  items: ids.map((id) => ({ id, state: "DIALLING" })),
  total: ids.length,
  page: 1,
  page_size: 100,
});

let shown: (PhoneLine | null)[];
const line = () => shown[shown.length - 1];
/** Lets the sign-in's answers (each a microtask away) arrive. */
async function settle() {
  for (let i = 0; i < 20; i++) await Promise.resolve();
}

beforeEach(() => {
  vi.useFakeTimers();
  shown = [];
  seat.busy = [];
  seat.closed = 0;
  tel.telephonyStatus.mockResolvedValue({
    configured: true,
    provider: "TXCONTACT",
    seat_login: SEAT,
  });
  tel.showOwnSeatPassword.mockResolvedValue({ password: "seat-pass" });
  tel.listAllCalls.mockReset().mockResolvedValue(dialling());
});

afterEach(() => {
  vi.useRealTimers();
});

describe("the phone line follows the call it is on (FEW-07)", () => {
  it("is Ready again once the call ended elsewhere", async () => {
    const stop = startLine((next) => shown.push(next));
    await settle();
    expect(line()?.words).toBe("Phone line: Ready");
    tel.listAllCalls.mockResolvedValue(dialling("c1", "c9"));
    line()?.onCall("c1");
    expect(line()?.words).toBe("Phone line: On a call");

    await vi.advanceTimersByTimeAsync(CALL_CHECK_MS);
    expect(tel.listAllCalls).toHaveBeenCalledWith({ state: "DIALLING", page: 1, page_size: 100 });
    expect(line()?.call).toBe("c1"); // still on the call

    tel.listAllCalls.mockResolvedValue(dialling("c9")); // cancelled on the Phone calls page
    await vi.advanceTimersByTimeAsync(CALL_CHECK_MS);
    expect(line()?.call).toBeNull();
    expect(line()?.words).toBe("Phone line: Ready");
    expect(seat.busy).toEqual([true, false]); // the seat is made Ready again

    const asked = tel.listAllCalls.mock.calls.length;
    await vi.advanceTimersByTimeAsync(3 * CALL_CHECK_MS);
    expect(tel.listAllCalls).toHaveBeenCalledTimes(asked); // nothing to look for any more
    stop();
  });

  it("keeps the call when a look fails, and stops looking when the line goes offline", async () => {
    const stop = startLine((next) => shown.push(next));
    await settle();
    line()?.onCall("starting"); // the call is being placed: no id to look for yet
    await vi.advanceTimersByTimeAsync(2 * CALL_CHECK_MS);
    expect(tel.listAllCalls).not.toHaveBeenCalled();

    line()?.onCall("c1");
    tel.listAllCalls.mockRejectedValue(new Error("Failed to fetch"));
    await vi.advanceTimersByTimeAsync(CALL_CHECK_MS);
    expect(tel.listAllCalls).toHaveBeenCalledTimes(1);
    expect(line()?.call).toBe("c1");
    expect(line()?.words).toBe("Phone line: On a call");

    stop();
    await vi.advanceTimersByTimeAsync(3 * CALL_CHECK_MS);
    expect(tel.listAllCalls).toHaveBeenCalledTimes(1);
    expect(seat.closed).toBe(1);
  });

  it("stops looking once the task page says the call is over", async () => {
    const stop = startLine((next) => shown.push(next));
    await settle();
    line()?.onCall("c1");
    line()?.onCall(null); // closed on its own task page
    await vi.advanceTimersByTimeAsync(3 * CALL_CHECK_MS);
    expect(tel.listAllCalls).not.toHaveBeenCalled();
    expect(line()?.words).toBe("Phone line: Ready");
    stop();
  });
});
