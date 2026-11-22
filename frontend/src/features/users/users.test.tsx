// Requirements: USER-001, USER-004, USER-005, USER-006
import { act, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { fakeApi, ME, renderAt, signedInAs } from "../../test/fakeApi";

afterEach(() => vi.unstubAllGlobals());

const user = (i: number) => ({
  id: `id${i}`,
  email: `person${i}@example.org`,
  display_name: `Person ${i}`,
  status: "ACTIVE",
  roles: ["MODERATOR"],
  mfa_enabled: false,
  password_set: i % 2 === 0,
  last_login_at: null,
  created_at: "2026-11-09T00:00:00Z",
});

describe("users admin", () => {
  it("lists users, sends filters to the API and pages through results", async () => {
    const { calls } = fakeApi(
      signedInAs(["users.manage"], {
        "GET /api/v1/users": (_b, url) => {
          const page = Number(url.searchParams.get("page"));
          return [200, { items: [user(page)], total: 30, page, page_size: 25 }];
        },
      }),
    );
    renderAt("/admin/users");
    expect(await screen.findByRole("link", { name: "Person 1" })).toBeInTheDocument();
    expect(screen.getByText(/invitation pending/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Next" }));
    expect(await screen.findByRole("link", { name: "Person 2" })).toBeInTheDocument();
    await userEvent.selectOptions(screen.getByLabelText("Role"), "QC_EXECUTIVE");
    await waitFor(() =>
      expect(
        calls.some((c) => c.path.includes("role=QC_EXECUTIVE") && c.path.includes("page=1")),
      ).toBe(true),
    );
  });

  it("puts the page's main button last, as on every other page (D-159)", async () => {
    fakeApi(
      signedInAs(["users.manage"], {
        "GET /api/v1/users": () => [200, { items: [user(1)], total: 1, page: 1, page_size: 25 }],
      }),
    );
    renderAt("/admin/users");
    const add = await screen.findByRole("link", { name: "Add user" });
    const buttons = [...(add.closest(".actions")?.children ?? [])].map((b) => b.textContent);
    expect(buttons).toEqual(["Import CSV", "Export CSV", "Add user"]);
  });

  it("keeps the search, filters and page when a user is opened and Back is pressed", async () => {
    const { calls } = fakeApi(
      signedInAs(["users.manage"], {
        "GET /api/v1/users": (_b, url) => {
          const page = Number(url.searchParams.get("page"));
          return [200, { items: [user(page)], total: 30, page, page_size: 25 }];
        },
        "GET /api/v1/users/id2": () => [200, user(2)],
      }),
    );
    const router = renderAt("/admin/users");
    await screen.findByRole("link", { name: "Person 1" });
    await userEvent.type(screen.getByLabelText("Search"), "person");
    await userEvent.selectOptions(screen.getByLabelText("Role"), "MODERATOR");
    await waitFor(() => expect(router.state.location.search).toContain("search=person"));
    await userEvent.click(await screen.findByRole("button", { name: "Next" }));
    await userEvent.click(await screen.findByRole("link", { name: "Person 2" }));
    expect(await screen.findByRole("heading", { name: "Person 2" })).toBeInTheDocument();

    await act(() => router.navigate(-1));
    expect(await screen.findByRole("link", { name: "Person 2" })).toBeInTheDocument();
    expect(screen.getByLabelText("Search")).toHaveValue("person");
    expect(screen.getByLabelText("Role")).toHaveValue("MODERATOR");
    expect(screen.getByText(/Page 2 of 2/)).toBeInTheDocument();
    const last = calls.filter((c) => c.path.startsWith("/api/v1/users?")).at(-1)?.path ?? "";
    expect(last).toContain("search=person");
    expect(last).toContain("role=MODERATOR");
    expect(last).toContain("page=2");
  });

  it("refuses a name of spaces alone", async () => {
    fakeApi(signedInAs(["users.manage"]));
    renderAt("/admin/users/new");
    await userEvent.type(await screen.findByLabelText(/Email/), "person4@example.org");
    await userEvent.type(screen.getByLabelText(/Name/), "   ");
    await userEvent.click(screen.getByLabelText("Moderator"));
    expect(screen.getByRole("button", { name: "Add and send invitation" })).toBeDisabled();
  });

  it("creates a user with roles and reports the invitation", async () => {
    const { calls } = fakeApi(
      signedInAs(["users.manage"], {
        "POST /api/v1/users": () => [201, { user: user(4), invite_sent: true }],
      }),
    );
    renderAt("/admin/users/new");
    await userEvent.type(await screen.findByLabelText(/Email/), "person4@example.org");
    await userEvent.type(screen.getByLabelText(/Name/), "Person 4");
    const submit = screen.getByRole("button", { name: "Add and send invitation" });
    expect(submit).toBeDisabled();
    await userEvent.click(screen.getByLabelText("Moderator"));
    await userEvent.click(submit);
    expect(await screen.findByText(/was invited by email/)).toBeInTheDocument();
    expect(calls.find((c) => c.method === "POST")?.body).toEqual({
      email: "person4@example.org",
      display_name: "Person 4",
      roles: ["MODERATOR"],
    });
  });

  it("previews a CSV import and imports only valid rows", async () => {
    const rows = [
      { line: 2, email: "ok@example.org", display_name: "Ok", roles: ["MODERATOR"], errors: [] },
      {
        line: 3,
        email: "bad",
        display_name: "Bad",
        roles: ["MODERATOR"],
        errors: ["email is not valid"],
      },
    ];
    const { calls } = fakeApi(
      signedInAs(["users.manage"], {
        "POST /api/v1/users/import/preview": () => [
          200,
          { rows, valid_count: 1, invalid_count: 1 },
        ],
        "POST /api/v1/users/import/confirm": () => [
          200,
          { created: 1, skipped: [rows[1]], invites_failed: 0 },
        ],
      }),
    );
    renderAt("/admin/users/import");
    const file = new File(
      ["email,display_name,roles\nok@example.org,Ok,MODERATOR\nbad,Bad,MODERATOR\n"],
      "u.csv",
      { type: "text/csv" },
    );
    await userEvent.upload(await screen.findByLabelText("Choose a CSV file"), file);
    expect(await screen.findByText("u.csv")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Preview" }));
    expect(await screen.findByText("email is not valid")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Import 1 valid row" }));
    expect(await screen.findByText("1 user created, 1 skipped.")).toBeInTheDocument();
    expect(
      calls.filter((c) => c.path.startsWith("/api/v1/users/import")).map((c) => c.path),
    ).toEqual(["/api/v1/users/import/preview", "/api/v1/users/import/confirm"]);
  });

  it("names the person in the tab, refuses a blank name and counts the sessions signed out", async () => {
    const { calls } = fakeApi(
      signedInAs(["users.manage"], {
        "GET /api/v1/users/id2": () => [200, user(2)],
        "POST /api/v1/users/id2/sessions/revoke": () => [200, { sessions_revoked: 2 }],
      }),
    );
    renderAt("/admin/users/id2");
    expect(await screen.findByRole("heading", { name: "Person 2" })).toBeInTheDocument();
    await waitFor(() => expect(document.title).toBe("Person 2 · Conversation Collection"));
    const name = screen.getByLabelText(/Name/);
    await userEvent.clear(name);
    await userEvent.type(name, "  ");
    expect(screen.getByRole("button", { name: "Save changes" })).toBeDisabled();
    await userEvent.click(screen.getByRole("button", { name: "Sign out everywhere" }));
    const dialog = await screen.findByRole("dialog");
    await userEvent.click(within(dialog).getByRole("button", { name: "Sign out everywhere" }));
    expect(await screen.findByText("2 sessions signed out.")).toBeInTheDocument();
    expect(calls.filter((c) => c.method === "PATCH")).toEqual([]);
  });

  it("lets a Super Admin view the app as someone else, read-only, and stop (D-100)", async () => {
    const viewing = {
      ...ME,
      id: "id1",
      email: "person1@example.org",
      display_name: "Person 1",
      roles: ["MODERATOR"],
      permissions: ["projects.view", "tasks.view"],
      viewer: { id: "u1", display_name: "Ada Admin" },
    };
    const { calls } = fakeApi(
      signedInAs(["users.manage", "projects.view"], {
        "GET /api/v1/users": () => [200, { items: [user(1)], total: 1, page: 1, page_size: 25 }],
        "GET /api/v1/projects": () => [200, { items: [], total: 0, page: 1, page_size: 25 }],
        "POST /api/v1/auth/view-as": () => [200, viewing],
        "DELETE /api/v1/auth/view-as": () => [200, { ...ME, permissions: ["users.manage"] }],
      }),
    );
    renderAt("/admin/users");
    await userEvent.click(await screen.findByRole("button", { name: "View as Person 1" }));
    expect(await screen.findByText(/Read-only: nothing can be changed/)).toBeInTheDocument();
    expect(calls.find((c) => c.path === "/api/v1/auth/view-as")?.body).toEqual({ user_id: "id1" });
    await userEvent.click(screen.getByRole("button", { name: "Stop viewing" }));
    expect(await screen.findByRole("link", { name: "Person 1" })).toBeInTheDocument();
    // The strip goes once the answer to "Stop viewing" is in: wait for it, do not race it.
    await waitFor(() =>
      expect(screen.queryByText(/Read-only: nothing can be changed/)).not.toBeInTheDocument(),
    );
  });

  it("offers View as only to a Super Admin", async () => {
    fakeApi({
      ...signedInAs(["users.manage"], {
        "GET /api/v1/users": () => [200, { items: [user(1)], total: 1, page: 1, page_size: 25 }],
      }),
      "GET /api/v1/auth/me": () => [
        200,
        { ...ME, roles: ["PROJECT_ADMIN"], permissions: ["users.manage"] },
      ],
    });
    renderAt("/admin/users");
    expect(await screen.findByRole("link", { name: "Person 1" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /View as/ })).not.toBeInTheDocument();
  });
});
