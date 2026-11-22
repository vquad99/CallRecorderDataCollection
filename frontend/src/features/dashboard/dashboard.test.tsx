// Dashboard filters and phone-call figures (D-108), laid out as one screen (D-151).
// Requirements: DASH-001, DASH-002, DASH-004
import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { fakeApi, renderAt, signedInAs } from "../../test/fakeApi";
import { ALL_PERMISSIONS, DASHBOARD, worldHandlers } from "../../test/world";

const wait = { timeout: 5000 };

function open(answer: (url: URL) => unknown = () => DASHBOARD) {
  return fakeApi(
    signedInAs(ALL_PERMISSIONS, {
      ...worldHandlers(),
      "GET /api/v1/dashboard": (_b, url) => [200, answer(url)],
    }),
  );
}

/** A table row named by its first cell, cell by cell. */
const row = (table: HTMLElement, name: string | RegExp) =>
  Array.from(
    (within(table).getByRole("rowheader", { name }).closest("tr") as HTMLTableRowElement).cells,
  ).map((c) => c.textContent);

/** The dashboard requests, as "name=value&..." without the fixed parts. */
const asked = (calls: { path: string }[]) =>
  calls.filter((c) => c.path.startsWith("/api/v1/dashboard")).map((c) => c.path.split("?")[1]);

