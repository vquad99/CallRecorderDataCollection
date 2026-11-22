// Requirements: FND-015, FND-017, FND-020, ROLE-011, AUTH-016
import { act, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { fakeApi, ME, renderAt, signedInAs, type Handler } from "../test/fakeApi";

const emptyProjects: Handler = () => [200, { items: [], total: 0, page: 1, page_size: 25 }];

// A page that fails to display (any render error, or a page file that could not be downloaded).
vi.mock("../features/status/StatusPage", () => ({
  StatusPage: () => {
    throw new TypeError("Cannot read properties of undefined (reading 'speakers')");
  },
}));

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe("routes and guards", () => {
  it("sends an anonymous visitor to sign-in and keeps the destination", async () => {
    fakeApi({
      "GET /api/v1/auth/csrf": () => [204, null],
      "GET /api/v1/auth/me": () => [
        401,
        { error: { code: "UNAUTHENTICATED", message: "Sign in required" } },
      ],
    });
    const router = renderAt("/admin/users");
    expect(await screen.findByRole("heading", { name: "Sign in" })).toBeInTheDocument();
    expect(router.state.location.search).toBe("?next=%2Fadmin%2Fusers");
  });

  it("explains an expired session on the sign-in page", async () => {
    fakeApi({
      "GET /api/v1/auth/csrf": () => [204, null],
      "GET /api/v1/auth/me": () => [
        401,
        { error: { code: "SESSION_EXPIRED", message: "expired" } },
      ],
    });
    renderAt("/projects");
    expect(await screen.findByText(/Your session has expired/)).toBeInTheDocument();
  });

  it("shows only the navigation a role may use", async () => {
    fakeApi(signedInAs(["projects.view"], { "GET /api/v1/projects": emptyProjects }));
    renderAt("/");
    const nav = await screen.findByRole("navigation", { name: "Main" });
    expect(nav).toHaveTextContent("Projects");
    expect(nav).not.toHaveTextContent("Users");
    expect(nav).not.toHaveTextContent("Settings");
    expect(screen.getByRole("link", { name: "Skip to content" })).toHaveAttribute("href", "#main");
  });

  it("shows 'No access' when a route needs a permission the user lacks", async () => {
    fakeApi(signedInAs(["projects.view"]));
    renderAt("/admin/users");
    expect(await screen.findByRole("heading", { name: "No access" })).toBeInTheDocument();
  });

  it("shows the not-found page for unknown routes", async () => {
    fakeApi(signedInAs(["projects.view"]));
    renderAt("/no/such/page");
    expect(
      await screen.findByRole("heading", { level: 1, name: "Page not found" }),
    ).toBeInTheDocument();
  });

  it("returns to sign-in when a session ends mid-use", async () => {
    let meCalls = 0;
    fakeApi(
      signedInAs(["projects.view"], {
        "GET /api/v1/auth/me": () =>
          meCalls++ === 0
            ? [
                200,
                {
                  id: "u1",
                  email: "a@b.org",
                  display_name: "A",
                  roles: [],
                  permissions: ["projects.view"],
                  project_ids: [],
                  mfa_enabled: false,
                },
              ]
            : [401, {}],
        "GET /api/v1/projects": () => [
          401,
          { error: { code: "SESSION_EXPIRED", message: "expired" } },
        ],
      }),
    );
    renderAt("/projects");
    await waitFor(() =>
      expect(screen.getByRole("heading", { name: "Sign in" })).toBeInTheDocument(),
    );
    expect(screen.getByText(/Your session has expired/)).toBeInTheDocument();
  });
});

describe("a page that fails to display (FEA-01)", () => {
  it("shows the app's own message inside the shell, never the error, and clears on another page", async () => {
    const consoleError = vi.spyOn(console, "error").mockImplementation(() => undefined);
    fakeApi(
      signedInAs(["projects.view", "settings.manage"], { "GET /api/v1/projects": emptyProjects }),
    );
    renderAt("/status");
    expect(
      await screen.findByRole("heading", { name: "This page could not be shown" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent(
      "Reload the page to try again. If it keeps happening, tell your administrator.",
    );
    // The top bar and the menu stay; no stack trace, no error text.
    const nav = screen.getByRole("navigation", { name: "Main" });
    expect(screen.getByRole("button", { name: "Sign out" })).toBeInTheDocument();
    expect(screen.queryByText(/Unexpected Application Error/)).toBeNull();
    expect(screen.queryByText(/reading 'speakers'/)).toBeNull();
    expect(document.querySelector("pre")).toBeNull();
    expect(screen.getByRole("button", { name: "Try again" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Go to the start page" })).toHaveAttribute("href", "/");
    expect(consoleError).toHaveBeenCalled();
    // Choosing another page leaves the error behind.
    await userEvent.click(within(nav).getByRole("link", { name: "Projects" }));
    expect(await screen.findByRole("heading", { level: 1, name: "Projects" })).toBeInTheDocument();
    expect(screen.queryByText("This page could not be shown")).toBeNull();
  });
});

describe("a server that cannot be reached at start (FEA-05)", () => {
  const ME_OK: [number, unknown] = [200, { ...ME, permissions: ["projects.view"] }];

  it.each<[string, [number, unknown] | "NETWORK"]>([
    ["a lost connection", "NETWORK"],
    ["a restart (503)", [503, { error: { code: "UNAVAILABLE", message: "Service unavailable" } }]],
    ["too many requests (429)", [429, { error: { code: "RATE_LIMITED", message: "Slow down" } }]],
  ])("keeps the person signed in through %s, and Try again opens the page", async (_, reply) => {
    let down = true;
    fakeApi(
      signedInAs(["projects.view"], {
        "GET /api/v1/auth/me": () => (down ? reply : ME_OK),
        "GET /api/v1/projects": emptyProjects,
      }),
    );
    const router = renderAt("/projects");
    expect(await screen.findByRole("heading", { name: "Cannot reach the server" })).toBeVisible();
    expect(screen.getByText("You are still signed in. Try again in a moment.")).toBeVisible();
    expect(router.state.location.pathname).toBe("/projects");
    expect(screen.queryByRole("heading", { name: "Sign in" })).toBeNull();
    down = false;
    await userEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByRole("heading", { level: 1, name: "Projects" })).toBeInTheDocument();
  });

  it("asks again by itself every few seconds", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    let down = true;
    const { calls } = fakeApi(
      signedInAs(["projects.view"], {
        "GET /api/v1/auth/me": () => (down ? "NETWORK" : ME_OK),
        "GET /api/v1/projects": emptyProjects,
      }),
    );
    renderAt("/projects");
    expect(await screen.findByRole("heading", { name: "Cannot reach the server" })).toBeVisible();
    const asked = () => calls.filter((c) => c.path === "/api/v1/auth/me").length;
    expect(asked()).toBe(1);
    await act(() => vi.advanceTimersByTimeAsync(5_000));
    await waitFor(() => expect(asked()).toBe(2));
    expect(screen.getByRole("heading", { name: "Cannot reach the server" })).toBeVisible();
    down = false;
    await act(() => vi.advanceTimersByTimeAsync(5_000));
    expect(await screen.findByRole("heading", { level: 1, name: "Projects" })).toBeInTheDocument();
  });

  it("a 401 at start still means sign in", async () => {
    fakeApi({
      "GET /api/v1/auth/csrf": () => [204, null],
      "GET /api/v1/auth/me": () => [401, { error: { code: "UNAUTHENTICATED", message: "x" } }],
    });
    renderAt("/projects");
    expect(await screen.findByRole("heading", { name: "Sign in" })).toBeInTheDocument();
    expect(screen.queryByText("Cannot reach the server")).toBeNull();
  });
});
