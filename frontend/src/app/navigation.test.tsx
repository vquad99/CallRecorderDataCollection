// Navigation (owner's test list, Option C).
// Requirements: FND-015, FND-020, ROLE-011, AUTH-016
//
// Each role sees exactly the menu its permissions allow; the current page is marked; every menu
// entry opens its page; signing out ends at sign-in (in every tab), and a sign-out the server did
// not get says so; the phone menu closes like an overlay; each page names itself in the browser
// tab; and no link on any page leads to a page that does not exist.
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { matchRoutes } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";

import { fakeApi, ME, renderAt, signedInAs } from "../test/fakeApi";
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
    "calls.end",
    "recordings.view",
    "recordings.download",
    "dashboard.view",
    "audit.view",
    "notes.view",
    "payments.manage",
  ],
  Moderator: [
    "projects.view",
    "participants.view",
    "participants.contact",
    "consent.view",
    "tasks.view",
    "calls.start",
    "calls.end",
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
    "Phone calls",
    "Participants",
    "Users",
    "Settings",
    "Payments",
    "Audit log",
    "System status",
  ],
  "Project Admin": [
    "Dashboard",
    "Projects",
    "Tasks",
    "Phone calls",
    "Participants",
    "Payments",
    "Audit log",
  ],
  Moderator: ["Dashboard", "Projects", "Tasks", "Phone calls"],
  "QC Executive": ["Dashboard", "Projects", "Tasks"],
  "Client Viewer": ["Dashboard", "Projects"],
};

