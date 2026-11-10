// Navigation (owner's test list, Option C).
// Requirements: FND-015, FND-020, ROLE-011, AUTH-016
//
// Each role sees exactly the menu its permissions allow; the current page is marked; every menu
// entry opens its page; signing out ends at sign-in; and no link on any page leads to a page that
// does not exist.
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { matchRoutes } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";

import { fakeApi, renderAt, signedInAs } from "../test/fakeApi";
import { PAGES } from "../test/pageSpecs";
import { ALL_PERMISSIONS, worldHandlers } from "../test/world";
import { routes } from "./routes";

afterEach(() => vi.unstubAllGlobals());

// Interface permissions per role, from the matrix in docs/ARCHITECTURE.md section 5.
const ROLE_PERMISSIONS: Record<string, string[]> = {
  "Super Admin": ALL_PERMISSIONS.filter((p) => p !== "recordings.create"),
  "Project Admin": [
    "projects.view",
    "projects.manage",
    "projects.members",
    "participants.view",
    "participants.manage",
    "participants.contact",
    "consent.view",
    "tasks.view",
    "tasks.assign",
    "recordings.view",
    "recordings.download",
    "dashboard.view",
    "audit.view",
    "notes.view",
  ],
  Moderator: [
    "projects.view",
    "participants.view",
    "participants.contact",
    "consent.capture",
    "consent.view",
    "tasks.view",
    "recordings.create",
    "recordings.view",
    "dashboard.view",
    "notes.view",
  ],
  "QC Executive": [
    "projects.view",
    "participants.view",
    "tasks.view",
    "recordings.view",
    "dashboard.view",
    "notes.view",
  ],
  "Client Viewer": [
    "projects.view",
    "participants.view",
    "recordings.view",
    "recordings.download",
    "dashboard.view",
  ],
};

const MENU: Record<string, string[]> = {
  "Super Admin": [
    "Dashboard",
    "Projects",
    "Tasks",
    "Users",
    "Settings",
    "Audit log",
    "System status",
  ],
  "Project Admin": ["Dashboard", "Projects", "Tasks", "Audit log", "System status"],
  Moderator: ["Dashboard", "Projects", "Tasks", "System status"],
  "QC Executive": ["Dashboard", "Projects", "Tasks", "System status"],
  "Client Viewer": ["Dashboard", "Projects", "System status"],
};

const HEADING: Record<string, string> = {
  Dashboard: "Dashboard|My work|Collection progress",
  Projects: "Projects",
  Tasks: "Tasks",
  Users: "Users",
  Settings: "Capacity targets",
  "Audit log": "Audit log",
  "System status": "System status",
};

async function menu() {
  return within(await screen.findByRole("navigation", { name: "Main" }));
}

describe.each(Object.keys(MENU))("%s", (role) => {
  it("sees exactly the menu entries the role allows, and each one opens its page", async () => {
    fakeApi(signedInAs(ROLE_PERMISSIONS[role] ?? [], worldHandlers()));
    renderAt("/status");
    const nav = await menu();
    expect(nav.getAllByRole("link").map((a) => a.textContent)).toEqual(MENU[role]);
    for (const entry of MENU[role] ?? []) {
      await userEvent.click(nav.getByRole("link", { name: entry }));
      expect(
        await screen.findByRole("heading", {
          level: 1,
          name: new RegExp(`^(${HEADING[entry] ?? entry})$`),
        }),
      ).toBeInTheDocument();
      const current = nav.getAllByRole("link").filter((a) => a.getAttribute("aria-current"));
      expect(current.map((a) => a.textContent)).toEqual([entry]);
    }
  });
});

describe("account and sign-out", () => {
  it("opens the account page from the user's name and signs out to the sign-in page", async () => {
    const { calls } = fakeApi(
      signedInAs(ALL_PERMISSIONS, {
        ...worldHandlers(),
        "POST /api/v1/auth/logout": () => [204, null],
      }),
    );
    renderAt("/projects");
    await userEvent.click(await screen.findByRole("link", { name: "Ada Admin" }));
    expect(await screen.findByRole("heading", { name: "My account" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Sign out" }));
    expect(await screen.findByRole("heading", { name: "Sign in" })).toBeInTheDocument();
    expect(calls.some((c) => c.method === "POST" && c.path === "/api/v1/auth/logout")).toBe(true);
    expect(screen.queryByRole("navigation", { name: "Main" })).not.toBeInTheDocument();
  });

  it("the not-found page's link opens the page it names", async () => {
    fakeApi(signedInAs(ALL_PERMISSIONS, worldHandlers()));
    renderAt("/no/such/page");
    await userEvent.click(await screen.findByRole("link", { name: "Go to projects" }));
    expect(await screen.findByRole("heading", { name: "Projects" })).toBeInTheDocument();
  });
});

/** The route a link opens, or "*" when only the not-found page matches. */
function destination(href: string): string {
  const path = new URL(href, "http://app.test").pathname;
  const matches = matchRoutes(routes, path) ?? [];
  return matches[matches.length - 1]?.route.path ?? "(none)";
}

describe("links", () => {
  it("the dead-link check itself recognises a missing page", () => {
    expect(destination("/no/such/page")).toBe("*");
    expect(destination("/projects/p1/team")).toBe("team");
  });

  it.each(Object.entries(PAGES))("every link on %s leads to an existing page", async (_, spec) => {
    const handlers = worldHandlers();
    fakeApi(
      spec.anonymous
        ? {
            ...handlers,
            "GET /api/v1/auth/csrf": () => [204, null],
            "GET /api/v1/auth/me": () => [
              401,
              { error: { code: "UNAUTHENTICATED", message: "x" } },
            ],
          }
        : signedInAs(ALL_PERMISSIONS, handlers),
    );
    renderAt(spec.url);
    await screen.findAllByText(spec.shows, {}, { timeout: 3000 });
    if (spec.noLinks) {
      // The participant page must not lead into the staff application.
      expect(document.querySelectorAll("a[href]").length).toBe(0);
      return;
    }
    await waitFor(() => expect(document.querySelectorAll("a[href]").length).toBeGreaterThan(0));
    const dead = Array.from(document.querySelectorAll<HTMLAnchorElement>("a[href]"))
      .map((a) => a.getAttribute("href") ?? "")
      .filter((href) => href.startsWith("/") && !href.startsWith("/api/"))
      .filter((href) => destination(href) === "*");
    expect(dead).toEqual([]);
  });
});
