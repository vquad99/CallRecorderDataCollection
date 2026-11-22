// The dashboards' shared figures and charts (D-151): tasks grouped by stage, a donut whose legend
// is a table, a split bar with its counts as text, tables in sections, and the day chart's axis;
// and D-158's tables in sections: stage parts kept whole, numbers beside their bars, a dash for an
// empty cell, a table that runs edge to edge.
// Requirements: DASH-001
import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { DataTable } from "../DataTable";
import {
  CellBar,
  DayChart,
  Donut,
  KeyTable,
  Kpi,
  KpiStrip,
  MatrixTable,
  ShareTable,
  SplitBar,
} from "./Charts";
import { stageParts } from "./stages";

describe("dashboard figures", () => {
  it("groups task statuses into the Progress tab's six stages", () => {
    const parts = stageParts({
      APPROVED: 5,
      AUDIO_QC: 3,
      ADMIN_REVIEW: 1,
      IN_PROGRESS: 2,
      ON_HOLD: 1,
      CONSENT_FIX: 1,
      ASSIGNED: 4,
      REJECTED: 0,
    });
    expect(parts.map((p) => [p.label, p.n, p.detail])).toEqual([
      ["Approved", 5, undefined],
      ["Waiting for QC or approval", 4, "Audio QC 3 · Admin review 1"],
      ["In progress", 4, "In progress 2 · On hold 1 · Consent form to fix 1"],
      ["Not started", 4, "Assigned 4"],
    ]);
  });

  it("gives a donut's numbers as a table, and says when there is nothing", () => {
    const { rerender } = render(
      <Donut
        label="Tasks by status"
        unit="tasks"
        emptyText="No tasks yet."
        parts={[
          { key: "a", label: "Approved", n: 3, color: "green" },
          { key: "b", label: "Rejected", n: 1, color: "red" },
        ]}
      />,
    );
    const legend = screen.getByRole("table", { name: "Tasks by status" });
    expect(
      within(legend)
        .getAllByRole("row")
        .slice(1)
        .map((r) => r.textContent),
    ).toEqual(["Approved375%", "Rejected125%"]);
    rerender(<Donut label="Tasks by status" unit="tasks" emptyText="No tasks yet." parts={[]} />);
    expect(screen.getByText("No tasks yet.")).toBeInTheDocument();
    expect(screen.queryByRole("table")).toBeNull();
  });

  it("lists a split bar's parts with their counts", () => {
    render(
      <SplitBar
        title="QC decisions"
        parts={[
          { key: "p", label: "Passed", n: 8, color: "green" },
          { key: "w", label: "Waiting", n: 2, color: "orange" },
        ]}
      />,
    );
    expect(screen.getByText("QC decisions")).toHaveTextContent("QC decisions10");
    expect(screen.getAllByRole("listitem").map((li) => li.textContent)).toEqual([
      "Passed8",
      "Waiting2",
    ]);
  });

  it("names each section of a table and says why an empty one is empty", () => {
    render(
      <MatrixTable<{ key: string; n: number }>
        label="Reasons"
        head="Reason"
        columns={[{ key: "n", label: "Count", num: true, cell: (r) => r.n }]}
        sections={[
          { key: "a", title: "Cancelled", rows: [{ key: "No answer", n: 2 }] },
          { key: "b", title: "Problems", rows: [], empty: "None in this period." },
        ]}
        rowKey={(r) => r.key}
        rowLabel={(r) => r.key}
      />,
    );
    const cancelled = screen.getByRole("rowgroup", { name: "Cancelled" });
    expect(
      within(cancelled).getByRole("rowheader", { name: "No answer" }).closest("tr"),
    ).toHaveTextContent("No answer2");
    expect(
      within(screen.getByRole("rowgroup", { name: "Problems" })).getByText("None in this period."),
    ).toBeInTheDocument();
  });

  it("puts round numbers on the day chart's axis", () => {
    render(
      <DayChart
        title="Hours per day"
        days={[
          { day: "2026-11-01", h: 17.7 },
          { day: "2026-11-02", h: 4 },
        ]}
        series={[{ label: "Recorded", className: "series--recorded", value: (d) => d.h }]}
        columns={[{ label: "Recorded", value: (d) => d.h }]}
        emptyText="Nothing yet."
      />,
    );
    const ticks = Array.from(document.querySelectorAll("text.chart__tick")).map(
      (t) => t.textContent,
    );
    expect(ticks.slice(0, 3)).toEqual(["0", "10", "20"]);
  });

  it("writes an axis under an hour in minutes, and under a minute in seconds, with room for it", () => {
    const chart = (busiest: number) => (
      <DayChart
        title="Hours per day"
        days={[
          { day: "2026-11-01", h: busiest },
          { day: "2026-11-02", h: busiest / 4 },
        ]}
        series={[{ label: "Recorded", className: "series--recorded", value: (d) => d.h }]}
        columns={[{ label: "Recorded", value: (d) => d.h }]}
        emptyText="Nothing yet."
      />
    );
    /** The axis' numbers, each with how far right of the drawing's left edge it ends. */
    const axis = () =>
      Array.from(document.querySelectorAll('text.chart__tick[text-anchor="end"]')).map((t) => ({
        text: t.textContent ?? "",
        x: Number(t.getAttribute("x")),
      }));
    // 0.02 h a day is 1.2 minutes: not "0.025" and "0.0125" cut off at the edge.
    const { rerender } = render(chart(0.02));
    expect(axis().map((t) => t.text)).toEqual(["0", "1 min", "2 min"]);
    // Each number is written right-aligned at x and needs about 7 px a character.
    for (const t of axis()) expect(t.x).toBeGreaterThanOrEqual(6.5 * t.text.length);
    rerender(chart(0.5));
    expect(axis().map((t) => t.text)).toEqual(["0", "25 min", "50 min"]);
    rerender(chart(0.004)); // about 14 seconds
    expect(axis().map((t) => t.text)).toEqual(["0", "10 s", "20 s"]);
    for (const t of axis()) expect(t.x).toBeGreaterThanOrEqual(6.5 * t.text.length);
  });

  it("shows a key figure's bar to its target", () => {
    render(
      <KpiStrip label="Key figures">
        <Kpi
          icon="clock"
          label="Today"
          value="3 h"
          meter={{ percent: 150, label: "Today of the daily target", text: "150%" }}
        />
      </KpiStrip>,
    );
    const figures = screen.getByRole("group", { name: "Key figures" });
    expect(figures).toHaveTextContent("Today3 h150%");
    // The bar stops at its end; the text says how far past it.
    expect(
      within(figures).getByRole("progressbar", { name: "Today of the daily target" }),
    ).toHaveAttribute("aria-valuenow", "100");
  });
});

