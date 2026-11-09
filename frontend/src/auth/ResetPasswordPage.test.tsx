// Requirements: AUTH-004, AUTH-016
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { fakeApi, renderAt } from "../test/fakeApi";

afterEach(() => vi.unstubAllGlobals());

const base = {
  "GET /api/v1/auth/csrf": () => [204, null] as [number, unknown],
  "GET /api/v1/auth/me": () => [401, {}] as [number, unknown],
};

describe("ResetPasswordPage", () => {
  it("blocks mismatched passwords and sends the token with the new password", async () => {
    const { calls } = fakeApi({ ...base, "POST /api/v1/auth/password/reset": () => [204, null] });
    renderAt("/reset-password?token=abcdefghijklmnop");
    await userEvent.type(await screen.findByLabelText(/^New password/), "a-long-new-password");
    await userEvent.type(screen.getByLabelText(/Repeat new password/), "different");
    expect(screen.getByText("The two passwords do not match.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Set password" })).toBeDisabled();
    await userEvent.clear(screen.getByLabelText(/Repeat new password/));
    await userEvent.type(screen.getByLabelText(/Repeat new password/), "a-long-new-password");
    await userEvent.click(screen.getByRole("button", { name: "Set password" }));
    expect(await screen.findByText(/Your password is set/)).toBeInTheDocument();
    expect(calls.find((c) => c.path === "/api/v1/auth/password/reset")?.body).toEqual({
      token: "abcdefghijklmnop",
      new_password: "a-long-new-password",
    });
  });

  it("shows the server error for an expired link", async () => {
    fakeApi({
      ...base,
      "POST /api/v1/auth/password/reset": () => [
        400,
        { error: { code: "INVALID_TOKEN", message: "This link is invalid or has expired" } },
      ],
    });
    renderAt("/reset-password?token=abcdefghijklmnop");
    await userEvent.type(await screen.findByLabelText(/^New password/), "a-long-new-password");
    await userEvent.type(screen.getByLabelText(/Repeat new password/), "a-long-new-password");
    await userEvent.click(screen.getByRole("button", { name: "Set password" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("invalid or has expired");
  });
});
