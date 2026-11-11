// Requirements: PROJ-009, PROJ-013, ROLE-011, USER-003
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { fakeApi, renderAt, signedInAs } from "../../test/fakeApi";

afterEach(() => vi.unstubAllGlobals());

const project = {
  id: "p1",
  code: "HINDI",
  name: "Hindi conversations",
  status: "DRAFT",
  allows_telephony: true,
  allows_face_to_face: false,
  target_telephony_hours_per_day: "10.00",
  target_face_to_face_hours_per_day: "0.00",
  created_at: "2026-11-09T00:00:00Z",
  description: "",
  phone_visibility_policy: "ADMINS_ONLY",
  consent_policy_version: "1",
  consent_text: "",
  status_reason: null,
  status_changed_at: null,
  languages: [{ language_code: "hi", dialect: "Awadhi" }],
  audio_rules: [
    {
      mode: "TELEPHONY",
      sample_rate: 16000,
      bit_depth: 16,
      channels: 2,
      max_silence_pct: "25.00",
      max_clipping_pct: null,
      min_duration_seconds: 0,
      max_duration_seconds: null,
    },
  ],
  retention_rules: [],
  accepts_new_work: false,
};

describe("project detail", () => {
  it("lets a project manager change status through the API", async () => {
    const { calls } = fakeApi(
      signedInAs(["projects.view", "projects.manage", "projects.members"], {
        "GET /api/v1/projects/p1": () => [200, project],
        "POST /api/v1/projects/p1/status": () => [
          200,
          { ...project, status: "ACTIVE", accepts_new_work: true },
        ],
      }),
    );
    renderAt("/projects/p1");
    expect(
      await screen.findByRole("heading", { name: "HINDI · Hindi conversations" }),
    ).toBeInTheDocument();
    // The Overview tab loads on first visit (O11): wait for it, not just the page heading.
    await userEvent.click(await screen.findByRole("button", { name: "Change status" }));
    expect(await screen.findByText("Status changed.")).toBeInTheDocument();
    expect(screen.getByText("This project accepts new work.")).toBeInTheDocument();
    expect(calls.find((c) => c.path === "/api/v1/projects/p1/status")?.body).toEqual({
      status: "ACTIVE",
      reason: null,
    });
  });

  it("shows a read-only project to a member without manage rights", async () => {
    fakeApi(signedInAs(["projects.view"], { "GET /api/v1/projects/p1": () => [200, project] }));
    renderAt("/projects/p1");
    await screen.findByRole("heading", { name: "HINDI · Hindi conversations" });
    expect(await screen.findByLabelText(/^Name/)).toBeDisabled(); // the tab has loaded
    expect(screen.queryByRole("button", { name: "Change status" })).not.toBeInTheDocument();
  });

  it("renders each tab", async () => {
    fakeApi(
      signedInAs(["projects.view", "projects.manage", "projects.members"], {
        "GET /api/v1/projects/p1": () => [200, project],
        "GET /api/v1/projects/p1/members": () => [200, []],
      }),
    );
    renderAt("/projects/p1/team");
    expect(await screen.findByText("No members yet")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("link", { name: "Audio rules" }));
    expect(await screen.findByRole("group", { name: "Telephony" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("link", { name: "Languages" }));
    expect(await screen.findByText(/Hindi \(hi\), Awadhi/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("link", { name: "Retention" }));
    expect(await screen.findByLabelText("Browser original captures")).toBeInTheDocument();
  });

  it("goes back to the project list with a note after creating a project", async () => {
    const created = { ...project, id: "p9", code: "PRJ0009", name: "Tamil talk" };
    fakeApi(
      signedInAs(["projects.view", "projects.create", "projects.manage"], {
        "POST /api/v1/projects": () => [201, created],
        "GET /api/v1/projects": () => [200, { items: [created], total: 1, page: 1, page_size: 25 }],
      }),
    );
    renderAt("/projects/new");
    await userEvent.type(await screen.findByLabelText(/^Name/), "Tamil talk");
    await userEvent.click(screen.getByRole("button", { name: "Create project" }));
    expect(
      await screen.findByText(/^PRJ0009 Tamil talk created\. It starts as Draft/),
    ).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Projects" })).toBeInTheDocument();
    expect(await screen.findByRole("link", { name: "PRJ0009" })).toHaveAttribute(
      "href",
      "/projects/p9",
    );
  });
});
