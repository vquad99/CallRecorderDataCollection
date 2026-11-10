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
    expect(await screen.findByText(/consent: given/)).toBeInTheDocument();
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
});