describe("dashboard filters", () => {
  it("narrows the figures by type, language, dialect, status and person", async () => {
    const { calls } = open((url) =>
      url.searchParams.get("mode") === "TELEPHONY"
        ? { ...DASHBOARD, recordings: 7, recorded_hours: 3 }
        : DASHBOARD,
    );
    renderAt("/dashboard");
    const filters = await screen.findByRole("group", { name: "Filters" }, wait);
    await screen.findByText("Moderator output", {}, wait);
    expect(asked(calls)).toEqual(["days=30"]);

    await userEvent.selectOptions(within(filters).getByLabelText("Recording type"), "TELEPHONY");
    await waitFor(() => expect(asked(calls).at(-1)).toBe("days=30&mode=TELEPHONY"));
    // The lists come from the server: the languages and dialects spoken, the people at work.
    await userEvent.selectOptions(within(filters).getByLabelText("Language"), "hi");
    await userEvent.selectOptions(within(filters).getByLabelText("Dialect"), "Awadhi");
    await userEvent.selectOptions(within(filters).getByLabelText("Task status"), "APPROVED");
    await userEvent.selectOptions(within(filters).getByLabelText("Staff"), "u7");
    await waitFor(() =>
      expect(asked(calls).at(-1)).toBe(
        "days=30&mode=TELEPHONY&language=hi&dialect=Awadhi&status=APPROVED&staff_id=u7",
      ),
    );
    expect(within(filters).getByRole("option", { name: "Max Moderator" })).toBeInTheDocument();

    // One click takes every filter off again.
    await userEvent.click(within(filters).getByRole("button", { name: "Clear filters" }));
    await waitFor(() => expect(asked(calls).at(-1)).toBe("days=30"));
    expect(within(filters).queryByRole("button", { name: "Clear filters" })).toBeNull();
    expect(within(filters).getByLabelText("Recording type")).toHaveValue("");
  });

  it("takes chosen days instead of a period, and catches days the wrong way round", async () => {
    const { calls } = open();
    renderAt("/dashboard");
    await screen.findByText("Moderator output", {}, wait);
    expect(screen.queryByLabelText("From")).toBeNull();
    await userEvent.selectOptions(screen.getByLabelText("Period"), "custom");
    await userEvent.type(await screen.findByLabelText("From"), "2026-11-01");
    await userEvent.type(screen.getByLabelText("To"), "2026-11-10");
    await waitFor(() =>
      expect(asked(calls).at(-1)).toBe("days=30&date_from=2026-11-01&date_to=2026-11-10"),
    );
    const before = asked(calls).length;
    await userEvent.clear(screen.getByLabelText("To"));
    await userEvent.type(screen.getByLabelText("To"), "2026-10-20");
    expect(await screen.findByText("Must not be before the first day")).toBeInTheDocument();
    // Nothing was asked of the server for days that cannot be.
    expect(
      asked(calls)
        .slice(before)
        .some((q) => q?.includes("date_to=2026-10-20")),
    ).toBe(false);
  });

  it("waits for a typed year before asking for the days (Edge fills it with zeros first)", async () => {
    const { calls } = open();
    renderAt("/dashboard");
    await screen.findByText("Moderator output", {}, wait);
    await userEvent.selectOptions(screen.getByLabelText("Period"), "custom");
    const from = await screen.findByLabelText("From");
    fireEvent.change(screen.getByLabelText("To"), { target: { value: "2026-11-10" } });
    await waitFor(() => expect(asked(calls).at(-1)).toBe("days=30&date_to=2026-11-10"));
    const before = asked(calls).length;
    // The first day's year half typed: nothing asked, no error, and the figures stay.
    fireEvent.change(from, { target: { value: "0002-11-01" } });
    fireEvent.change(from, { target: { value: "0202-11-01" } });
    await new Promise((done) => setTimeout(done, 300));
    expect(asked(calls)).toHaveLength(before);
    expect(screen.queryByText("Must not be before the first day")).toBeNull();
    expect(screen.getByRole("group", { name: "Key figures" })).toBeInTheDocument();
    // The whole year: asked once.
    fireEvent.change(from, { target: { value: "2026-11-01" } });
    await waitFor(() =>
      expect(asked(calls).at(-1)).toBe("days=30&date_from=2026-11-01&date_to=2026-11-10"),
    );
    expect(asked(calls)).toHaveLength(before + 1);
  });

  it("opens the task list filtered to a queue that needs attention", async () => {
    open();
    const router = renderAt("/dashboard");
    const qc = await screen.findByRole("link", { name: /Waiting for audio QC/ }, wait);
    expect(qc).toHaveAttribute("href", "/tasks?status=AUDIO_QC");
    expect(screen.getByRole("link", { name: /Tasks on hold/ })).toHaveAttribute(
      "href",
      "/tasks?status=ON_HOLD",
    );
    // Sent back by QC for a new signed consent form (D-146).
    expect(screen.getByRole("link", { name: /Consent forms to fix/ })).toHaveAttribute(
      "href",
      "/tasks?status=CONSENT_FIX",
    );
    // Recording problems are not task statuses: no link that would show the wrong list.
    expect(screen.queryByRole("link", { name: /Processing failed/ })).toBeNull();
    await userEvent.click(qc);
    expect(router.state.location.search).toBe("?status=AUDIO_QC");
  });

  it("shows managers the phone calls, and offers no person filter to others", async () => {
    open();
    renderAt("/dashboard");
    const card = (await screen.findByRole("heading", { name: "Phone calls" }, wait)).closest(
      "section",
    ) as HTMLElement;
    expect(card).toHaveTextContent("Placed12");
    expect(card).toHaveTextContent("Recorded9");
    expect(card).toHaveTextContent("Could not be placed2");
    expect(card).toHaveTextContent("Waiting for a person1");
    expect(within(card).getByRole("link", { name: "Phone calls" })).toHaveAttribute(
      "href",
      "/calls",
    );
  });

  it("shows effective speech and the completed hours each project counts (D-148)", async () => {
    open(() => ({ ...DASHBOARD, effective_pending: 2 }));
    renderAt("/dashboard");
    const figures = await screen.findByRole("group", { name: "Key figures" }, wait);
    const figure = (label: string) =>
      within(figures).getByText(label).closest(".figline__item") as HTMLElement;
    expect(figure("Completed")).toHaveTextContent("6.0 h");
    expect(figure("Completed")).toHaveTextContent("as each project counts it");
    expect(figure("Recorded")).toHaveTextContent("30 recordings");
    expect(figure("Effective speech")).toHaveTextContent("9.4 h");
    // Face-to-face beside phone and both together, one row per figure (D-151).
    const modes = screen.getByRole("table", { name: "By recording type" });
    expect(row(modes, "Effective speech")).toEqual(["Effective speech", "5.6 h", "3.8 h", "9.4 h"]);
    expect(row(modes, "Completed")).toEqual(["Completed", "3.7 h", "2.3 h", "6.0 h"]);
    expect(row(modes, "Recordings")).toEqual(["Recordings", "18", "12", "30"]);
    expect(row(modes, "Daily target")).toEqual(["Daily target", "2 h", "2 h", "4 h"]);
    expect(
      screen.getByText(/2 recordings are still being measured and count no effective speech yet/),
    ).toBeInTheDocument();
  });

  it("shows the key figures as one line, and tasks, queues and audio QC as plain tables (D-154)", async () => {
    open();
    renderAt("/dashboard");
    const figures = await screen.findByRole("group", { name: "Key figures" }, wait);
    const figure = (label: string) =>
      within(figures).getByText(label).closest(".figline__item") as HTMLElement;
    expect(figure("Today")).toHaveTextContent("1.5 h of 4 h");
    expect(figure("Today")).toHaveTextContent("38% of the daily target");
    expect(figure("Tasks approved")).toHaveTextContent("22 / 40");
    expect(figure("Tasks approved")).toHaveTextContent("55% of all tasks");
    // The tasks by stage, each status named under its stage.
    const stages = screen.getByRole("table", { name: "Tasks by status" });
    expect(row(stages, "Approved")).toEqual(["Approved", "22", "55%"]);
    expect(row(stages, /^Waiting for QC or approval/)).toEqual([
      "Waiting for QC or approvalAudio QC 6",
      "6",
      "15%",
    ]);
    expect(row(stages, "In progress")).toEqual(["In progress", "4", "10%"]);
    expect(row(stages, /^Not started/)).toEqual(["Not startedAssigned 8", "8", "20%"]);
    expect(row(stages, "Total")).toEqual(["Total", "40", ""]);
    // Audio QC as one table: the decisions, and the automatic check of those waiting.
    const qc = screen.getByRole("table", { name: "Audio QC" });
    expect(within(qc).getByRole("rowgroup", { name: "QC decisions" })).toHaveTextContent(
      "QC decisions29Passed22Rejected1Waiting6",
    );
    expect(
      within(qc).getByRole("rowgroup", { name: "Automatic check of those waiting" }),
    ).toHaveTextContent("All checks passed4Listen and decide1Failed a check1");
    // The moderators, and the storage used (a key figure).
    expect(row(screen.getByRole("table", { name: "Moderator output" }), "Max Moderator")).toEqual([
      "Max Moderator",
      "30",
      "13 h",
    ]);
    expect(figure("Storage used")).toHaveTextContent("3.0 GB");
  });

  it("gives a client viewer the filters that are about the recordings only", async () => {
    open(() => ({
      ...DASHBOARD,
      view: "client",
      tasks_by_status: null,
      qc: null,
      queues: null,
      team: null,
      storage_bytes: null,
      calls: null,
      options: { languages: ["hi"], dialects: [] },
    }));
    renderAt("/dashboard");
    const filters = await screen.findByRole("group", { name: "Filters" }, wait);
    await screen.findByRole("heading", { name: "Collection progress" }, wait);
    expect(within(filters).getByLabelText("Recording type")).toBeInTheDocument();
    expect(within(filters).getByLabelText("Language")).toBeInTheDocument();
    expect(within(filters).queryByLabelText("Dialect")).toBeNull(); // none is spoken here
    expect(within(filters).queryByLabelText("Task status")).toBeNull();
    expect(within(filters).queryByLabelText("Staff")).toBeNull();
    expect(screen.queryByRole("heading", { name: "Phone calls" })).toBeNull();
    // Collection progress only: no tasks, queues, QC or people.
    expect(screen.getByRole("group", { name: "Key figures" })).toBeInTheDocument();
    for (const name of ["Tasks by status", "Needs attention", "Audio QC", "Moderator output"]) {
      expect(screen.queryByRole("region", { name })).toBeNull();
    }
  });

  it("keeps the filters and the key figures apart, and pairs sections of like height (D-158)", async () => {
    open();
    renderAt("/dashboard");
    const filters = await screen.findByRole("group", { name: "Filters" }, wait);
    const figures = await screen.findByRole("group", { name: "Key figures" }, wait);
    // Two sections of their own, the key figures right after the filters.
    expect(filters).not.toContainElement(figures);
    expect(figures).not.toContainElement(filters);
    expect(filters.nextElementSibling).toBe(figures);
    // One moderator: the tasks by status among the short tables, the moderators at the end.
    const sections = () =>
      Array.from(
        screen.getByRole("region", { name: "Moderator output" }).parentElement?.children ?? [],
      ).map((s) => s.querySelector("h2")?.textContent);
    expect(sections()).toEqual([
      "Hours per day",
      "By recording type",
      "Tasks by status",
      "Needs attention",
      "Audio QC",
      "Phone calls",
      "Moderator output",
    ]);
  });

  it("puts the tasks by status beside a long list of moderators (D-158)", async () => {
    const team = Array.from({ length: 12 }, (_, i) => ({
      name: `Moderator ${i + 1}`,
      recordings: 10,
      recorded_hours: 2,
    }));
    open(() => ({ ...DASHBOARD, team }));
    renderAt("/dashboard");
    const output = await screen.findByRole("region", { name: "Moderator output" }, wait);
    expect(
      Array.from(output.parentElement?.children ?? []).map(
        (s) => s.querySelector("h2")?.textContent,
      ),
    ).toEqual([
      "Hours per day",
      "By recording type",
      "Needs attention",
      "Audio QC",
      "Phone calls",
      "Tasks by status",
      "Moderator output",
    ]);
    // The first ten, and the button for the rest on the section's title bar.
    expect(within(output).queryByText("Moderator 11")).toBeNull();
    const showAll = within(output).getByRole("button", { name: "Show all (12)" });
    expect(
      within(output).getByRole("heading", { name: "Moderator output" }).parentElement,
    ).toContainElement(showAll);
    await userEvent.click(showAll);
    expect(within(output).getByText("Moderator 12")).toBeInTheDocument();
  });

  it("names the chart's unit as its axis does: minutes when no day reaches an hour (D-158)", async () => {
    open(() => ({
      ...DASHBOARD,
      view: "worker",
      target_hours_per_day: 0,
      daily: DASHBOARD.daily.map((d) => ({ ...d, recorded_hours: 0.1, approved_hours: 0.05 })),
      queues: null,
      team: null,
      calls: null,
      options: { languages: ["hi"], dialects: [] },
    }));
    renderAt("/dashboard");
    const chart = await screen.findByRole("figure", { name: "Minutes per day" }, wait);
    expect(screen.queryByRole("heading", { name: "Hours per day" })).toBeNull();
    // The busiest day is 6 minutes: an axis of plain minutes up to 10, no other unit on it.
    const ticks = Array.from(chart.querySelectorAll("text")).map((t) => t.textContent);
    expect(ticks).toEqual(expect.arrayContaining(["0", "5", "10"]));
    expect(ticks.some((t) => /min|h$/.test(t ?? ""))).toBe(false);
    // Without moderators, the tasks by status sit beside audio QC.
    const grid = screen.getByRole("region", { name: "Audio QC" }).parentElement;
    expect(Array.from(grid?.children ?? []).map((s) => s.querySelector("h2")?.textContent)).toEqual(
      ["Minutes per day", "By recording type", "Tasks by status", "Audio QC"],
    );
  });
});
