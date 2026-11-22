// Requirements: SEC-001
// The audit log in words: each action reads as words with its key under it (the key is what the
// Action box takes), and a change lists only the fields that changed, "Field: old → new".
import { screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { fakeApi, renderAt, signedInAs } from "../../test/fakeApi";
import { actionLabel, changeLines } from "./AuditPage";

afterEach(() => vi.unstubAllGlobals());

const entry = (over: Record<string, unknown>) => ({
  id: "x",
  created_at: "2026-11-09T00:00:00Z",
  actor_email: "ada@example.org",
  action: "user.roles_changed",
  entity_type: "user",
  entity_id: "u2",
  project_id: null,
  before: null,
  after: null,
  ip: null,
  request_id: null,
  ...over,
});

describe("audit log", () => {
  it("shows audit entries with before and after", async () => {
    fakeApi(
      signedInAs(["audit.view"], {
        "GET /api/v1/audit-logs": () => [
          200,
          {
            items: [
              entry({ before: { roles: ["MODERATOR"] }, after: { roles: ["QC_EXECUTIVE"] } }),
              entry({
                id: "y",
                action: "auth.login",
                entity_type: "session",
                entity_id: null,
              }),
            ],
            total: 2,
            page: 1,
            page_size: 50,
          },
        ],
      }),
    );
    renderAt("/admin/audit");
    // The words, with the key under them.
    expect(await screen.findByText("user.roles_changed")).toBeInTheDocument();
    expect(screen.getByText("Users: Roles changed")).toBeInTheDocument();
    expect(screen.getByText("Signed in")).toBeInTheDocument();
    expect(screen.getByText("auth.login")).toBeInTheDocument();
    // What changed, as a line; nothing for an entry without a change.
    expect(screen.getByText("Roles: MODERATOR → QC_EXECUTIVE")).toBeInTheDocument();
    expect(screen.getAllByText("Before and after")).toHaveLength(1);
    expect(screen.queryByText(/"roles"/)).toBeNull();
    // The areas include payments, call lists and audio files.
    for (const area of ["Payments", "Call lists", "Audio files"]) {
      expect(screen.getByRole("option", { name: area })).toBeInTheDocument();
    }
  });

  it("names actions in words", () => {
    expect(actionLabel("task.status_changed")).toBe("Tasks: Status changed");
    expect(actionLabel("payments.rates_changed")).toBe("Payments: Rates changed");
    expect(actionLabel("audio_qc.automatic")).toBe("Automatic audio check");
    expect(actionLabel("auth.login_failed")).toBe("Sign-in failed");
    expect(actionLabel("something_new")).toBe("Something new");
  });

  it("lists only what changed, and a one-sided entry field by field", () => {
    expect(
      changeLines(
        { status: "DRAFT" },
        { status: "ASSIGNED", comment: "Moderator assigned", reason_code: null },
      ),
    ).toEqual(["Status: DRAFT → ASSIGNED", "Comment: Moderator assigned"]);
    expect(changeLines({ device: "Nokia" }, { device: "" })).toEqual(["Device: Nokia → -"]);
    expect(changeLines(null, { languages: [["hi", ""]], has_email: true, district: "" })).toEqual([
      'Languages: ["hi",""]',
      "Has email: Yes",
      "District: -",
    ]);
    expect(
      changeLines({ P000192: { device_make: null } }, { P000192: { device_make: "Nokia" } }),
    ).toEqual(['P000192: {"device_make":null} → {"device_make":"Nokia"}']);
    expect(changeLines({ a: 1 }, { a: 1 })).toEqual([]);
    expect(changeLines(null, null)).toEqual([]);
  });
});
