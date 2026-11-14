// The phone-calls page (D-102, D-103): figures from the platform's own call records (calls, the
// way from call to approval, today against the target, phone tasks, checks and QC, the checklist),
// TxContact's own traffic count (or why it is not available), the calls as a spreadsheet, and
// every call linked to its task.
// Requirements: TEL-018, DASH-001, GEN-004
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { fakeApi, renderAt, signedInAs } from "../../test/fakeApi";
import { ALL_PERMISSIONS, CALL_ROW, worldHandlers } from "../../test/world";

afterEach(() => vi.unstubAllGlobals());

describe("phone calls page", () => {
  it("shows the call figures, why TxContact's count is missing, and links each call", async () => {
    fakeApi(signedInAs(ALL_PERMISSIONS, worldHandlers()));
    renderAt("/calls");
    expect(await screen.findByText("Calls per day", {}, { timeout: 5000 })).toBeInTheDocument();
    expect(screen.getByText("50% of calls")).toBeInTheDocument();
    expect(screen.getByText("Busiest hour: 11:00 (3 call(s)).")).toBeInTheDocument();
    expect(screen.getByText("TxContact refused the call")).toBeInTheDocument();
    // Today against the daily target, and tasks nobody has called yet.
    expect(screen.getByText(/4% of the daily target \(10\.0 h\)/)).toBeInTheDocument();
    expect(screen.getByText("1 task(s) called more than once")).toBeInTheDocument();
    // From call to approval: every step with its share of the calls started.
    const funnel = screen.getByRole("region", { name: "From call to approval" });
    expect(within(funnel).getByText("Recording stored")).toBeInTheDocument();
    expect(within(funnel).getByText("75%")).toBeInTheDocument();
    expect(within(funnel).getAllByText("50%")).toHaveLength(2);
    // The checklist on closed calls, and the phone tasks by status.
    expect(screen.getByText("I am muted and listening")).toBeInTheDocument();
    expect(
      within(screen.getByRole("region", { name: "Phone tasks by status" })).getByText("Approved"),
    ).toBeInTheDocument();
    expect(
      await screen.findByText(/Not available: TxContact refused the recording sign-in/),
    ).toBeInTheDocument();
    expect(await screen.findByRole("link", { name: "T000001" })).toHaveAttribute(
      "href",
      "/tasks/t1",
    );
    // The call's length and its recording's length.
    expect(screen.getAllByText("12.0 min")).toHaveLength(2);
  });

  it("marks a call that was left open and downloads the calls as a spreadsheet", async () => {
    vi.stubGlobal(
      "URL",
      Object.assign(URL, { createObjectURL: () => "blob:x", revokeObjectURL: () => {} }),
    );
    const api = fakeApi(
      signedInAs(ALL_PERMISSIONS, {
        ...worldHandlers(),
        "GET /api/v1/calls": () => [
          200,
          {
            items: [{ ...CALL_ROW, state: "DIALLING", stale: true, closed_at: null }],
            total: 1,
            page: 1,
            page_size: 25,
          },
        ],
        "GET /api/v1/calls/export": () => [200, "started,closed\n"],
      }),
    );
    renderAt("/calls");
    expect(await screen.findByText("Left open", {}, { timeout: 5000 })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Download calls (CSV)" }));
    await waitFor(() =>
      expect(api.calls.some((c) => c.path === "/api/v1/calls/export?days=30")).toBe(true),
    );
  });

  it("starts the list again at its first page when the project changes", async () => {
    const api = fakeApi(
      signedInAs(ALL_PERMISSIONS, {
        ...worldHandlers(),
        "GET /api/v1/calls": (_, url) => [
          200,
          {
            items: [CALL_ROW],
            total: 60,
            page: Number(url.searchParams.get("page") ?? 1),
            page_size: 25,
          },
        ],
      }),
    );
    renderAt("/calls");
    await userEvent.click(await screen.findByRole("button", { name: /Next/ }, { timeout: 5000 }));
    await waitFor(() => expect(api.calls.some((c) => c.path.includes("page=2"))).toBe(true));
    await userEvent.selectOptions(screen.getByLabelText("Project"), "p1");
    await waitFor(() =>
      expect(
        api.calls.some((c) => c.path.includes("project_id=p1") && c.path.includes("page=1")),
      ).toBe(true),
    );
    expect(
      api.calls.some((c) => c.path.includes("project_id=p1") && c.path.includes("page=2")),
    ).toBe(false);
  });

  it("gives a moderator a plain list of their own calls, and no figures (D-104)", async () => {
    const api = fakeApi(
      signedInAs(
        ALL_PERMISSIONS.filter((p) => p !== "tasks.assign"),
        worldHandlers(),
      ),
    );
    renderAt("/calls");
    expect(
      await screen.findByRole("heading", { name: "My phone calls" }, { timeout: 5000 }),
    ).toBeInTheDocument();
    expect(await screen.findByRole("link", { name: "T000001" })).toHaveAttribute(
      "href",
      "/tasks/t1",
    );
    expect(screen.queryByText("Calls per day")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Download calls (CSV)" })).not.toBeInTheDocument();
    for (const path of [
      "/api/v1/telephony/analytics",
      "/api/v1/telephony/provider-traffic",
      "/api/v1/calls/export",
    ]) {
      expect(api.calls.some((c) => c.path.startsWith(path))).toBe(false);
    }
  });
});
