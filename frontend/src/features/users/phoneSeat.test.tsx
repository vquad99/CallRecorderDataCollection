// The phone seat's password (D-130): the Super Admin saves it with the seat and can show it; the
// moderator sees their seat and can show the password on My account. Shown only on request.
// Requirements: USER-001, TEL-002, SEC-001, SEC-003
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { fakeApi, ME, renderAt, signedInAs } from "../../test/fakeApi";
import { ALL_PERMISSIONS, USER, worldHandlers } from "../../test/world";

afterEach(() => vi.unstubAllGlobals());

const SECRET = "chirp-test-71"; // made up: not a real password
const SEATED = { ...USER, telephony_agent_id: "70001", telephony_has_password: true };

describe("the Super Admin's phone seat box", () => {
  it("keeps the saved password unless a new one is typed, and shows it on request", async () => {
    const { calls } = fakeApi(
      signedInAs(ALL_PERMISSIONS, {
        ...worldHandlers(),
        "GET /api/v1/users/u2": () => [200, SEATED],
        "GET /api/v1/users/u2/telephony-agent/password": () => [200, { password: SECRET }],
        "PUT /api/v1/users/u2/telephony-agent": (body) => [
          200,
          {
            user_id: "u2",
            telephony_agent_id: (body as { agent_id: string }).agent_id,
            has_password: true,
          },
        ],
      }),
    );
    renderAt("/admin/users/u2");
    expect(await screen.findByLabelText("Seat number", {}, { timeout: 5000 })).toHaveValue("70001");
    const password = screen.getByLabelText("Seat password");
    expect(password).toHaveAttribute("type", "password");
    expect(password).toHaveValue("");
    expect(screen.getByText("Leave empty to keep the saved password.")).toBeInTheDocument();

    // Hidden until asked for: the page does not even have it before Show.
    expect(screen.queryByText(SECRET)).not.toBeInTheDocument();
    expect(calls.some((c) => c.path.endsWith("/password"))).toBe(false);
    await userEvent.click(screen.getByRole("button", { name: "Show" }));
    expect(await screen.findByText(SECRET)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Hide" }));
    expect(screen.queryByText(SECRET)).not.toBeInTheDocument();

    // Saved without a password: the saved one is kept (nothing sent for it).
    await userEvent.click(screen.getByRole("button", { name: "Save phone seat" }));
    expect(await screen.findByText("Phone seat saved.")).toBeInTheDocument();
    // A new password typed: sent once, and the box is emptied again.
    await userEvent.type(screen.getByLabelText("Seat password"), "new-test-pass");
    await userEvent.click(screen.getByRole("button", { name: "Save phone seat" }));
    await waitFor(() => expect(screen.getByLabelText("Seat password")).toHaveValue(""));
    expect(calls.filter((c) => c.method === "PUT").map((c) => c.body)).toEqual([
      { agent_id: "70001" },
      { agent_id: "70001", password: "new-test-pass" },
    ]);
  });

  it("offers nothing to show when no password is saved", async () => {
    fakeApi(
      signedInAs(ALL_PERMISSIONS, {
        ...worldHandlers(),
        "GET /api/v1/users/u2": () => [200, { ...SEATED, telephony_has_password: false }],
      }),
    );
    renderAt("/admin/users/u2");
    expect(
      await screen.findByLabelText("Seat password", {}, { timeout: 5000 }),
    ).toBeInTheDocument();
    expect(screen.queryByText("Leave empty to keep the saved password.")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Show" })).not.toBeInTheDocument();
  });
});

describe("the moderator's own phone seat on My account", () => {
  const as = (me: Record<string, unknown>) =>
    fakeApi({
      ...signedInAs(ALL_PERMISSIONS, {
        ...worldHandlers(),
        "GET /api/v1/auth/phone-seat/password": () => [200, { password: SECRET }],
      }),
      "GET /api/v1/auth/me": () => [200, { ...ME, roles: ["MODERATOR"], ...me }],
    });

  it("shows the seat number and, on request, the password for the Chirp app", async () => {
    const { calls } = as({ telephony_agent_id: "80003", telephony_has_password: true });
    renderAt("/account");
    expect(await screen.findByRole("heading", { name: "Phone seat" })).toBeInTheDocument();
    expect(screen.getByText("Use these to sign in to the Chirp app.")).toBeInTheDocument();
    expect(screen.getByText("80003")).toBeInTheDocument();
    expect(screen.queryByText(SECRET)).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Show" }));
    expect(await screen.findByText(SECRET)).toBeInTheDocument();
    expect(calls.filter((c) => c.path === "/api/v1/auth/phone-seat/password")).toHaveLength(1);
  });

  it("says when no password is saved yet", async () => {
    as({ telephony_agent_id: "80003", telephony_has_password: false });
    renderAt("/account");
    expect(
      await screen.findByText("No seat password is saved yet. Ask your Super Admin."),
    ).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Show" })).not.toBeInTheDocument();
  });

  it("has no phone seat card for someone without a seat", async () => {
    as({ telephony_agent_id: null });
    renderAt("/account");
    expect(await screen.findByText(/This device/)).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Phone seat" })).not.toBeInTheDocument();
  });
});
