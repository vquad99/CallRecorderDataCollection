// The Payments page (D-137): one tab per kind of person with totals, "No rate set" for a project
// without a rate, the filters and search sent to the server, the CSV download, and each project's
// rates changed in a window.
// Requirements: DASH-002, EXP-007, ROLE-003
import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { fakeApi, renderAt, signedInAs, type Handler } from "../../test/fakeApi";
import { ALL_PERMISSIONS, PARTICIPANT_PAY, RATES, worldHandlers } from "../../test/world";

afterEach(() => vi.unstubAllGlobals());

function open(extra: Record<string, Handler> = {}) {
  vi.stubGlobal(
    "URL",
    Object.assign(URL, { createObjectURL: () => "blob:x", revokeObjectURL: () => {} }),
  );
  return fakeApi(
    signedInAs(ALL_PERMISSIONS, {
      ...worldHandlers(),
      "GET /api/v1/payments/moderators/export": () => [200, "project,moderator\n"],
      "PUT /api/v1/payments/rates/p1": (body) => [200, { ...RATES, ...(body as object) }],
      ...extra,
    }),
  );
}

describe("payments page", () => {
  it("shows what each moderator earned, with totals", async () => {
    open();
    renderAt("/payments");
    const table = await screen.findByRole(
      "table",
      { name: "Moderator payments" },
      { timeout: 5000 },
    );
    const row = within(table).getByText("Mona Moderator").closest("tr") as HTMLElement;
    expect(within(row).getByText("25.50")).toBeInTheDocument();
    expect(within(row).getByText("₹2.00 / min")).toBeInTheDocument();
    expect(within(row).getByText("₹51.00")).toBeInTheDocument();
    expect(within(table).getByText("Total")).toBeInTheDocument();
  });

  it("shows participants' share, and No rate set where a project has no rate", async () => {
    open();
    renderAt("/payments?view=participants");
    const table = await screen.findByRole(
      "table",
      { name: "Participant payments" },
      { timeout: 5000 },
    );
    const row = within(table).getByText("P000001").closest("tr") as HTMLElement;
    expect(within(row).getByText("Asha")).toBeInTheDocument();
    expect(within(row).getAllByText("No rate set")).toHaveLength(2);
    expect(within(table).getByText("Not in it: 12.75 min with no rate set")).toBeInTheDocument();
  });

  it("sends the project, the approval days and the search, and downloads the same choice", async () => {
    const { calls } = open();
    renderAt("/payments");
    await screen.findByText("Mona Moderator", {}, { timeout: 5000 });
    await userEvent.selectOptions(screen.getByLabelText("Project"), "p1");
    await userEvent.type(screen.getByLabelText("Approved from"), "2026-11-01");
    await userEvent.type(screen.getByLabelText("Approved to"), "2026-11-15");
    await userEvent.type(screen.getByLabelText("Search by name"), "mona");
    const asked = "project_id=p1&date_from=2026-11-01&date_to=2026-11-15&search=mona";
    await waitFor(() =>
      expect(calls.some((c) => c.path === `/api/v1/payments/moderators?${asked}`)).toBe(true),
    );
    await userEvent.click(screen.getByRole("button", { name: "Download CSV" }));
    await waitFor(() =>
      expect(calls.some((c) => c.path === `/api/v1/payments/moderators/export?${asked}`)).toBe(
        true,
      ),
    );
  });

  it("does not ask for days the wrong way round", async () => {
    open();
    renderAt("/payments");
    await screen.findByText("Mona Moderator", {}, { timeout: 5000 });
    await userEvent.type(screen.getByLabelText("Approved from"), "2026-11-15");
    await userEvent.type(screen.getByLabelText("Approved to"), "2026-11-01");
    expect(await screen.findByText("Must not be before the first day")).toBeInTheDocument();
    expect(screen.queryByRole("table", { name: "Moderator payments" })).toBeNull();
  });

  it("waits for a typed year before asking for the days (Edge fills it with zeros first)", async () => {
    const { calls } = open();
    renderAt("/payments");
    await screen.findByText("Mona Moderator", {}, { timeout: 5000 });
    const asked = () => calls.filter((c) => c.path.startsWith("/api/v1/payments/moderators?"));
    fireEvent.change(screen.getByLabelText("Approved to"), { target: { value: "2026-11-10" } });
    await waitFor(() => expect(asked()).toHaveLength(1));
    // The first day's year half typed: nothing asked, no error, and the table stays.
    for (const halfTyped of ["0002-11-01", "0020-11-01", "0202-11-01"])
      fireEvent.change(screen.getByLabelText("Approved from"), { target: { value: halfTyped } });
    await new Promise((done) => setTimeout(done, 400));
    expect(asked()).toHaveLength(1);
    expect(screen.queryByText("Must not be before the first day")).toBeNull();
    expect(screen.getByRole("table", { name: "Moderator payments" })).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Approved from"), { target: { value: "2026-11-01" } });
    await waitFor(() => expect(asked()).toHaveLength(2));
    expect(asked()[1]?.path).toBe(
      "/api/v1/payments/moderators?date_from=2026-11-01&date_to=2026-11-10",
    );
  });

  it("shows a long list fifty rows a page, with the totals of every row", async () => {
    const rows = Array.from({ length: 120 }, (_, i) => ({
      ...PARTICIPANT_PAY.rows[0],
      participant_id: `a${i}`,
      participant_code: `P${String(i + 1).padStart(6, "0")}`,
      name: `Person ${i + 1}`,
    }));
    const totals = { ...PARTICIPANT_PAY.totals, count: 120 };
    const { calls } = open({
      "GET /api/v1/payments/participants": () => [200, { ...PARTICIPANT_PAY, rows, totals }],
    });
    renderAt("/payments?view=participants");
    const table = () => screen.getByRole("table", { name: "Participant payments" });
    const pages = () => screen.getByRole("navigation", { name: "Pages" });
    const codes = () =>
      within(table())
        .getAllByText(/^P\d{6}$/)
        .map((c) => c.textContent);
    await screen.findByRole("table", { name: "Participant payments" }, { timeout: 5000 });
    expect(codes()).toHaveLength(50);
    expect(codes()[0]).toBe("P000001");
    // The totals are of every row, not of the page.
    expect(
      within(table()).getByRole("rowheader", { name: "Total" }).closest("tr"),
    ).toHaveTextContent("120");
    expect(pages()).toHaveTextContent("Page 1 of 3 (120 total)");
    await userEvent.click(within(pages()).getByRole("button", { name: /Next/ }));
    await userEvent.click(within(pages()).getByRole("button", { name: /Next/ }));
    expect(codes()).toEqual(rows.slice(100).map((r) => r.participant_code));
    // The rows come once: a page is not asked for again.
    expect(calls.filter((c) => c.path.startsWith("/api/v1/payments/participants"))).toHaveLength(1);
    // A search starts again at the first page.
    await userEvent.type(screen.getByLabelText("Search by code or name"), "Person");
    await waitFor(() =>
      expect(calls.some((c) => c.path === "/api/v1/payments/participants?search=Person")).toBe(
        true,
      ),
    );
    await waitFor(() => expect(pages()).toHaveTextContent("Page 1 of 3"));
    expect(codes()[0]).toBe("P000001");
  });

  it("changes a project's rates and loads the amounts again", async () => {
    const { calls } = open();
    renderAt("/payments");
    await screen.findByText("Mona Moderator", {}, { timeout: 5000 });
    const before = calls.filter((c) => c.path.startsWith("/api/v1/payments/moderators")).length;
    await userEvent.click(screen.getByRole("button", { name: "Change rates of HINDI" }));
    const dialog = screen.getByRole("dialog");
    const participants = within(dialog).getByLabelText("Participants (₹ per approved minute)");
    await userEvent.type(participants, "1");
    await userEvent.click(within(dialog).getByRole("button", { name: "Save rates" }));
    expect(await screen.findByText("Rates of HINDI saved.")).toBeInTheDocument();
    expect(calls.find((c) => c.method === "PUT")?.body).toEqual({
      moderator_rate: "2.00",
      participant_rate: "1",
    });
    const rates = screen.getByRole("table", { name: "Rates per project" });
    expect(within(rates).getByText("₹1.00 / min")).toBeInTheDocument();
    await waitFor(() =>
      expect(
        calls.filter((c) => c.path.startsWith("/api/v1/payments/moderators")).length,
      ).toBeGreaterThan(before),
    );
  });
});
