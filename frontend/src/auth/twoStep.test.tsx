// Two-step sign-in is required for admins (D-106): the set-up comes before everything else.
// Requirements: AUTH-008, AUTH-016
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { fakeApi, ME, renderAt, signedInAs } from "../test/fakeApi";
import { ALL_PERMISSIONS, USER, worldHandlers } from "../test/world";
import { qrCode, qrPath } from "./qr";

afterEach(() => vi.unstubAllGlobals());

const KEY = "AAAABBBBCCCCDDDDEEEEFFFF"; // made up: not a real key

describe("two-step sign-in for admins", () => {
  it("sends an admin who has not set it up to the set-up, and nowhere else", async () => {
    let enabled = false;
    const { calls } = fakeApi(
      signedInAs(ALL_PERMISSIONS, {
        ...worldHandlers(),
        "GET /api/v1/auth/me": () => [
          200,
          {
            ...ME,
            permissions: ALL_PERMISSIONS,
            mfa_enabled: enabled,
            mfa_setup_required: !enabled,
          },
        ],
        "POST /api/v1/auth/mfa/enroll": () => [
          200,
          { secret: KEY, otpauth_uri: `otpauth://totp/CCP:admin@example.org?secret=${KEY}` },
        ],
        "POST /api/v1/auth/mfa/confirm": () => {
          enabled = true;
          return [204, null];
        },
      }),
    );
    const router = renderAt("/projects");
    expect(
      await screen.findByRole("heading", { name: "Set up two-step sign-in" }, { timeout: 5000 }),
    ).toBeInTheDocument();
    expect(router.state.location.pathname).toBe("/two-step-setup");
    expect(screen.getByText(/Your role \(Super Admin\) needs two-step sign-in/)).toBeVisible();
    // No menu, and no page was asked for its data.
    expect(within(screen.getByRole("navigation", { name: "Main" })).queryAllByRole("link")).toEqual(
      [],
    );
    expect(calls.some((c) => c.path.startsWith("/api/v1/projects"))).toBe(false);

    await userEvent.type(screen.getByLabelText(/^Your password/), "a-long-password");
    await userEvent.click(screen.getByRole("button", { name: "Turn on two-step sign-in" }));
    // A code to scan, made from the very link the server gave.
    const code = await screen.findByRole("img", { name: "QR code for your authenticator app" });
    const size = qrCode(`otpauth://totp/CCP:admin@example.org?secret=${KEY}`).size;
    expect(code).toHaveAttribute("viewBox", `0 0 ${size + 8} ${size + 8}`);
    expect(code.querySelector("path")?.getAttribute("d")).toBe(
      qrPath(qrCode(`otpauth://totp/CCP:admin@example.org?secret=${KEY}`)),
    );
    // For someone who cannot scan: the key in groups, a way to copy it, a link for a phone.
    await userEvent.click(screen.getByText("Cannot scan? Type the key instead"));
    expect(await screen.findByText("AAAA BBBB CCCC DDDD EEEE FFFF")).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: "Open in an authenticator app on this device" }),
    ).toHaveAttribute("href", `otpauth://totp/CCP:admin@example.org?secret=${KEY}`);
    await userEvent.type(screen.getByLabelText(/^Authenticator code/), "123456");
    await userEvent.click(screen.getByRole("button", { name: "Confirm" }));
    await waitFor(() => expect(router.state.location.pathname).not.toBe("/two-step-setup"));
    expect(calls.find((c) => c.path === "/api/v1/auth/mfa/confirm")?.body).toEqual({
      code: "123456",
    });
    // The application is open now: the menu is back.
    await waitFor(() =>
      expect(
        within(screen.getByRole("navigation", { name: "Main" })).getAllByRole("link").length,
      ).toBeGreaterThan(3),
    );
  });

  it("goes to the set-up when the server asks for it in the middle of work", async () => {
    // A role given while the person was signed in: the next request is refused.
    fakeApi(
      signedInAs(ALL_PERMISSIONS, {
        ...worldHandlers(),
        "GET /api/v1/projects": () => [
          403,
          {
            error: {
              code: "MFA_SETUP_REQUIRED",
              message: "Set up two-step sign-in to continue: your role needs it.",
              request_id: "r1",
            },
          },
        ],
      }),
    );
    const router = renderAt("/projects");
    expect(
      await screen.findByRole("heading", { name: "Set up two-step sign-in" }, { timeout: 5000 }),
    ).toBeInTheDocument();
    expect(router.state.location.pathname).toBe("/two-step-setup");
  });

  it("says there is nothing to set up for someone who does not need it", async () => {
    fakeApi(signedInAs(ALL_PERMISSIONS, worldHandlers()));
    renderAt("/two-step-setup");
    expect(await screen.findByText(/Nothing to set up here/, {}, { timeout: 5000 })).toBeVisible();
    expect(screen.getByRole("link", { name: "your account page" })).toHaveAttribute(
      "href",
      "/account",
    );
    expect(screen.queryByLabelText(/^Your password/)).toBeNull();
  });

  it("lets a Super Admin reset the two-step sign-in of someone who lost their phone", async () => {
    const confirm = vi.fn(() => true);
    vi.stubGlobal("confirm", confirm);
    const { calls } = fakeApi(
      signedInAs(ALL_PERMISSIONS, {
        ...worldHandlers(),
        "GET /api/v1/users/u2": () => [200, { ...USER, id: "u2", mfa_enabled: true }],
        "POST /api/v1/users/u2/mfa/reset": () => [200, { sessions_revoked: 2 }],
      }),
    );
    renderAt("/admin/users/u2");
    expect(await screen.findByText(/Two-step sign-in: on/, {}, { timeout: 5000 })).toBeVisible();
    await userEvent.click(screen.getByRole("button", { name: "Reset two-step sign-in" }));
    expect(confirm).toHaveBeenCalledWith(expect.stringContaining("lost their authenticator"));
    expect(
      await screen.findByText("Two-step sign-in reset. They are signed out everywhere."),
    ).toBeInTheDocument();
    expect(calls.some((c) => c.method === "POST" && c.path === "/api/v1/users/u2/mfa/reset")).toBe(
      true,
    );
    // Off now, so there is nothing left to reset.
    expect(await screen.findByText(/Two-step sign-in: off/)).toBeVisible();
    expect(screen.queryByRole("button", { name: "Reset two-step sign-in" })).toBeNull();
  });
});
