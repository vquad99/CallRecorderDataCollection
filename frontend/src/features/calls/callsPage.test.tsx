// The phone-calls page (D-102, D-103): figures from the platform's own call records (calls, the
// way from call to approval, today against the target, phone tasks, checks and QC, the checklist),
// TxContact's own traffic count (or why it is not available), the calls as a spreadsheet, and
// on its own tab every call linked to its task. One dashboard of figures and tables (D-151).
// Requirements: TEL-018, DASH-001, GEN-004
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { fakeApi, renderAt, signedInAs } from "../../test/fakeApi";
import {
  ALL_PERMISSIONS,
  CALL_ANALYTICS,
  CALL_ROW,
  PROJECT,
  worldHandlers,
} from "../../test/world";

afterEach(() => vi.unstubAllGlobals());

describe("phone calls page", () => {
  it("shows the call figures, why TxContact's count is missing, and links each call", async () => {
    fakeApi(signedInAs(ALL_PERMISSIONS, worldHandlers()));
    renderAt("/calls");
    expect(await screen.findByText("Calls per day", {}, { timeout: 5000 })).toBeInTheDocument();
    expect(screen.getByText("50% of calls")).toBeInTheDocument();
    expect(screen.getByText("Busiest hour: 11:00 (3 calls).")).toBeInTheDocument();
    expect(screen.getByText("TxContact refused the call")).toBeInTheDocument();
    // Today against the daily target, and tasks nobody has called yet.
    expect(screen.getByText(/4% of the daily target \(10\.0 h\)/)).toBeInTheDocument();
    expect(screen.getByText("1 task called more than once")).toBeInTheDocument();
    expect(screen.getByText("1.3 calls for each task")).toBeInTheDocument();
    // The times on the page and in the CSV are India time, and say so.
    expect(
      screen.getByText(/Times are in India time \(IST\), here and in the CSV\./),
    ).toBeInTheDocument();
    // From call to approval: every step with its share of the calls started.
    const funnel = screen.getByRole("region", { name: "From call to approval" });
    expect(within(funnel).getByText("Recording stored")).toBeInTheDocument();
    expect(within(funnel).getByText("75%")).toBeInTheDocument();
    expect(within(funnel).getAllByText("50%")).toHaveLength(2);
    expect(
      within(funnel).getByRole("rowheader", { name: "Recording stored" }).closest("tr"),
    ).toHaveTextContent("Recording stored250%");
    // The key figures as one line (D-154).
    const figures = screen.getByRole("group", { name: "Call figures" });
    expect(within(figures).getByText("Tasks not called yet")).toBeInTheDocument();
    // Calls per hour as one matrix: our count, and TxContact's beside it (D-154).
    const byHour = screen.getByRole("table", { name: "Calls by hour of the day" });
    expect(within(byHour).getByRole("columnheader", { name: "11" })).toBeInTheDocument();
    expect(
      within(byHour).getByRole("rowheader", { name: "Calls made" }).closest("tr"),
    ).toHaveTextContent(/3/);
    // The counted lists as tables with a section per kind and a row per reason.
    const problems = screen.getByRole("rowgroup", { name: "Problems getting the recording" });
    expect(
      within(problems).getByRole("rowheader", { name: "TxContact refused the call" }).closest("tr"),
    ).toHaveTextContent("TxContact refused the call1");
    const cancelled = screen.getByRole("rowgroup", { name: "Why calls were cancelled" });
    expect(within(cancelled).getByRole("rowheader", { name: "No answer" })).toBeInTheDocument();
    expect(
      within(screen.getByRole("rowgroup", { name: "QC decisions on call recordings" })).getByRole(
        "rowheader",
        { name: "Passed" },
      ),
    ).toBeInTheDocument();
    // The phone tasks by status (the old call checklist is no longer shown, D-127).
    expect(screen.queryByText("I am muted and listening")).not.toBeInTheDocument();
    expect(
      within(screen.getByRole("region", { name: "Phone tasks by status" })).getByText("Approved"),
    ).toBeInTheDocument();
    expect(
      await screen.findByText(/Not available: TxContact refused the recording sign-in/),
    ).toBeInTheDocument();
    // Every call is on its own tab, so the figures page stays short.
    expect(screen.queryByRole("link", { name: "T000001" })).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("tab", { name: "All calls" }));
    expect(screen.getByRole("tab", { name: "All calls" })).toHaveAttribute("aria-selected", "true");
    expect(await screen.findByRole("link", { name: "T000001" })).toHaveAttribute(
      "href",
      "/tasks/t1",
    );
    // The call's length and its recording's length.
    expect(screen.getAllByText("12.0 min")).toHaveLength(2);
    expect(screen.queryByText("Calls per day")).not.toBeInTheDocument();
  });

  it("shows the first ten moderators and the rest on request", async () => {
    const many = Array.from({ length: 12 }, (_, i) => ({
      moderator_id: `m${i}`,
      name: `Moderator ${i + 1}`,
      calls: 1,
      recorded: 1,
      failed: 0,
      recorded_minutes: 1,
      avg_call_minutes: 1,
    }));
    fakeApi(
      signedInAs(ALL_PERMISSIONS, {
        ...worldHandlers(),
        "GET /api/v1/telephony/analytics": () => [200, { ...CALL_ANALYTICS, by_moderator: many }],
      }),
    );
    renderAt("/calls");
    const card = await screen.findByRole("region", { name: "By moderator" }, { timeout: 5000 });
    expect(within(card).queryByText("Moderator 11")).not.toBeInTheDocument();
    // The button sits on the section's title bar, beside its title (D-158).
    const showAll = within(card).getByRole("button", { name: "Show all (12)" });
    expect(
      within(card).getByRole("heading", { name: "By moderator" }).parentElement,
    ).toContainElement(showAll);
    await userEvent.click(showAll);
    expect(within(card).getByText("Moderator 12")).toBeInTheDocument();
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
    renderAt("/calls?view=calls");
    expect(await screen.findByText("Left open", {}, { timeout: 5000 })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Download calls (CSV)" }));
    await waitFor(() =>
      expect(api.calls.some((c) => c.path === "/api/v1/calls/export?days=30")).toBe(true),
    );
  });

  it("says why the calls CSV could not be made", async () => {
    fakeApi(
      signedInAs(ALL_PERMISSIONS, {
        ...worldHandlers(),
        "GET /api/v1/calls/export": () => [
          422,
          {
            error: {
              code: "TOO_LARGE",
              message:
                "More than 20,000 calls in this period: choose a project or a shorter period",
              request_id: "r1",
            },
          },
        ],
      }),
    );
    renderAt("/calls");
    await userEvent.click(
      await screen.findByRole("button", { name: "Download calls (CSV)" }, { timeout: 5000 }),
    );
    expect(
      await screen.findByText(
        "More than 20,000 calls in this period: choose a project or a shorter period",
      ),
    ).toBeInTheDocument();
  });

  it("offers every project in the picker, not only the newest hundred", async () => {
    const newest = Array.from({ length: 100 }, (_, i) => ({
      ...PROJECT,
      id: `n${i}`,
      code: `NEW${i}`,
      name: `Newer ${i}`,
    }));
    const oldest = { ...PROJECT, id: "old", code: "OLDEST", name: "The first project" };
    const api = fakeApi(
      signedInAs(ALL_PERMISSIONS, {
        ...worldHandlers(),
        "GET /api/v1/projects": (_b, url) => [
          200,
          {
            items: url.searchParams.get("page") === "2" ? [oldest] : newest,
            total: 101,
            page: Number(url.searchParams.get("page") ?? 1),
            page_size: 100,
          },
        ],
      }),
    );
    renderAt("/calls");
    const picker = await screen.findByLabelText("Project", {}, { timeout: 5000 });
    expect(
      await within(picker).findByRole("option", { name: "OLDEST · The first project" }),
    ).toBeInTheDocument();
    expect(within(picker).getAllByRole("option")).toHaveLength(102); // with "All my projects"
    expect(
      api.calls.some((c) => c.path.startsWith("/api/v1/projects?") && c.path.includes("page=2")),
    ).toBe(true);
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
    renderAt("/calls?view=calls");
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

  it("gives each kind of reason a section of its own and writes '-' for an hour with no call (D-158)", async () => {
    fakeApi(signedInAs(ALL_PERMISSIONS, worldHandlers()));
    renderAt("/calls");
    const cancelled = await screen.findByRole(
      "region",
      { name: "Cancelled calls and recording problems" },
      { timeout: 5000 },
    );
    for (const name of ["Why calls were cancelled", "Problems getting the recording"]) {
      expect(within(cancelled).getByRole("rowgroup", { name })).toBeInTheDocument();
    }
    const checks = screen.getByRole("region", { name: "Checks and QC decisions" });
    for (const name of [
      "Automatic audio check of call recordings",
      "QC decisions on call recordings",
    ]) {
      expect(within(checks).getByRole("rowgroup", { name })).toBeInTheDocument();
    }
    // The hours from the first call to the last: one without a call shows "-", never a dot.
    const made = within(screen.getByRole("table", { name: "Calls by hour of the day" }))
      .getByRole("rowheader", { name: "Calls made" })
      .closest("tr") as HTMLTableRowElement;
    expect(Array.from(made.cells).map((c) => c.textContent)).toEqual([
      "Calls made",
      "3",
      "-",
      "-",
      "-",
      "1",
    ]);
  });

  it("lists the calls in a section with its filter on the title bar, and the pages under it (D-158)", async () => {
    fakeApi(
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
    renderAt("/calls?view=calls");
    const list = await screen.findByRole("region", { name: "All calls" }, { timeout: 5000 });
    // The "Show" filter sits on the section's title bar, beside its title.
    const bar = within(list).getByRole("heading", { name: "All calls" }).parentElement;
    expect(bar).toContainElement(within(list).getByLabelText("Show"));
    // A stored recording has no reason: the column shows "-".
    const call = (await within(list).findByRole("link", { name: "T000001" })).closest("tr");
    expect(call?.lastElementChild).toHaveTextContent(/^-$/);
    // The pages are under the section, outside its frame.
    const pages = screen.getByRole("navigation", { name: "Pages" });
    expect(list).not.toContainElement(pages);
    expect(list.nextElementSibling).toBe(pages);
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