const HEADING: Record<string, string> = {
  Dashboard: "Dashboard|My work|Collection progress",
  Projects: "Projects",
  Tasks: "Tasks",
  "Phone calls": "Phone calls|My phone calls",
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

  it("a sign-out the server did not get keeps the person signed in, and says so (SECF-03)", async () => {
    let up = false;
    fakeApi(
      signedInAs(ALL_PERMISSIONS, {
        ...worldHandlers(),
        "POST /api/v1/auth/logout": () =>
          up
            ? [204, null]
            : [503, { error: { code: "UNAVAILABLE", message: "Service unavailable" } }],
      }),
    );
    renderAt("/projects");
    await userEvent.click(await screen.findByRole("button", { name: "Sign out" }));
    const message = await screen.findByText(
      "You are still signed in: the server could not be reached. Try Sign out again.",
    );
    expect(message.closest('[role="alert"]')).not.toBeNull();
    expect(screen.getByRole("navigation", { name: "Main" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Sign in" })).toBeNull();
    // The next try works: the message goes with the session.
    up = true;
    await userEvent.click(screen.getByRole("button", { name: "Sign out" }));
    expect(await screen.findByRole("heading", { name: "Sign in" })).toBeInTheDocument();
    expect(screen.queryByText(/You are still signed in/)).toBeNull();
  });

  it("a session that had already ended signs out at once", async () => {
    fakeApi(
      signedInAs(ALL_PERMISSIONS, {
        ...worldHandlers(),
        "POST /api/v1/auth/logout": () => [
          401,
          { error: { code: "UNAUTHENTICATED", message: "Sign in required" } },
        ],
      }),
    );
    renderAt("/projects");
    await userEvent.click(await screen.findByRole("button", { name: "Sign out" }));
    expect(await screen.findByRole("heading", { name: "Sign in" })).toBeInTheDocument();
    expect(screen.queryByRole("navigation", { name: "Main" })).toBeNull();
  });
});

describe("the other tabs of the browser (SECF-04)", () => {
  /** Another tab of the same browser, open while `steps` run. */
  async function otherTab(steps: (tab: BroadcastChannel, heard: unknown[]) => Promise<void>) {
    const tab = new BroadcastChannel("ccp-auth");
    const heard: unknown[] = [];
    tab.onmessage = (event: MessageEvent) => heard.push(event.data);
    try {
      await steps(tab, heard);
    } finally {
      tab.close();
    }
  }

  it("signing out in another tab signs this one out too", async () => {
    fakeApi(signedInAs(ALL_PERMISSIONS, worldHandlers()));
    renderAt("/projects");
    await screen.findByRole("navigation", { name: "Main" });
    await otherTab(async (tab) => {
      tab.postMessage("signed-out");
      expect(await screen.findByRole("heading", { name: "Sign in" })).toBeInTheDocument();
      expect(screen.queryByRole("navigation", { name: "Main" })).toBeNull();
    });
  });

  it("signing in in another tab opens this one", async () => {
    let signedIn = false;
    fakeApi({
      ...worldHandlers(),
      "GET /api/v1/auth/csrf": () => [204, null],
      "GET /api/v1/auth/me": () =>
        signedIn
          ? [200, { ...ME, permissions: ALL_PERMISSIONS }]
          : [401, { error: { code: "UNAUTHENTICATED", message: "Sign in required" } }],
    });
    renderAt("/login?next=%2Fprojects");
    await screen.findByRole("heading", { name: "Sign in" });
    signedIn = true;
    await otherTab(async (tab) => {
      tab.postMessage("signed-in");
      expect(
        await screen.findByRole("heading", { level: 1, name: "Projects" }),
      ).toBeInTheDocument();
    });
  });

  it("a new sign-in starts without the message of a sign-out that failed before", async () => {
    let signedIn = true;
    fakeApi({
      ...worldHandlers(),
      "GET /api/v1/auth/csrf": () => [204, null],
      "GET /api/v1/auth/me": () =>
        signedIn
          ? [200, { ...ME, permissions: ALL_PERMISSIONS }]
          : [401, { error: { code: "UNAUTHENTICATED", message: "x" } }],
      "POST /api/v1/auth/login": () => [200, { ...ME, permissions: ALL_PERMISSIONS }],
      "POST /api/v1/auth/logout": () => "NETWORK",
    });
    renderAt("/projects");
    await userEvent.click(await screen.findByRole("button", { name: "Sign out" }));
    await screen.findByText(/You are still signed in/);
    await otherTab(async (tab) => {
      signedIn = false;
      tab.postMessage("signed-out");
      await screen.findByRole("heading", { name: "Sign in" });
    });
    await userEvent.type(screen.getByLabelText(/Email/), "ada@example.org");
    await userEvent.type(screen.getByLabelText(/Password/), "a-long-password");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
    await screen.findByRole("navigation", { name: "Main" });
    expect(screen.queryByText(/You are still signed in/)).toBeNull();
  });

  it("tells the other tabs when this one signs in and out", async () => {
    fakeApi({
      ...worldHandlers(),
      "GET /api/v1/auth/csrf": () => [204, null],
      "GET /api/v1/auth/me": () => [401, { error: { code: "UNAUTHENTICATED", message: "x" } }],
      "POST /api/v1/auth/login": () => [200, { ...ME, permissions: ALL_PERMISSIONS }],
      "POST /api/v1/auth/logout": () => [204, null],
    });
    renderAt("/login");
    await otherTab(async (_, heard) => {
      await userEvent.type(await screen.findByLabelText(/Email/), "ada@example.org");
      await userEvent.type(screen.getByLabelText(/Password/), "a-long-password");
      await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
      await userEvent.click(await screen.findByRole("button", { name: "Sign out" }));
      await screen.findByRole("heading", { name: "Sign in" });
      await waitFor(() => expect(heard).toEqual(["signed-in", "signed-out"]));
    });
  });
});

describe("the menu on a small screen (FEA-10)", () => {
  it("closes on Escape, on a tap beside it and on any of its links", async () => {
    fakeApi(signedInAs(ALL_PERMISSIONS, worldHandlers()));
    renderAt("/projects");
    const button = await screen.findByRole("button", { name: "Menu" });
    expect(button).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByRole("button", { name: "Close menu" })).toBeNull();

    await userEvent.click(button);
    expect(button).toHaveAttribute("aria-expanded", "true");
    await userEvent.tab(); // the focus moves on, and comes back with Escape
    await userEvent.keyboard("{Escape}");
    expect(button).toHaveAttribute("aria-expanded", "false");
    expect(button).toHaveFocus();

    await userEvent.click(button);
    await userEvent.click(screen.getByRole("button", { name: "Close menu" }));
    expect(button).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByRole("button", { name: "Close menu" })).toBeNull();

    // The current page's own link closes it too.
    await userEvent.click(button);
    const nav = within(screen.getByRole("navigation", { name: "Main" }));
    await userEvent.click(nav.getByRole("link", { name: "Projects" }));
    expect(button).toHaveAttribute("aria-expanded", "false");
  });
});

