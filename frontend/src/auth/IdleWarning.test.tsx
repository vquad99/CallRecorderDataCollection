// Requirements: AUTH-005, AUTH-016
// Sign-out warning (D-122): sessions end after some minutes without a request. A minute before,
// the person is warned and can stay signed in; the warning's own clock is not activity.
import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { markApiActivity } from "../api/client";
import { fakeApi, ME } from "../test/fakeApi";
import { AuthContext, type AuthValue } from "./AuthContext";
import { IdleWarning } from "./IdleWarning";

const MINUTE = 60_000;

function show(refresh = vi.fn(() => Promise.resolve())) {
  const auth = { refresh } as unknown as AuthValue;
  render(
    <AuthContext.Provider value={auth}>
      <IdleWarning idleMinutes={10} />
    </AuthContext.Provider>,
  );
  return refresh;
}
const wait = (ms: number) => act(() => vi.advanceTimersByTimeAsync(ms));

beforeEach(() => {
  vi.useFakeTimers();
  vi.setSystemTime(new Date("2026-11-17T10:00:00Z"));
  markApiActivity();
});
afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe("sign-out warning", () => {
  it("warns one minute before the session ends, and not before", async () => {
    const { fetchMock } = fakeApi({});
    show();
    await wait(8 * MINUTE);
    expect(screen.queryByRole("alert")).toBeNull();
    await wait(MINUTE + 10_000);
    expect(screen.getByRole("alert")).toHaveTextContent("You will be signed out in 1 minute.");
    // Watching the clock asked the server nothing: it is not activity.
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("stays signed in when asked: one request, and the warning goes", async () => {
    const { calls } = fakeApi({ "GET /api/v1/auth/me": () => [200, ME] });
    show();
    await wait(9 * MINUTE + 10_000);
    fireEvent.click(screen.getByRole("button", { name: "Stay signed in" }));
    await wait(0);
    expect(calls.map((c) => c.path)).toEqual(["/api/v1/auth/me"]);
    expect(screen.queryByRole("alert")).toBeNull();
    // The request counts: another nine minutes pass before the next warning.
    await wait(8 * MINUTE);
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("any request to the server counts as activity", async () => {
    show();
    await wait(9 * MINUTE + 10_000);
    expect(screen.getByRole("alert")).toBeInTheDocument();
    markApiActivity(); // e.g. the page loaded a list
    await wait(5_000);
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("asks the server when the time is up, which leads to the sign-in page", async () => {
    const refresh = show();
    await wait(10 * MINUTE + 5_000);
    expect(refresh).toHaveBeenCalled();
  });
});
