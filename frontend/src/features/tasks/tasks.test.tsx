// Requirements: TASK-001, TASK-003, TASK-006, TASK-007, TASK-011, PART-006, SEC-001
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { fakeApi, renderAt, signedInAs } from "../../test/fakeApi";

afterEach(() => vi.unstubAllGlobals());

const party = (id: string, code: string) => ({
  id,
  participant_code: code,
  consent_status: null,
  consent_at: null,
});
const task = {
  id: "t1",
  task_code: "T000001",
  project_id: "p1",
  recording_mode: "TELEPHONY",
  status: "ASSIGNED",
  priority: "HIGH",
  due_at: null,
  created_at: "2026-11-09T00:00:00Z",
  held_from: null,
  reason_code: null,
  participant_a: party("a1", "P000001"),
  participant_b: party("b1", "P000002"),
  moderator_id: "m1",
  moderator_name: "Mona Moderator",
  allowed_transitions: ["CANCELLED", "ON_HOLD"],
  reasons: {
    ON_HOLD: ["OTHER", "WAITING_FOR_PARTICIPANT"],
    CANCELLED: ["CLIENT_REQUEST", "OTHER"],
  },
  can_assign: true,
  is_moderator: false,
};
const timeline = [
  { at: "2026-11-09T00:00:00Z", kind: "status", actor: "Ada", text: "created -> DRAFT" },
];

