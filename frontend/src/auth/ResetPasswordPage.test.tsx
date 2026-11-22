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

  it("offers a new link instead of the form when the link has expired or was used", async () => {
    fakeApi({
      ...base,
      "POST /api/v1/auth/password/reset": () => [
        400,
        {
          error: {
            code: "INVALID_TOKEN",
            message: "This link is invalid or has expired",
            request_id: "4a37aa55bb66cc77dd88ee99ff001122",
          },
        },
      ],
    });
    renderAt("/reset-password?token=abcdefghijklmnop");
    await userEvent.type(await screen.findByLabelText(/^New password/), "a-long-new-password");
    await userEvent.type(screen.getByLabelText(/Repeat new password/), "a-long-new-password");
    await userEvent.click(screen.getByRole("button", { name: "Set password" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      /^This link is invalid or has expired$/,
    );
    expect(screen.getByRole("link", { name: "Request a new link" })).toHaveAttribute(
      "href",
      "/forgot-password",
    );
    expect(screen.queryByRole("button", { name: "Set password" })).toBeNull();
    expect(screen.queryByLabelText(/^New password/)).toBeNull();
  });

  it("offers a new link for a link without its token", async () => {
    fakeApi(base);
    renderAt("/reset-password");
    expect(await screen.findByRole("alert")).toHaveTextContent("This link is incomplete.");
    expect(screen.getByRole("link", { name: "Request a new link" })).toBeInTheDocument();
  });
});
