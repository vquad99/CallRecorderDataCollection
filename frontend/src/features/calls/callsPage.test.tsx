// The phone-calls page (D-102): figures from the platform's own call records, TxContact's own
// traffic count (or why it is not available), and every call linked to its task.
// Requirements: TEL-018, DASH-001, GEN-004
import { screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { fakeApi, renderAt, signedInAs } from "../../test/fakeApi";
import { ALL_PERMISSIONS, worldHandlers } from "../../test/world";

afterEach(() => vi.unstubAllGlobals());

describe("phone calls page", () => {
  it("shows the call figures, why TxContact's count is missing, and links each call", async () => {
    fakeApi(signedInAs(ALL_PERMISSIONS, worldHandlers()));
    renderAt("/calls");
    expect(await screen.findByText("Calls per day", {}, { timeout: 5000 })).toBeInTheDocument();
    expect(screen.getByText("50% of calls")).toBeInTheDocument();
    expect(screen.getByText("Busiest hour: 11:00 (3 call(s)).")).toBeInTheDocument();
    expect(screen.getByText("TxContact refused the call")).toBeInTheDocument();
    expect(
      await screen.findByText(/Not available: TxContact refused the recording sign-in/),
    ).toBeInTheDocument();
    expect(await screen.findByRole("link", { name: "T000001" })).toHaveAttribute(
      "href",
      "/tasks/t1",
    );
  });

  it("hides TxContact's account-wide count from people who do not assign tasks", async () => {
    const api = fakeApi(
      signedInAs(
        ALL_PERMISSIONS.filter((p) => p !== "tasks.assign"),
        worldHandlers(),
      ),
    );
    renderAt("/calls");
    expect(await screen.findByText("Calls per day", {}, { timeout: 5000 })).toBeInTheDocument();
    expect(api.calls.some((c) => c.path.startsWith("/api/v1/telephony/provider-traffic"))).toBe(
      false,
    );
  });
});
