// Requirements: TASK-001, TASK-003, TASK-006, TASK-007, TASK-011, PART-006, SEC-001
import { cleanup, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { fakeApi, renderAt, signedInAs } from "../../test/fakeApi";

afterEach(() => vi.unstubAllGlobals());

const party = (id: string, code: string) => ({
  id,
  participant_code: code,
  display_label: `Name of ${code}`,
  has_email: true,
  consent_status: null,
  consent_at: null,
  may_record: false,
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
  can_reassign: true,
  is_moderator: false,
  consent_missing: ["A", "B"],
};
const timeline = [
  {
    at: "2026-11-09T00:00:00Z",
    kind: "status",
    actor: "Ada",
    text: "created -> DRAFT",
    from_status: null,
    to_status: "DRAFT",
    reason_code: null,
    comment: null,
  },
  {
    at: "2026-11-09T01:00:00Z",
    kind: "status",
    actor: "Ada",
    text: "DRAFT -> ON_HOLD WAITING_FOR_PARTICIPANT Back next week",
    from_status: "DRAFT",
    to_status: "ON_HOLD",
    reason_code: "WAITING_FOR_PARTICIPANT",
    comment: "Back next week",
  },
];
/** The open confirmation window. */
const dialog = () => screen.getByRole("dialog");

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

  it("deletes a task made by mistake, with a reason, and says so on the list (D-115)", async () => {
    const { calls } = fakeApi(
      signedInAs(["tasks.view", "tasks.assign"], {
        "GET /api/v1/tasks/t1": () => [200, task],
        "GET /api/v1/tasks/t1/timeline": () => [200, timeline],
        "GET /api/v1/projects/p1/members": () => [200, []],
        "POST /api/v1/tasks/t1/delete": () => [204, null],
        "GET /api/v1/tasks": () => [200, { items: [], total: 0, page: 1, page_size: 25 }],
        "GET /api/v1/projects": () => [200, { items: [], total: 0, page: 1, page_size: 100 }],
      }),
    );
    const router = renderAt("/tasks/t1");
    await screen.findByRole("heading", { name: /^Task T000001/ });
    await userEvent.click(screen.getByRole("button", { name: "Delete task" }));
    const confirm = within(dialog()).getByRole("button", { name: "Delete task" });
    expect(confirm).toBeDisabled();
    await userEvent.type(
      within(dialog()).getByLabelText(/Why is it deleted/),
      "Made twice by mistake",
    );
    await userEvent.click(confirm);
    expect(await screen.findByText("Task T000001 deleted.")).toBeInTheDocument();
    expect(router.state.location.pathname).toBe("/tasks");
    expect(calls.find((c) => c.path === "/api/v1/tasks/t1/delete")?.body).toEqual({
      reason: "Made twice by mistake",
    });
  });

  it("explains when a task cannot be deleted, and offers nothing to people who do not assign", async () => {
    fakeApi(
      signedInAs(["tasks.view", "tasks.assign"], {
        "GET /api/v1/tasks/t1": () => [200, task],
        "GET /api/v1/tasks/t1/timeline": () => [200, timeline],
        "GET /api/v1/projects/p1/members": () => [200, []],
        "POST /api/v1/tasks/t1/delete": () => [
          409,
          {
            error: {
              code: "TASK_HAS_WORK",
              message:
                "This task already has consent noted, so it is kept for the record. Cancel it instead.",
            },
          },
        ],
      }),
    );
    renderAt("/tasks/t1");
    await screen.findByRole("heading", { name: /^Task T000001/ });
    await userEvent.click(screen.getByRole("button", { name: "Delete task" }));
    await userEvent.type(within(dialog()).getByLabelText(/Why is it deleted/), "test");
    await userEvent.click(within(dialog()).getByRole("button", { name: "Delete task" }));
    // The window stays open with the reason typed, and says why.
    expect(await within(dialog()).findByText(/Cancel it instead/)).toBeInTheDocument();
    expect(within(dialog()).getByLabelText(/Why is it deleted/)).toHaveValue("test");
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
    await screen.findByRole("heading", { name: /^Task T000001/ });
    // No list of statuses to pick from: each action is its own button (UI review 2026-11-17).
    expect(screen.queryByLabelText("Move to")).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Put on hold" }));
    const apply = within(dialog()).getByRole("button", { name: "Put on hold" });
    expect(apply).toBeDisabled();
    expect(
      within(dialog()).getByRole("option", { name: "Waiting for a participant" }),
    ).toBeInTheDocument();
    await userEvent.selectOptions(
      within(dialog()).getByLabelText(/^Reason/),
      "WAITING_FOR_PARTICIPANT",
    );
    await userEvent.click(apply);
    expect(await screen.findByText("On hold.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Resume task" })).toBeInTheDocument();
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
      can_reassign: false,
      is_moderator: true,
      allowed_transitions: ["IN_PROGRESS"],
      consent_missing: [],
    };
    const { calls } = fakeApi(
      signedInAs(["tasks.view"], {
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
    expect(screen.getByText("Session started.")).toBeInTheDocument();
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
      signedInAs(["tasks.view", "recordings.view"], {
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
      allowed_transitions: ["APPROVED", "REJECTED"],
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

  it("approves many tasks at once (D-093)", async () => {
    const row = (id: string, code: string, status: string) => ({
      id,
      task_code: code,
      project_id: "p1",
      recording_mode: "FACE_TO_FACE",
      status,
      priority: "NORMAL",
      due_at: null,
      created_at: "2026-11-09T00:00:00Z",
    });
    const items = [
      row("t1", "T000001", "ADMIN_REVIEW"),
      row("t2", "T000002", "ADMIN_REVIEW"),
      row("t3", "T000003", "ASSIGNED"),
    ];
    const ready = {
      id: "r1",
      task_id: "t1",
      state: "READY",
      saved_seconds: 60,
      assets: [{ id: "as1", kind: "FTF_DERIVED_PCM" }],
    };
    const { calls } = fakeApi(
      signedInAs(["tasks.view", "tasks.assign", "recordings.download"], {
        "GET /api/v1/projects": () => [
          200,
          { items: [{ id: "p1", code: "VOICE" }], total: 1, page: 1, page_size: 100 },
        ],
        "GET /api/v1/tasks": () => [200, { items, total: 3, page: 1, page_size: 25 }],
        "POST /api/v1/tasks/t1/transition": () => [200, { ...task, status: "APPROVED" }],
        "POST /api/v1/tasks/t2/transition": () => [200, { ...task, status: "APPROVED" }],
        "GET /api/v1/tasks/t1/recordings": () => [200, [ready]],
        "GET /api/v1/tasks/t3/recordings": () => [200, []],
        "POST /api/v1/assets/as1/url": () => [
          200,
          { url: "https://files.example/a.wav", expires_in: 300 },
        ],
        "GET /api/v1/recordings/r1/consent-form": () => [200, "<html></html>"],
        "GET /api/v1/recordings/r1/metadata": () => [200, { task: "T000001" }],
      }),
    );
    renderAt("/tasks");
    await userEvent.click(await screen.findByLabelText("Select every task on this page"));
    expect(screen.getByText("3 selected")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Approve selected (2)" }));
    expect(
      await screen.findByText("2 approved. 1 skipped: not waiting for admin review."),
    ).toBeInTheDocument();
    expect(calls.filter((c) => c.path.endsWith("/transition")).map((c) => c.body)).toEqual([
      { to: "APPROVED", reason_code: null, comment: "" },
      { to: "APPROVED", reason_code: null, comment: "" },
    ]);

    expect(screen.queryByRole("button", { name: "Download audio and metadata" })).toBeNull();
  });

  it("shows consent from the participants' own forms and emails the form again to whoever has not agreed (D-127, D-129)", async () => {
    const { calls } = fakeApi(
      signedInAs(["tasks.view", "participants.manage"], {
        "GET /api/v1/tasks/t1": () => [
          200,
          {
            ...task,
            can_assign: false,
            can_reassign: false,
            is_moderator: true,
            allowed_transitions: ["IN_PROGRESS"],
            consent_missing: ["B"],
            participant_a: {
              ...task.participant_a,
              consent_status: "GIVEN",
              consent_at: "2026-11-09T01:00:00Z",
              may_record: true,
            },
          },
        ],
        "GET /api/v1/tasks/t1/timeline": () => [200, timeline],
        "POST /api/v1/projects/p1/participants/b1/portal-link/email": () => [
          201,
          { sent: true, expires_at: "2026-12-09T00:00:00Z" },
        ],
      }),
    );
    renderAt("/tasks/t1");
    const card = await screen.findByRole("region", { name: "Waiting for consent" });
    // Nobody ticks consent here: it comes from the forms. Only B, who has not agreed, is listed.
    expect(screen.queryByRole("button", { name: "Agreed" })).not.toBeInTheDocument();
    expect(within(card).queryByText("P000001")).not.toBeInTheDocument();
    expect(within(card).getByText("P000002")).toBeInTheDocument();
    expect(screen.getAllByText("Agreed").length).toBeGreaterThan(0); // A's chip in the facts
    await userEvent.click(within(card).getByRole("button", { name: "Email consent form again" }));
    expect(await screen.findByText("Consent form emailed to Name of P000002.")).toBeInTheDocument();
    expect(calls.some((c) => c.path.endsWith("/b1/portal-link/email"))).toBe(true);
    // Names sit next to the codes (D-128).
    expect(within(card).getByText("Name of P000002")).toBeInTheDocument();
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

  it("offers only people who agreed to the consent form for a new task (D-129)", async () => {
    const proj = {
      id: "p1",
      code: "PRJ0001",
      name: "Voice",
      status: "ACTIVE",
      allows_telephony: false,
      allows_face_to_face: true,
      languages: [],
    };
    const person = (code: string, consent_status: string) => ({
      id: code,
      participant_code: code,
      display_label: `Name ${code}`,
      has_phone: true,
      consent_status,
    });
    let people = [
      person("P000001", "GIVEN"),
      person("P000002", "GIVEN"),
      person("P000003", "NONE"),
      person("P000004", "REFUSED"),
    ];
    fakeApi(
      signedInAs(["tasks.view", "tasks.assign", "projects.view"], {
        "GET /api/v1/projects": () => [200, { items: [proj], total: 1, page: 1, page_size: 100 }],
        "GET /api/v1/projects/p1": () => [200, proj],
        "GET /api/v1/projects/p1/participants": () => [
          200,
          { items: people, total: people.length, page: 1, page_size: 100 },
        ],
        "GET /api/v1/projects/p1/members": () => [200, []],
      }),
    );
    renderAt("/tasks/new");
    await userEvent.selectOptions(await screen.findByLabelText("Project (active projects)"), "p1");
    expect(
      await screen.findByText("Only people who agreed to the consent form can be chosen."),
    ).toBeInTheDocument();
    const offered = within(screen.getByLabelText("Participant A"))
      .getAllByRole("option")
      .map((o) => o.textContent);
    expect(offered).toEqual([
      "Choose participant A",
      "P000001 Name P000001",
      "P000002 Name P000002",
    ]);
    cleanup();

    people = [person("P000001", "GIVEN"), person("P000003", "NONE")];
    renderAt("/tasks/new");
    await userEvent.selectOptions(await screen.findByLabelText("Project (active projects)"), "p1");
    expect(
      await screen.findByText(
        "Only people who agreed to the consent form can be chosen. Only 1 person here has agreed yet, and a task needs two.",
      ),
    ).toBeInTheDocument();
  });
});

describe("task page in plain words (UI review 2026-11-17)", () => {
  it("shows the history in words, not status codes", async () => {
    fakeApi(
      signedInAs(["tasks.view", "tasks.assign"], {
        "GET /api/v1/tasks/t1": () => [200, task],
        "GET /api/v1/tasks/t1/timeline": () => [200, timeline],
        "GET /api/v1/projects/p1/members": () => [200, []],
      }),
    );
    renderAt("/tasks/t1");
    expect(await screen.findByText("Draft → On hold")).toBeInTheDocument();
    expect(screen.getByText("Created as Draft")).toBeInTheDocument();
    expect(screen.getByText("Waiting for a participant · Back next week")).toBeInTheDocument();
    expect(screen.queryByText(/DRAFT -> ON_HOLD/)).not.toBeInTheDocument();
    // Priority and recording type as words.
    expect(screen.getByText("High")).toBeInTheDocument();
    expect(screen.getByText("Phone call")).toBeInTheDocument();
  });

  it("keeps the recorder closed until both people have agreed on their form (D-119)", async () => {
    fakeApi(
      signedInAs(["tasks.view"], {
        "GET /api/v1/tasks/t1": () => [
          200,
          {
            ...task,
            recording_mode: "FACE_TO_FACE",
            status: "IN_PROGRESS",
            can_assign: false,
            can_reassign: false,
            is_moderator: true,
            allowed_transitions: [],
            consent_missing: ["B"],
          },
        ],
        "GET /api/v1/tasks/t1/timeline": () => [200, timeline],
      }),
    );
    renderAt("/tasks/t1");
    const open = await screen.findByRole("button", { name: "Open the recorder" });
    expect(open).toBeDisabled();
    expect(open).toHaveAccessibleDescription(
      "Waiting for both people to agree on their consent form.",
    );
    expect(screen.queryByRole("link", { name: "Open the recorder" })).not.toBeInTheDocument();
  });

  it("lets the admin reject at the final approval, with a reason and a comment (D-118)", async () => {
    const review = {
      ...task,
      status: "ADMIN_REVIEW",
      recording_mode: "FACE_TO_FACE",
      can_reassign: false,
      allowed_transitions: ["APPROVED", "REJECTED"],
      reasons: { REJECTED: ["AUDIO_QUALITY", "OTHER"] },
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
        "POST /api/v1/tasks/t1/transition": () => [
          200,
          { ...review, status: "REJECTED", allowed_transitions: [] },
        ],
      }),
    );
    renderAt("/tasks/t1");
    expect(
      await screen.findByText("QC passed this recording. Listen, then approve or reject it."),
    ).toBeInTheDocument();
    expect(screen.queryByText(/send it back/)).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Approve" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Reject" }));
    await userEvent.selectOptions(within(dialog()).getByLabelText(/^Reason/), "OTHER");
    const confirm = within(dialog()).getByRole("button", { name: "Reject" });
    expect(confirm).toBeDisabled(); // Other needs a comment
    await userEvent.type(within(dialog()).getByLabelText(/^Comment/), "Wrong language");
    await userEvent.click(confirm);
    expect(await screen.findByText("Recording rejected.")).toBeInTheDocument();
    expect(calls.find((c) => c.path.endsWith("/transition"))?.body).toEqual({
      to: "REJECTED",
      reason_code: "OTHER",
      comment: "Wrong language",
    });
  });

  it("opens the task list filtered by the status and project in its address", async () => {
    const { calls } = fakeApi(
      signedInAs(["tasks.view", "tasks.assign"], {
        "GET /api/v1/projects": () => [
          200,
          { items: [{ id: "p1", code: "VOICE" }], total: 1, page: 1, page_size: 100 },
        ],
        "GET /api/v1/tasks": () => [200, { items: [task], total: 1, page: 1, page_size: 25 }],
      }),
    );
    renderAt("/tasks?status=AUDIO_QC&project=p1");
    await screen.findByText("T000001");
    expect(screen.getByLabelText("Status")).toHaveValue("AUDIO_QC");
    expect(screen.getByLabelText("Project")).toHaveValue("p1");
    expect(
      calls.some(
        (c) =>
          c.path.startsWith("/api/v1/tasks?") &&
          c.path.includes("status=AUDIO_QC") &&
          c.path.includes("project_id=p1"),
      ),
    ).toBe(true);
  });
});
