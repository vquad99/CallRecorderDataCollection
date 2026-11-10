// Requirements: USER-001, USER-004, USER-005, USER-006
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { fakeApi, renderAt, signedInAs } from "../../test/fakeApi";

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
    await userEvent.upload(await screen.findByLabelText("CSV file"), file);
    await userEvent.click(screen.getByRole("button", { name: "Preview" }));
    expect(await screen.findByText("email is not valid")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Import 1 valid row(s)" }));
    expect(await screen.findByText("1 user(s) created, 1 skipped.")).toBeInTheDocument();
    expect(
      calls.filter((c) => c.path.startsWith("/api/v1/users/import")).map((c) => c.path),
    ).toEqual(["/api/v1/users/import/preview", "/api/v1/users/import/confirm"]);
  });
});
