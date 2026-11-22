// Requirements: CAP-001, CAP-002
import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { fakeApi, renderAt, signedInAs } from "../../test/fakeApi";

afterEach(() => vi.unstubAllGlobals());

const setting = (key: string, value: number, min_value: number, max_value: number) => ({
  key,
  value,
  min_value,
  max_value,
  updated_at: "2026-11-09T00:00:00Z",
});

// In the server's order (by key): the page puts the one real limit first.
const settings = [
  setting("capacity.concurrent_conferences", 50, 1, 10000),
  setting("capacity.participants_per_conversation", 2, 2, 2),
  setting("capacity.staff_accounts", 50, 1, 100000),
  setting("capacity.total_hours_per_day", 250, 1, 1000000),
];

function open() {
  const api = fakeApi(
    signedInAs(["settings.manage"], {
      "GET /api/v1/settings": () => [200, settings],
      "PATCH /api/v1/settings": () => [
        200,
        settings.map((s) => (s.key === "capacity.total_hours_per_day" ? { ...s, value: 300 } : s)),
      ],
    }),
  );
  renderAt("/admin/settings");
  return api;
}

describe("SettingsPage", () => {
  it("sends only changed targets", async () => {
    const { calls } = open();
    const total = await screen.findByLabelText(/Total recording hours per day/);
    await userEvent.clear(total);
    await userEvent.type(total, "300");
    await userEvent.click(screen.getByRole("button", { name: "Save targets" }));
    expect(await screen.findByText(/New values apply immediately/)).toBeInTheDocument();
    expect(calls.find((c) => c.method === "PATCH")?.body).toEqual({
      values: { "capacity.total_hours_per_day": 300 },
    });
  });

  it("shows the account limit first as enforced, and the rest as planning figures", async () => {
    open();
    const boxes = (await screen.findAllByRole("spinbutton")) as HTMLInputElement[];
    expect(boxes.map((b) => b.labels?.[0]?.textContent)).toEqual([
      "Staff accounts",
      "Total recording hours per day",
      "Simultaneous phone conferences",
    ]);
    const limit = screen.getByRole("group", { name: /Account limit/ });
    expect(within(limit).getByText(/Enforced/)).toBeInTheDocument();
    expect(
      within(limit).getByText(
        "New or re-enabled accounts above this number are refused. Allowed: 1 to 1,00,000.",
      ),
    ).toBeInTheDocument();
    const planning = screen.getByRole("group", { name: "Planning figures" });
    expect(
      within(planning).getByText(
        "For reference only; nothing in the platform is limited by these.",
      ),
    ).toBeInTheDocument();
    expect(within(planning).getByText("Allowed: 1 to 10,00,000.")).toBeInTheDocument();
    // One possible value: shown, never a box to type in.
    expect(screen.queryByLabelText(/Participants per conversation/)).not.toBeInTheDocument();
    expect(within(planning).getByText(/Participants per conversation: 2/)).toBeInTheDocument();
    expect(screen.queryByText(/reports/)).not.toBeInTheDocument();
  });

  it.each([
    ["a fraction", "2.5"],
    ["an empty box", ""],
    ["a number below the least allowed", "0"],
  ])("refuses %s naming the field, and sends nothing", async (_, typed) => {
    const { calls } = open();
    const staff = await screen.findByLabelText("Staff accounts");
    await userEvent.clear(staff);
    if (typed) await userEvent.type(staff, typed);
    await userEvent.click(screen.getByRole("button", { name: "Save targets" }));
    expect(
      await screen.findByText("Staff accounts: enter a whole number from 1 to 1,00,000."),
    ).toBeInTheDocument();
    expect(calls.some((c) => c.method === "PATCH")).toBe(false);
    expect(screen.queryByText(/capacity\./)).not.toBeInTheDocument();
  });
});
