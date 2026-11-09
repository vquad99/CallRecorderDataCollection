// Requirements: FND-015, FND-020, ROLE-011, AUTH-016
import { screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { fakeApi, renderAt, signedInAs, type Handler } from "../test/fakeApi";

const emptyProjects: Handler = () => [200, { items: [], total: 0, page: 1, page_size: 25 }];

afterEach(() => vi.unstubAllGlobals());

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
    expect(await screen.findByRole("heading", { name: "Page not found" })).toBeInTheDocument();
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
