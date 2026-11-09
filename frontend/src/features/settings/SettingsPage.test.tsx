// Requirements: CAP-002
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { fakeApi, renderAt, signedInAs } from "../../test/fakeApi";

afterEach(() => vi.unstubAllGlobals());

const settings = [
  {
    key: "capacity.staff_accounts",
    value: 50,
    min_value: 1,
    max_value: 100000,
    updated_at: "2026-11-09T00:00:00Z",
  },
  {
    key: "capacity.total_hours_per_day",
    value: 250,
    min_value: 1,
    max_value: 1000000,
    updated_at: "2026-11-09T00:00:00Z",
  },
];

describe("SettingsPage", () => {
  it("sends only changed targets", async () => {
    const { calls } = fakeApi(
      signedInAs(["settings.manage"], {
        "GET /api/v1/settings": () => [200, settings],
        "PATCH /api/v1/settings": () => [
          200,
          settings.map((s) =>
            s.key === "capacity.total_hours_per_day" ? { ...s, value: 300 } : s,
          ),
        ],
      }),
    );
    renderAt("/admin/settings");
    const total = await screen.findByLabelText(/Total recording hours per day/);
    await userEvent.clear(total);
    await userEvent.type(total, "300");
    await userEvent.click(screen.getByRole("button", { name: "Save targets" }));
    expect(await screen.findByText(/New values apply immediately/)).toBeInTheDocument();
    expect(calls.find((c) => c.method === "PATCH")?.body).toEqual({
      values: { "capacity.total_hours_per_day": 300 },
    });
  });
});
