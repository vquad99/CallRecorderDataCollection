// Requirements: AUTH-001, AUTH-002, AUTH-008, AUTH-016
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { fakeApi, ME, renderAt } from "../test/fakeApi";

afterEach(() => vi.unstubAllGlobals());

const anonymous = {
  "GET /api/v1/auth/csrf": () => [204, null] as [number, unknown],
  "GET /api/v1/auth/me": () =>
    [401, { error: { code: "UNAUTHENTICATED", message: "x" } }] as [number, unknown],
  "GET /api/v1/projects": () =>
    [200, { items: [], total: 0, page: 1, page_size: 25 }] as [number, unknown],
};

async function fill(email: string, password: string) {
  await userEvent.type(await screen.findByLabelText(/Email/), email);
  await userEvent.type(screen.getByLabelText(/Password/), password);
  await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
}

describe("LoginPage", () => {
  it("shows the server's message for wrong credentials, without its reference", async () => {
    fakeApi({
      ...anonymous,
      "POST /api/v1/auth/login": () => [
        401,
        {
          error: {
            code: "INVALID_CREDENTIALS",
            message: "Invalid email or password",
            request_id: "7640467b0123456789abcdef0123af45",
          },
        },
      ],
    });
    renderAt("/login");
    await fill("a@example.org", "wrong");
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent(/^Invalid email or password$/);
  });

  it("points out empty fields and an incomplete address at the field, and sends nothing", async () => {
    const { calls } = fakeApi({ ...anonymous, "POST /api/v1/auth/login": () => [200, ME] });
    renderAt("/login");
    await userEvent.click(await screen.findByRole("button", { name: "Sign in" }));
    expect(screen.getByLabelText(/Email/)).toHaveAccessibleDescription("Enter your email address.");
    expect(screen.getByLabelText(/Password/)).toHaveAccessibleDescription("Enter your password.");
    expect(screen.getByLabelText(/Email/)).toBeInvalid();
    // Typing into a field takes its message away.
    await userEvent.type(screen.getByLabelText(/Email/), "ada");
    expect(screen.queryByText("Enter your email address.")).toBeNull();
    expect(screen.getByText("Enter your password.")).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText(/Password/), "a-long-password");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
    expect(screen.getByLabelText(/Email/)).toHaveAccessibleDescription(
      "Enter your full email address, for example name@example.org.",
    );
    expect(calls.some((c) => c.path === "/api/v1/auth/login")).toBe(false);
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("the reset request also points out an empty address, and sends nothing", async () => {
    const { calls } = fakeApi({
      ...anonymous,
      "POST /api/v1/auth/password/forgot": () => [202, { status: "sent" }],
    });
    renderAt("/forgot-password");
    await userEvent.click(await screen.findByRole("button", { name: "Send reset link" }));
    expect(screen.getByLabelText(/Email/)).toHaveAccessibleDescription("Enter your email address.");
    expect(calls.some((c) => c.path === "/api/v1/auth/password/forgot")).toBe(false);
    await userEvent.type(screen.getByLabelText(/Email/), " ada@example.org ");
    await userEvent.click(screen.getByRole("button", { name: "Send reset link" }));
    expect(await screen.findByText("sent")).toBeInTheDocument();
    expect(calls.find((c) => c.path === "/api/v1/auth/password/forgot")?.body).toEqual({
      email: "ada@example.org",
    });
  });

  it("asks for the authenticator code, then signs in and goes to the requested page", async () => {
    const { calls } = fakeApi({
      ...anonymous,
      "POST /api/v1/auth/login": (body) =>
        (body as { totp_code?: string }).totp_code === "123456"
          ? [200, ME]
          : [401, { error: { code: "MFA_REQUIRED", message: "code" } }],
    });
    const router = renderAt("/login?next=%2Fprojects");
    await fill("admin@example.org", "secret-password");
    await userEvent.type(await screen.findByLabelText(/Authenticator code/), "123456");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
    expect(await screen.findByRole("heading", { name: "Projects" })).toBeInTheDocument();
    expect(router.state.location.pathname).toBe("/projects");
    expect(calls.filter((c) => c.path === "/api/v1/auth/login")).toHaveLength(2);
  });

  it("ignores an off-site next parameter", async () => {
    fakeApi({ ...anonymous, "POST /api/v1/auth/login": () => [200, ME] });
    const router = renderAt("/login?next=%2F%2Fevil.example");
    await fill("admin@example.org", "secret-password");
    await screen.findByRole("heading", { name: "Projects" });
    expect(router.state.location.pathname).toBe("/projects"); // "/" opens the start page
  });

  it("ignores a next parameter that a browser would read as another site", async () => {
    fakeApi({ ...anonymous, "POST /api/v1/auth/login": () => [200, ME] });
    const router = renderAt("/login?next=%2F%5Cevil.example");
    await fill("admin@example.org", "secret-password");
    await screen.findByRole("heading", { name: "Projects" });
    expect(router.state.location.pathname).toBe("/projects");
  });
});