describe("tables in sections (D-158)", () => {
  it("keeps each part of a stage on one line, breaking only between parts", () => {
    render(
      <ShareTable
        label="Tasks by status"
        head="Stage"
        countHead="Tasks"
        emptyText="No tasks yet."
        parts={stageParts({ AUDIO_QC: 48, ADMIN_REVIEW: 12 })}
      />,
    );
    const stage = screen.getByRole("rowheader", { name: /Waiting for QC or approval/ });
    expect(stage).toHaveTextContent("Waiting for QC or approvalAudio QC 48 · Admin review 12");
    expect(Array.from(stage.querySelectorAll(".nowrap")).map((s) => s.textContent)).toEqual([
      "Audio QC 48",
      "Admin review 12",
    ]);
  });

  it("writes a number after its bar, not over it", () => {
    render(
      <CellBar value={26} max={52}>
        26 h
      </CellBar>,
    );
    const n = screen.getByText("26 h");
    expect(n).toHaveClass("cellbar__n");
    const bar = n.previousElementSibling;
    expect(bar).toHaveAttribute("aria-hidden", "true");
    expect(bar?.firstElementChild).toHaveStyle({ width: "50%" });
  });

  it("shows a dash in a cell with nothing in it", () => {
    render(
      <>
        <KeyTable
          label="Phone calls"
          rows={[
            { label: "Placed", value: 3 },
            { label: "Last call", value: null },
          ]}
        />
        <MatrixTable<{ key: string; n: number | null }>
          label="Reasons"
          head="Reason"
          columns={[{ key: "n", label: "Count", num: true, cell: (r) => r.n }]}
          sections={[{ key: "a", title: "Cancelled", rows: [{ key: "No answer", n: null }] }]}
          rowKey={(r) => r.key}
          rowLabel={(r) => r.key}
        />
      </>,
    );
    expect(screen.getByRole("rowheader", { name: "Last call" }).closest("tr")).toHaveTextContent(
      "Last call-",
    );
    expect(screen.getByRole("rowheader", { name: "Placed" }).closest("tr")).toHaveTextContent(
      "Placed3",
    );
    expect(screen.getByRole("rowheader", { name: "No answer" }).closest("tr")).toHaveTextContent(
      "No answer-",
    );
  });

  it("lets a table inside a section run edge to edge when asked", () => {
    const { rerender } = render(
      <DataTable label="Device details">
        <tbody>
          <tr>
            <td>Samsung</td>
          </tr>
        </tbody>
      </DataTable>,
    );
    const wrap = () => screen.getByRole("table", { name: "Device details" }).parentElement;
    expect(wrap()).toHaveClass("table-wrap");
    expect(wrap()).not.toHaveClass("bleed");
    rerender(
      <DataTable label="Device details" bleed>
        <tbody>
          <tr>
            <td>Samsung</td>
          </tr>
        </tbody>
      </DataTable>,
    );
    expect(wrap()).toHaveClass("table-wrap", "bleed");
  });
});