describe("page titles (WCAG 2.4.2)", () => {
  it("names the page in the browser tab", async () => {
    fakeApi(signedInAs(ALL_PERMISSIONS, worldHandlers()));
    renderAt("/admin/audit");
    await screen.findByRole("heading", { level: 1, name: "Audit log" });
    expect(document.title).toBe("Audit log · Conversation Collection");
  });

  it("a project's pages name the project as well, and follow the menu", async () => {
    fakeApi(signedInAs([...ALL_PERMISSIONS, "exports.create"], worldHandlers()));
    renderAt("/projects/p1/team");
    await screen.findByRole("heading", { level: 1, name: "Team" });
    await waitFor(() => expect(document.title).toBe("Team · HINDI · Conversation Collection"));
    const menu = within(screen.getByRole("navigation", { name: "Project sections" }));
    await userEvent.click(menu.getByRole("link", { name: "Overview" }));
    await waitFor(() =>
      expect(document.title).toBe("HINDI · Hindi conversations · Conversation Collection"),
    );
    // Each section of the Rules has its own.
    await userEvent.click(menu.getByRole("link", { name: "Rules" }));
    await waitFor(() =>
      expect(document.title).toBe("Speakers · Rules · HINDI · Conversation Collection"),
    );
    await userEvent.click(menu.getByRole("link", { name: "Consent" }));
    await waitFor(() =>
      expect(document.title).toBe("Consent · Rules · HINDI · Conversation Collection"),
    );
    // A page without one of its own keeps the route's (the main menu's Tasks).
    await userEvent.click(
      within(screen.getByRole("navigation", { name: "Main" })).getByRole("link", { name: "Tasks" }),
    );
    await screen.findByRole("heading", { level: 1, name: "Tasks" });
    expect(document.title).toBe("Tasks · Conversation Collection");
  });
});

describe("a project's menu (D-150)", () => {
  it("lists the project's pages beside the side menu, marks the current one and opens each", async () => {
    fakeApi(signedInAs([...ALL_PERMISSIONS, "exports.create"], worldHandlers()));
    renderAt("/projects/p1");
    const menu = within(await screen.findByRole("navigation", { name: "Project sections" }));
    expect(menu.getAllByRole("link").map((a) => a.textContent)).toEqual([
      "Overview",
      "Progress",
      "Team",
      "Participants",
      "Tasks",
      "Audio rules",
      "Rules",
      "Languages",
      "Retention",
      "Export",
    ]);
    const current = () =>
      menu
        .getAllByRole("link")
        .filter((a) => a.getAttribute("aria-current") === "page")
        .map((a) => a.textContent);
    expect(current()).toEqual(["Overview"]);
    for (const page of ["Team", "Audio rules", "Languages", "Retention"]) {
      await userEvent.click(menu.getByRole("link", { name: page }));
      // Each page is titled with its own name.
      expect(await screen.findByRole("heading", { level: 1, name: page })).toBeInTheDocument();
      expect(current()).toEqual([page]);
    }
    // The side menu keeps Projects marked.
    expect(
      within(screen.getByRole("navigation", { name: "Main" })).getByRole("link", {
        name: "Projects",
      }),
    ).toHaveAttribute("aria-current", "page");
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
    expect(destination("/projects/p1/rules/consent")).toBe(":section");
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
