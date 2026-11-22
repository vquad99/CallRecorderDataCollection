// My account's signed-in devices: this device first, then the first ten, and the rest on request
// from the section's title bar, as on the dashboard (D-158).
// Requirements: AUTH-010
import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import type { SessionInfo } from "../../api/auth";
import { fakeApi, renderAt, signedInAs } from "../../test/fakeApi";
import { ALL_PERMISSIONS, worldHandlers } from "../../test/world";

/** Twelve devices; the one in use is the last the server lists. */
const SESSIONS: SessionInfo[] = Array.from({ length: 12 }, (_, i) => ({
  id: `s${i + 1}`,
  created_at: "2026-11-09T00:00:00Z",
  last_seen_at: "2026-11-09T00:00:00Z",
  expires_at: "2026-11-10T00:00:00Z",
  ip: `10.0.0.${i + 1}`,
  user_agent: "test",
  current: i === 11,
}));

describe("signed-in devices", () => {
  it("shows this device first and ten in all, the rest from the title bar", async () => {
    fakeApi(
      signedInAs(ALL_PERMISSIONS, {
        ...worldHandlers(),
        "GET /api/v1/auth/sessions": () => [200, SESSIONS],
      }),
    );
    renderAt("/account");
    const title = await screen.findByRole("heading", { name: "Signed-in devices" });
    const section = title.closest("section") as HTMLElement;
    await within(section).findByText("This device");
    const rows = () => within(section).getAllByRole("row").slice(1);
    expect(rows()).toHaveLength(10);
    expect(rows()[0]).toHaveTextContent("This device");
    expect(rows()[0]).toHaveTextContent("10.0.0.12");
    const more = within(section).getByRole("button", { name: "Show all (12)" });
    expect(more.closest(".card__head")).toHaveTextContent("Signed-in devices");
    await userEvent.click(more);
    expect(rows()).toHaveLength(12);
  });
});
