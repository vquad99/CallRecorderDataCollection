// Requirements: AUTH-005, AUTH-016
// Sign-out warning (D-122): sessions end after some minutes without a request. Two minutes before
// the page's count ends (the server notes use at most once a minute, so its count can end a minute
// earlier), the person is warned and can stay signed in; the warning's own clock is not activity,
// and neither is its check when the time is up.
import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { BACKGROUND_HEADER, markApiActivity } from "../api/client";
import { fakeApi, ME } from "../test/fakeApi";
import { AuthContext, type AuthValue } from "./AuthContext";
import { IdleWarning } from "./IdleWarning";

const MINUTE = 60_000;
const EXPIRED = [401, { error: { code: "SESSION_EXPIRED", message: "expired" } }] as [
  number,
  unknown,
];

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
  it("warns two minutes before the page's count ends, and not before", async () => {
    const { fetchMock } = fakeApi({});
    show();
    await wait(7 * MINUTE + 55_000);
    expect(screen.queryByRole("alert")).toBeNull();
    await wait(10_000);
    expect(screen.getByRole("alert")).toHaveTextContent(
      "You will be signed out in under 2 minutes.",
    );
    // Watching the clock asked the server nothing: it is not activity.
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("stays signed in when asked: one request, and the warning goes", async () => {
    const { calls } = fakeApi({ "GET /api/v1/auth/me": () => [200, ME] });
    const refresh = show();
    await wait(8 * MINUTE + 10_000);
    fireEvent.click(screen.getByRole("button", { name: "Stay signed in" }));
    await wait(0);
    expect(calls.map((c) => c.path)).toEqual(["/api/v1/auth/me"]);
    expect(screen.queryByRole("alert")).toBeNull();
    expect(refresh).not.toHaveBeenCalled();
    // The request counts: another eight minutes pass before the next warning.
    await wait(7 * MINUTE);
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("a session that has already ended leads to the sign-in page, not an error", async () => {
    fakeApi({ "GET /api/v1/auth/me": () => EXPIRED });
    const refresh = show();
    await wait(9 * MINUTE);
    fireEvent.click(screen.getByRole("button", { name: "Stay signed in" }));
    await wait(0);
    expect(refresh).toHaveBeenCalledOnce();
    expect(screen.getByRole("alert")).not.toHaveTextContent("expired");
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
    const { fetchMock } = fakeApi({ "GET /api/v1/auth/me": () => EXPIRED });
    const refresh = show();
    await wait(10 * MINUTE + 5_000);
    expect(refresh).toHaveBeenCalledOnce();
    // A background request: asking does not keep the session alive.
    const init = fetchMock.mock.calls[0]?.[1] as RequestInit;
    expect((init.headers as Record<string, string>)[BACKGROUND_HEADER]).toBe("1");
  });

  it("leaves a session another tab keeps alive alone, and asks only once a minute", async () => {
    const { calls } = fakeApi({ "GET /api/v1/auth/me": () => [200, ME] });
    const refresh = show();
    await wait(10 * MINUTE + 5_000);
    expect(calls).toHaveLength(1);
    await wait(30_000);
    expect(calls).toHaveLength(1);
    await wait(30_000);
    expect(calls).toHaveLength(2);
    expect(refresh).not.toHaveBeenCalled();
    expect(screen.queryByRole("alert")).toBeNull();
  });
});