describe("tasks", () => {
  it("finds tasks by code once typing pauses", async () => {
    const { calls } = fakeApi(
      signedInAs(["tasks.view"], {
        "GET /api/v1/projects": () => [200, { items: [], total: 0, page: 1, page_size: 100 }],
        "GET /api/v1/tasks": () => [200, { items: [task], total: 1, page: 1, page_size: 25 }],
      }),
    );
    renderAt("/tasks");
    await screen.findByText("T000001");
    await userEvent.type(screen.getByLabelText("Task or participant code"), "P0001");
    await waitFor(() => expect(calls.some((c) => c.path.includes("search=P0001"))).toBe(true));
    const searches = calls.filter(
      (c) => c.path.startsWith("/api/v1/tasks?") && c.path.includes("search="),
    );
    expect(searches).toHaveLength(1);
  });

  it("lists tasks with project codes and filters by status", async () => {
    const { calls } = fakeApi(
      signedInAs(["tasks.view", "tasks.assign"], {
        "GET /api/v1/projects": () => [
          200,
          { items: [{ id: "p1", code: "VOICE" }], total: 1, page: 1, page_size: 100 },
        ],
        "GET /api/v1/tasks": () => [200, { items: [task], total: 1, page: 1, page_size: 25 }],
      }),
    );
    renderAt("/tasks");
    const row = (await screen.findByRole("link", { name: "T000001" })).closest("tr") as HTMLElement;
    expect(within(row).getByText("VOICE")).toBeInTheDocument();
    await userEvent.selectOptions(screen.getByLabelText("Status"), "ON_HOLD");
    expect(calls.some((c) => c.path.includes("status=ON_HOLD"))).toBe(true);
  });

  it("puts a task on hold only with a reason", async () => {
    const { calls } = fakeApi(
      signedInAs(["tasks.view", "tasks.assign"], {
        "GET /api/v1/tasks/t1": () => [200, task],
        "GET /api/v1/tasks/t1/timeline": () => [200, timeline],
        "GET /api/v1/projects/p1/members": () => [200, []],
        "POST /api/v1/tasks/t1/transition": () => [
          200,
          {
            ...task,
            status: "ON_HOLD",
            held_from: "ASSIGNED",
            allowed_transitions: ["ASSIGNED", "CANCELLED"],
          },
        ],
      }),
    );
    renderAt("/tasks/t1");
    await screen.findByRole("heading", { name: "Task T000001" });
    await userEvent.selectOptions(screen.getByLabelText("Move to"), "ON_HOLD");
    const apply = screen.getByRole("button", { name: "Apply" });
    expect(apply).toBeDisabled();
    await userEvent.selectOptions(screen.getByLabelText("Reason"), "WAITING_FOR_PARTICIPANT");
    await userEvent.click(apply);
    expect(await screen.findByText("On hold")).toBeInTheDocument();
    expect(calls.find((c) => c.path.endsWith("/transition"))?.body).toEqual({
      to: "ON_HOLD",
      reason_code: "WAITING_FOR_PARTICIPANT",
      comment: "",
    });
  });

  it("needs a reason to reassign the moderator", async () => {
    const { calls } = fakeApi(
      signedInAs(["tasks.view", "tasks.assign"], {
        "GET /api/v1/tasks/t1": () => [200, task],
        "GET /api/v1/tasks/t1/timeline": () => [200, timeline],
        "GET /api/v1/projects/p1/members": () => [
          200,
          [
            {
              user_id: "m2",
              email: "m2@example.org",
              display_name: "Max",
              roles: ["MODERATOR"],
              status: "ACTIVE",
              added_at: "",
            },
          ],
        ],
        "POST /api/v1/tasks/t1/assign": () => [
          200,
          { ...task, moderator_id: "m2", moderator_name: "Max" },
        ],
      }),
    );
    renderAt("/tasks/t1");
    await screen.findByRole("option", { name: "Max (m2@example.org)" });
    await userEvent.selectOptions(screen.getByLabelText("Moderator"), "m2");
    expect(screen.getByRole("button", { name: "Reassign" })).toBeDisabled();
    await userEvent.type(screen.getByLabelText(/Reason for reassigning/), "On leave");
    await userEvent.click(screen.getByRole("button", { name: "Reassign" }));
    expect(await screen.findByText("Max")).toBeInTheDocument();
    expect(calls.find((c) => c.path.endsWith("/assign"))?.body).toEqual({
      user_id: "m2",
      reason: "On leave",
    });
  });

  it("gives the moderator one button to start, then the recorder (D-091)", async () => {
    const mine = {
      ...task,
      recording_mode: "FACE_TO_FACE",
      can_assign: false,
      is_moderator: true,
      allowed_transitions: ["IN_PROGRESS"],
    };
    const { calls } = fakeApi(
      signedInAs(["tasks.view", "consent.capture"], {
        "GET /api/v1/tasks/t1": () => [200, mine],
        "GET /api/v1/tasks/t1/timeline": () => [200, timeline],
        "POST /api/v1/tasks/t1/transition": () => [
          200,
          { ...mine, status: "IN_PROGRESS", allowed_transitions: ["ON_HOLD"] },
        ],
      }),
    );
    renderAt("/tasks/t1");
    await userEvent.click(await screen.findByRole("button", { name: "Start session" }));
    expect(await screen.findByRole("link", { name: "Open the recorder" })).toHaveAttribute(
      "href",
      "/tasks/t1/record",
    );
    expect(calls.find((c) => c.path.endsWith("/transition"))?.body).toEqual({
      to: "IN_PROGRESS",
      reason_code: null,
      comment: "",
    });
  });

  it("lets the moderator listen and send the recording to QC, then the admin approve (D-092)", async () => {
    const recorded = {
      ...task,
      status: "RECORDED",
      recording_mode: "FACE_TO_FACE",
      can_assign: false,
      is_moderator: true,
      allowed_transitions: ["AUDIO_QC", "IN_PROGRESS"],
    };
    const recording = {
      id: "r1",
      task_id: "t1",
      state: "READY",
      saved_seconds: 120,
      assets: [{ id: "as1", kind: "FTF_DERIVED_PCM" }],
    };
    const { calls } = fakeApi(
      signedInAs(["tasks.view", "consent.capture", "recordings.view"], {
        "GET /api/v1/tasks/t1": () => [200, recorded],
        "GET /api/v1/tasks/t1/timeline": () => [200, timeline],
        "GET /api/v1/tasks/t1/recordings": () => [200, [recording]],
        "GET /api/v1/tasks/t1/audio-qc": () => [
          404,
          { error: { code: "NOT_FOUND", message: "x" } },
        ],
        "POST /api/v1/tasks/t1/transition": () => [
          200,
          { ...recorded, status: "AUDIO_QC", allowed_transitions: [] },
        ],
      }),
    );
    renderAt("/tasks/t1");
    expect(
      await screen.findByRole("heading", { name: "Check your recording" }),
    ).toBeInTheDocument();
    expect((await screen.findAllByRole("button", { name: "Listen" })).length).toBeGreaterThan(0);
    expect(screen.getByRole("button", { name: "Record again" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Send to QC" }));
    await waitFor(() =>
      expect(calls.find((c) => c.path.endsWith("/transition"))?.body).toEqual({
        to: "AUDIO_QC",
        reason_code: null,
        comment: "",
      }),
    );
  });

  it("gives the admin a final approval after QC passed (D-092)", async () => {
    const review = {
      ...task,
      status: "ADMIN_REVIEW",
      recording_mode: "FACE_TO_FACE",
      can_assign: true,
      is_moderator: false,
      allowed_transitions: ["APPROVED", "REJECTED", "RETURNED"],
    };
    const { calls } = fakeApi(
      signedInAs(["tasks.view", "tasks.assign", "recordings.view"], {
        "GET /api/v1/tasks/t1": () => [200, review],
        "GET /api/v1/tasks/t1/timeline": () => [200, timeline],
        "GET /api/v1/tasks/t1/recordings": () => [200, []],
        "GET /api/v1/tasks/t1/audio-qc": () => [
          404,
          { error: { code: "NOT_FOUND", message: "x" } },
        ],
        "GET /api/v1/projects/p1/members": () => [200, []],
        "POST /api/v1/tasks/t1/transition": () => [
          200,
          { ...review, status: "APPROVED", allowed_transitions: [] },
        ],
      }),
    );
    renderAt("/tasks/t1");
    expect(await screen.findByRole("heading", { name: "Final approval" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Approve" }));
    await waitFor(() =>
      expect(calls.find((c) => c.path.endsWith("/transition"))?.body).toEqual({
        to: "APPROVED",
        reason_code: null,
        comment: "",
      }),
    );
  });

  it("lets the assigned moderator record consent", async () => {
    const { calls } = fakeApi(
      signedInAs(["tasks.view", "consent.capture"], {
        "GET /api/v1/tasks/t1": () => [
          200,
          { ...task, can_assign: false, is_moderator: true, allowed_transitions: ["IN_PROGRESS"] },
        ],
        "GET /api/v1/tasks/t1/timeline": () => [200, timeline],
        "POST /api/v1/tasks/t1/consent": () => [
          201,
          {
            ...task,
            is_moderator: true,
            participant_a: {
              ...task.participant_a,
              consent_status: "GIVEN",
              consent_at: "2026-11-09T01:00:00Z",
            },
          },
        ],
      }),
    );
    renderAt("/tasks/t1");
    await screen.findByRole("heading", { name: "Record consent" });
    expect(
      screen.queryByRole("heading", { name: /Assign moderator|Reassign moderator/ }),
    ).not.toBeInTheDocument();
    await userEvent.click(
      screen.getAllByRole("button", { name: "Consent given" })[0] as HTMLElement,
    );
    expect((await screen.findAllByText("Given")).length).toBeGreaterThan(0);
    expect(
      screen.getAllByRole("button", { name: "Consent given" })[0] as HTMLElement,
    ).toHaveAttribute("aria-pressed", "true");
    expect(calls.find((c) => c.path.endsWith("/consent"))?.body).toEqual({
      participant_id: "a1",
      status: "GIVEN",
      method: "VERBAL_RECORDED",
    });
  });

  it("shows audit entries with before and after", async () => {
    fakeApi(
      signedInAs(["audit.view"], {
        "GET /api/v1/audit-logs": () => [
          200,
          {
            items: [
              {
                id: "x",
                created_at: "2026-11-09T00:00:00Z",
                actor_email: "ada@example.org",
                action: "user.roles_changed",
                entity_type: "user",
                entity_id: "u2",
                project_id: null,
                before: { roles: ["MODERATOR"] },
                after: { roles: ["QC_EXECUTIVE"] },
                ip: null,
                request_id: null,
              },
            ],
            total: 1,
            page: 1,
            page_size: 50,
          },
        ],
      }),
    );
    renderAt("/admin/audit");
    expect(await screen.findByText("user.roles_changed")).toBeInTheDocument();
    expect(screen.getByText('before: {"roles":["MODERATOR"]}')).toBeInTheDocument();
  });

  it("says when the project has too few participants and adds many tasks from a file", async () => {
    const proj = {
      id: "p1",
      code: "PRJ0001",
      name: "Voice",
      status: "ACTIVE",
      allows_telephony: false,
      allows_face_to_face: true,
      languages: [],
    };
    const { calls } = fakeApi(
      signedInAs(["tasks.view", "tasks.assign", "projects.view"], {
        "GET /api/v1/projects": () => [200, { items: [proj], total: 1, page: 1, page_size: 100 }],
        "GET /api/v1/projects/p1": () => [200, proj],
        "GET /api/v1/projects/p1/participants": () => [
          200,
          { items: [], total: 0, page: 1, page_size: 100 },
        ],
        "GET /api/v1/projects/p1/members": () => [200, []],
        "POST /api/v1/tasks/import": (body) => [
          200,
          {
            rows: [
              {
                line: 2,
                pair: "P000001 + P000002",
                ok: true,
                message: (body as { confirm: boolean }).confirm ? "Added" : "Ready to add",
                task_code: (body as { confirm: boolean }).confirm ? "T000009" : null,
              },
            ],
            ready: 1,
            created: (body as { confirm: boolean }).confirm ? 1 : 0,
          },
        ],
      }),
    );
    renderAt("/tasks/new");
    await userEvent.selectOptions(await screen.findByLabelText("Project (active projects)"), "p1");
    expect(await screen.findByText(/This project has no participants/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Add participants to the project" })).toHaveAttribute(
      "href",
      "/projects/p1/participants",
    );
    // The sample CSV downloads as a file (D-085).
    const saved: Blob[] = [];
    const [create, revoke] = [URL.createObjectURL, URL.revokeObjectURL];
    URL.createObjectURL = (b: Blob | MediaSource) => (saved.push(b as Blob), "blob:sample");
    URL.revokeObjectURL = () => undefined;
    const clicks = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
    await userEvent.click(screen.getByRole("button", { name: "Download sample CSV" }));
    expect(clicks).toHaveBeenCalledTimes(1);
    expect(await saved[0]?.text()).toMatch(
      /^participant_a,participant_b,mode,priority,due_date,moderator\nP000001,P000002,/,
    );
    clicks.mockRestore();
    [URL.createObjectURL, URL.revokeObjectURL] = [create, revoke];
    await userEvent.type(
      screen.getByLabelText("Tasks (CSV)"),
      "participant_a,participant_b{enter}P000001,P000002",
    );
    await userEvent.click(screen.getByRole("button", { name: "Check rows" }));
    expect(await screen.findByText("1 of 1 rows are ready.")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Add 1 tasks" }));
    expect(await screen.findByText("1 tasks added.")).toBeInTheDocument();
    expect(calls.filter((c) => c.path === "/api/v1/tasks/import").map((c) => c.body)).toEqual([
      { project_id: "p1", csv: "participant_a,participant_b\nP000001,P000002", confirm: false },
      { project_id: "p1", csv: "participant_a,participant_b\nP000001,P000002", confirm: true },
    ]);
  });
});
