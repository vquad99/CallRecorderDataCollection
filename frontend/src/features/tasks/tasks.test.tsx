// Requirements: TASK-001, TASK-003, TASK-006, TASK-007, TASK-011, PART-006, SEC-001
import { act, cleanup, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { fakeApi, renderAt, signedInAs } from "../../test/fakeApi";
import {
  ALL_PERMISSIONS,
  DEVICE_DETAILS,
  PROJECT,
  TASK,
  TASK_ROW,
  worldHandlers,
} from "../../test/world";

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
  // Nothing has happened on it yet: Delete is offered (FEW-12, D-115).
  can_delete: true,
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
    // D-159: a project code in plain monospace, as the task's and the people's codes.
    expect(within(row).getByText("VOICE")).toHaveClass("mono");
    // D-159: New task among the title row's actions, so on a phone it fills its row.
    expect(screen.getByRole("link", { name: "New task" }).parentElement).toHaveClass("actions");
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
      current: true,
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
      current: true,
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
    // D-159: the fields are a section with its title on a bar; Create task stays at its foot.
    const details = screen.getByRole("form", { name: "Task details" });
    expect(details.firstElementChild).toHaveTextContent(/^Task details$/);
    expect(details.lastElementChild).toBe(
      within(details).getByRole("button", { name: "Create task" }),
    );
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
    // Nothing checked yet: no count on the button (POL-14).
    expect(screen.getByRole("button", { name: "Add tasks" })).toBeDisabled();
    await userEvent.type(
      screen.getByLabelText("Tasks (CSV)"),
      "participant_a,participant_b{enter}P000001,P000002",
    );
    await userEvent.click(screen.getByRole("button", { name: "Check rows" }));
    expect(await screen.findByText("1 of 1 rows are ready.")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Add 1 task" }));
    expect(await screen.findByText("1 task added.")).toBeInTheDocument();
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

describe("new task: the project's pairing rules (D-143)", () => {
  it("greys out who cannot be chosen and says why; the server stays the judge", async () => {
    const proj = {
      id: "p1",
      code: "PRJ0001",
      name: "Konkani",
      status: "ACTIVE",
      allows_telephony: false,
      allows_face_to_face: true,
      languages: [],
      max_conversations_per_speaker: 3,
      unique_pairs: true,
      speaker_min_age: 20,
      speaker_max_age: 60,
      required_speaker_details: ["age", "gender"],
    };
    const person = (
      code: string,
      conversations: number,
      pairedWith: string[],
      complete = true,
      age = 30,
    ) => ({
      id: code,
      participant_code: code,
      display_label: `Name ${code}`,
      has_phone: true,
      consent_status: "GIVEN",
      speaker_details_complete: complete,
      age,
      pairing: { conversations, paired_with: pairedWith },
    });
    const people = [
      person("P000001", 1, ["P000002"]),
      person("P000002", 1, ["P000001"]),
      person("P000003", 0, [], false),
      person("P000004", 3, ["P000007", "P000008", "P000009"]),
      person("P000005", 1, ["P000006"]),
      person("P000006", 1, ["P000005"]),
      // Older than the project's speakers (D-145).
      person("P000007", 0, [], true, 65),
    ];
    const { calls } = fakeApi(
      signedInAs(["tasks.view", "tasks.assign", "projects.view"], {
        "GET /api/v1/projects": () => [200, { items: [proj], total: 1, page: 1, page_size: 100 }],
        "GET /api/v1/projects/p1": () => [200, proj],
        "GET /api/v1/projects/p1/participants": () => [
          200,
          { items: people, total: people.length, page: 1, page_size: 100 },
        ],
        "GET /api/v1/projects/p1/members": () => [200, []],
        "POST /api/v1/tasks": () => [
          409,
          {
            error: {
              code: "PAIR_ALREADY_USED",
              message: "P000001 and P000005 already have a conversation together in this project.",
            },
          },
        ],
      }),
    );
    renderAt("/tasks/new");
    await userEvent.selectOptions(await screen.findByLabelText("Project (active projects)"), "p1");
    // A face-to-face project: its tasks take its type, nothing to choose (D-153).
    expect(await screen.findByText("(the project's type)")).toBeInTheDocument();
    expect(screen.queryByRole("combobox", { name: "Recording type" })).toBeNull();
    const options = (label: string) =>
      within(screen.getByLabelText(label))
        .getAllByRole("option")
        .slice(1)
        .map((o) => [o.textContent, (o as HTMLOptionElement).disabled]);
    expect(options("Participant A")).toEqual([
      ["P000001 Name P000001", false],
      ["P000002 Name P000002", false],
      ["P000003 Name P000003 – details missing", true],
      ["P000004 Name P000004 – 3 conversations already", true],
      ["P000005 Name P000005", false],
      ["P000006 Name P000006", false],
      ["P000007 Name P000007 – outside the ages 20 to 60", true],
    ]);
    expect(
      screen.getByText(
        "Greyed-out people cannot be chosen now; the reason is after their name. A task needs " +
          "the speaker details the project asks for, speakers aged 20 to 60, at most 3 " +
          "conversations per speaker, and each pair of speakers only once.",
      ),
    ).toBeInTheDocument();
    await userEvent.selectOptions(screen.getByLabelText("Participant A"), "P000001");
    expect(options("Participant B")).toEqual([
      ["P000002 Name P000002 – already paired with the chosen A", true],
      ["P000003 Name P000003 – details missing", true],
      ["P000004 Name P000004 – 3 conversations already", true],
      ["P000005 Name P000005", false],
      ["P000006 Name P000006", false],
      ["P000007 Name P000007 – outside the ages 20 to 60", true],
    ]);
    await userEvent.selectOptions(screen.getByLabelText("Participant B"), "P000005");
    // Another A who may still be paired with B keeps B; one B worked with clears it (below).
    await userEvent.selectOptions(screen.getByLabelText("Participant A"), "P000002");
    expect(screen.getByLabelText("Participant B")).toHaveValue("P000005");
    // The server stays the judge: its answer is shown as it is.
    await userEvent.selectOptions(screen.getByLabelText("Participant A"), "P000001");
    await userEvent.click(screen.getByRole("button", { name: "Create task" }));
    expect(
      await screen.findByText(
        "P000001 and P000005 already have a conversation together in this project.",
      ),
    ).toBeInTheDocument();
    const posted = calls.filter((c) => c.method === "POST" && c.path === "/api/v1/tasks");
    expect(posted).toHaveLength(1);
    expect(posted[0]?.body).toMatchObject({ recording_mode: "FACE_TO_FACE" });
  });

  it("clears B when the new A has already been paired with them", async () => {
    const proj = {
      id: "p1",
      code: "PRJ0001",
      name: "Konkani",
      status: "ACTIVE",
      allows_telephony: false,
      allows_face_to_face: true,
      languages: [],
      max_conversations_per_speaker: null,
      unique_pairs: true,
      speaker_min_age: 20,
      speaker_max_age: 60,
      required_speaker_details: ["age", "gender"],
    };
    const person = (code: string, pairedWith: string[]) => ({
      id: code,
      participant_code: code,
      display_label: null,
      has_phone: true,
      consent_status: "GIVEN",
      speaker_details_complete: true,
      pairing: { conversations: pairedWith.length, paired_with: pairedWith },
    });
    const people = [
      person("P000001", []),
      person("P000002", ["P000003"]),
      person("P000003", ["P000002"]),
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
    await userEvent.selectOptions(await screen.findByLabelText("Participant A"), "P000001");
    await userEvent.selectOptions(screen.getByLabelText("Participant B"), "P000002");
    await userEvent.selectOptions(screen.getByLabelText("Participant A"), "P000003");
    expect((screen.getByLabelText("Participant B") as HTMLSelectElement).value).toBe("");
    // No limit in this project: the sentence leaves it out.
    expect(
      screen.getByText(
        "Greyed-out people cannot be chosen now; the reason is after their name. A task needs " +
          "the speaker details the project asks for, speakers aged 20 to 60, and each pair of " +
          "speakers only once.",
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

  it("takes every filter off with Clear filters, in the page's filter bar (D-158)", async () => {
    const { calls } = fakeApi(
      signedInAs(["tasks.view", "tasks.assign"], {
        "GET /api/v1/projects": () => [
          200,
          { items: [{ id: "p1", code: "VOICE" }], total: 1, page: 1, page_size: 100 },
        ],
        "GET /api/v1/tasks": () => [200, { items: [task], total: 1, page: 1, page_size: 25 }],
      }),
    );
    renderAt("/tasks?status=AUDIO_QC&project=p1&mode=TELEPHONY&page=2");
    await screen.findByText("T000001");
    const filters = screen.getByRole("group", { name: "Filters" });
    await userEvent.click(within(filters).getByRole("button", { name: "Clear filters" }));
    expect(within(filters).getByLabelText("Status")).toHaveValue("");
    expect(within(filters).getByLabelText("Project")).toHaveValue("");
    expect(within(filters).getByLabelText("Recording type")).toHaveValue("");
    // Nothing left to clear: the button goes; the list is asked again from page 1, unfiltered.
    expect(within(filters).queryByRole("button", { name: "Clear filters" })).toBeNull();
    await waitFor(() =>
      expect(calls.filter((c) => c.path.startsWith("/api/v1/tasks?")).at(-1)?.path).not.toMatch(
        /status=|project_id=|mode=|page=2/,
      ),
    );
  });
});

describe("one task on one screen (D-152)", () => {
  const entry = (n: number, from: string, to: string) => ({
    at: `2026-11-1${n}T00:00:00Z`,
    kind: "status",
    actor: "Ada",
    text: "",
    from_status: from,
    to_status: to,
    reason_code: null,
    comment: null,
  });
  const history = [
    entry(0, "", "DRAFT"),
    entry(1, "DRAFT", "ASSIGNED"),
    entry(2, "ASSIGNED", "ON_HOLD"),
    entry(3, "ON_HOLD", "ASSIGNED"),
    entry(4, "ASSIGNED", "ON_HOLD"),
  ].map((e, i) => (i === 0 ? { ...e, from_status: null } : e));

  it("shows the summary, both people as one matrix and the newest history beside the work", async () => {
    fakeApi(
      signedInAs(ALL_PERMISSIONS, {
        ...worldHandlers(),
        "GET /api/v1/tasks/t1/timeline": () => [200, history],
      }),
    );
    renderAt("/tasks/t1");
    const side = await screen.findByRole("complementary", { name: "About this task" });
    // Who acts next, where the work would be: nothing for this person to do now.
    expect(screen.getByRole("region", { name: "Next step" })).toHaveTextContent(
      "Waiting for Mona Moderator to start the session.",
    );
    const summary = within(side).getByRole("region", { name: "Summary" });
    // D-159: its lines run edge to edge, as the participants table's under it.
    expect(summary.querySelector("dl")).toHaveClass("facts", "bleed");
    expect(summary).toHaveTextContent("ModeratorMona Moderator");
    expect(summary).toHaveTextContent("Recording typeFace-to-face");
    // The browser tab names the task (UXA-08).
    await waitFor(() => expect(document.title).toMatch(/^Task T000001 · /));
    // The project the task belongs to, first, with the way to it (UXW-04).
    expect(summary).toHaveTextContent(/^SummaryProjectHINDI · Hindi conversations/);
    expect(within(summary).getByRole("link", { name: "HINDI" })).toHaveAttribute(
      "href",
      "/projects/p1",
    );
    // A row per fact, a column per person.
    const people = within(side).getByRole("table", { name: "Both participants" });
    const rows = within(people)
      .getAllByRole("row")
      .map((row) => Array.from(row.children, (cell) => cell.textContent).join(" | "));
    expect(rows).toEqual([
      "Detail | Participant A | Participant B",
      "Code | P000001 | P000002",
      "Name | Asha | Bina",
      "Consent | Agreed | Agreed",
      "Device details | Not yet | Not yet",
      "Speaker details | View | View",
    ]);
    expect(
      within(people).getByRole("button", { name: "View the details of P000002" }),
    ).toBeInTheDocument();
    // The newest three entries first; the rest on request.
    const log = within(side).getByRole("region", { name: "History" });
    const titles = () =>
      Array.from(log.querySelectorAll(".timeline__title"), (el) => el.textContent);
    await within(log).findByText("On hold → Assigned");
    expect(titles()).toEqual(["Assigned → On hold", "On hold → Assigned", "Assigned → On hold"]);
    // D-159: when, who and what each stay whole; the line breaks only after a dot.
    const meta = log.querySelector(".timeline li > .muted") as HTMLElement;
    expect(Array.from(meta.querySelectorAll(".nowrap"), (s) => s.textContent)).toEqual([
      expect.stringMatching(/^14 Nov 2026, .+ IST ·$/),
      "Ada ·",
      "Status changed",
    ]);
    // D-159: the compact button every other section's bar has for the same, not a text link.
    const more = within(log).getByRole("button", { name: "Show all (5)" });
    expect(more).toHaveClass("button", "button--secondary");
    await userEvent.click(more);
    expect(titles()).toHaveLength(5);
    expect(titles()[4]).toBe("Created as Draft");
    expect(within(log).getByRole("button", { name: "Show fewer" })).toHaveAttribute(
      "aria-expanded",
      "true",
    );
  });

  it("asks for a moderator in the work column while nobody is assigned", async () => {
    fakeApi(
      signedInAs(ALL_PERMISSIONS, {
        ...worldHandlers(),
        "GET /api/v1/tasks/t1": () => [
          200,
          { ...TASK, status: "DRAFT", moderator_id: null, moderator_name: null },
        ],
      }),
    );
    renderAt("/tasks/t1");
    expect(await screen.findByRole("heading", { name: "Assign moderator" })).toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "Next step" })).toBeNull();
    expect(screen.queryByText("Reassign moderator")).toBeNull();
  });

  it("shows a rejected task stopped at the step it ended at (FEW-11)", async () => {
    fakeApi(
      signedInAs(ALL_PERMISSIONS, {
        ...worldHandlers(),
        "GET /api/v1/tasks/t1": () => [
          200,
          {
            ...TASK,
            status: "REJECTED",
            ended_from: "AUDIO_QC",
            allowed_transitions: [],
            can_reassign: false,
            can_delete: false,
          },
        ],
      }),
    );
    renderAt("/tasks/t1");
    const steps = await screen.findByRole("img", { name: "Workflow progress: Rejected" });
    const states = Array.from(steps.querySelectorAll(".stepper__step"), (s) =>
      [...s.classList].find((c) => c.startsWith("stepper__step--"))?.replace("stepper__step--", ""),
    );
    expect(states).toEqual(["done", "done", "done", "done", "halted", "todo", "todo"]);
    expect(steps.querySelector(".stepper__step--halted")).toHaveAttribute("data-label", "Audio QC");
  });

  it("offers Delete only where the server says it can work (FEW-12)", async () => {
    const cancelled = {
      ...task,
      status: "CANCELLED",
      allowed_transitions: [],
      can_reassign: false,
      consent_missing: [],
    };
    fakeApi(
      signedInAs(["tasks.view", "tasks.assign"], {
        "GET /api/v1/tasks/t1": () => [200, { ...cancelled, can_delete: false }],
        "GET /api/v1/tasks/t1/timeline": () => [200, timeline],
        "GET /api/v1/tasks/t2": () => [200, { ...cancelled, id: "t2", task_code: "T000002" }],
        "GET /api/v1/tasks/t2/timeline": () => [200, timeline],
      }),
    );
    const router = renderAt("/tasks/t1");
    // Cancelled after a recording: kept for the record, nothing to delete.
    await screen.findByRole("heading", { name: /^Task T000001/ });
    expect(screen.queryByRole("button", { name: "Delete task" })).toBeNull();
    // Cancelled before anything happened on it: it can still go (D-115).
    await act(async () => {
      await router.navigate("/tasks/t2");
    });
    await screen.findByRole("heading", { name: /^Task T000002/ });
    expect(screen.getByRole("button", { name: "Delete task" })).toBeInTheDocument();
  });

  it("leaves a task's message on that task when another task opens (FEW-14)", async () => {
    const held = {
      ...task,
      status: "ON_HOLD",
      held_from: "ASSIGNED",
      allowed_transitions: ["ASSIGNED", "CANCELLED"],
    };
    fakeApi(
      signedInAs(["tasks.view", "tasks.assign"], {
        "GET /api/v1/tasks/t1": () => [200, held],
        "GET /api/v1/tasks/t1/timeline": () => [200, timeline],
        "GET /api/v1/projects/p1/members": () => [200, []],
        "POST /api/v1/tasks/t1/transition": () => [200, task],
        "GET /api/v1/tasks/t2": () => [200, { ...task, id: "t2", task_code: "T000002" }],
        "GET /api/v1/tasks/t2/timeline": () => [200, timeline],
      }),
    );
    const router = renderAt("/tasks/t1");
    await userEvent.click(await screen.findByRole("button", { name: "Resume task" }));
    expect(await screen.findByText("Task resumed.")).toBeInTheDocument();
    // The same page, another task (as a participant's Sessions link opens it).
    await act(async () => {
      await router.navigate("/tasks/t2");
    });
    expect(await screen.findByRole("heading", { name: /^Task T000002/ })).toBeInTheDocument();
    expect(screen.queryByText("Task resumed.")).toBeNull();
  });

  it("keeps a titled page with the way back when the task cannot be shown (POL-13)", async () => {
    fakeApi(
      signedInAs(["tasks.view"], {
        "GET /api/v1/tasks/t1": () => [
          404,
          { error: { code: "NOT_FOUND", message: "Task not found", request_id: "r1" } },
        ],
      }),
    );
    renderAt("/tasks/t1");
    expect(await screen.findByRole("heading", { level: 2, name: "Not found" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 1, name: "Task" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "All tasks" })).toHaveAttribute("href", "/tasks");
  });
});

describe("a cancelled task keeps its records (FEW-10)", () => {
  const cancelled = {
    ...TASK,
    status: "CANCELLED",
    ended_from: "RECORDED",
    allowed_transitions: [],
    can_reassign: false,
    can_delete: false,
  };
  const AUTO = {
    id: "q1",
    recording_id: "r1",
    asset_id: "as1",
    automated: true,
    outcome: "PASS",
    reason_code: null,
    comment: "Passed every check",
    reviewer_name: null,
    created_at: "2026-11-10T09:00:00Z",
    checks: [],
  };
  const qcView = (results: unknown[]) => ({
    task_status: "CANCELLED",
    pass_approves: false,
    qc_user_id: null,
    qc_name: null,
    can_decide: false,
    can_assign: false,
    can_recheck: false,
    reasons: { FAIL: [] },
    results,
  });
  const recording = {
    id: "r1",
    task_id: "t1",
    state: "READY",
    current: true,
    saved_seconds: 600,
    assets: [{ id: "as1", kind: "FTF_DERIVED_PCM", sample_rate: 16000, channels: 1 }],
  };
  const [partyA, partyB] = DEVICE_DETAILS.participants;

  it("shows the recording, its audio check and the device details it had, read only", async () => {
    fakeApi(
      signedInAs(ALL_PERMISSIONS, {
        ...worldHandlers(),
        "GET /api/v1/tasks/t1": () => [200, cancelled],
        "GET /api/v1/tasks/t1/recordings": () => [200, [recording]],
        "GET /api/v1/tasks/t1/audio-qc": () => [200, qcView([AUTO])],
        "GET /api/v1/tasks/t1/device-details": () => [
          200,
          {
            ...DEVICE_DETAILS,
            editable: false,
            participants: [
              {
                ...partyA,
                details: { ...partyA?.details, device_make: "Samsung" },
                filled_by: "Mona Moderator",
                filled_at: "2026-11-10T08:00:00Z",
              },
              partyB,
            ],
          },
        ],
      }),
    );
    renderAt("/tasks/t1");
    expect(
      await screen.findByRole("region", { name: "Recordings" }, { timeout: 5000 }),
    ).toHaveTextContent("Recording 1");
    expect(await screen.findByRole("region", { name: "Audio quality" })).toHaveTextContent(
      "Passed every check",
    );
    const devices = await screen.findByRole("region", { name: "Device details" });
    expect(await within(devices).findByText("Samsung")).toBeInTheDocument();
    expect(within(devices).queryByRole("textbox")).toBeNull();
    // The progress line stops where the task was cancelled.
    const steps = screen.getByRole("img", { name: "Workflow progress: Cancelled" });
    expect(steps.querySelector(".stepper__step--halted")).toHaveAttribute("data-label", "Recorded");
  });

  it("shows none of them for a task cancelled before anything was recorded", async () => {
    const { calls } = fakeApi(
      signedInAs(ALL_PERMISSIONS, {
        ...worldHandlers(),
        "GET /api/v1/tasks/t1": () => [200, { ...cancelled, ended_from: "ASSIGNED" }],
        "GET /api/v1/tasks/t1/recordings": () => [200, []],
        "GET /api/v1/tasks/t1/audio-qc": () => [200, qcView([])],
        "GET /api/v1/tasks/t1/device-details": () => [200, { ...DEVICE_DETAILS, editable: false }],
      }),
    );
    renderAt("/tasks/t1");
    const people = await screen.findByRole("table", { name: "Both participants" });
    const deviceRow = () => within(people).getByRole("rowheader", { name: "Device details" });
    // Not "Not yet": the details were asked, and nobody filled them.
    await waitFor(() =>
      expect(deviceRow().closest("tr")).toHaveTextContent("Device detailsNot filledNot filled"),
    );
    await waitFor(() =>
      expect(
        ["/recordings", "/audio-qc"].every((end) =>
          calls.some((c) => c.path === `/api/v1/tasks/t1${end}`),
        ),
      ).toBe(true),
    );
    await act(async () => {});
    for (const name of ["Recordings", "Audio quality", "Device details"])
      expect(screen.queryByRole("region", { name })).toBeNull();
    const summary = screen.getByRole("region", { name: "Summary" });
    expect(summary).not.toHaveTextContent("QC Executive");
    expect(screen.getByRole("region", { name: "Next step" })).toHaveTextContent(
      "Cancelled. The task has ended.",
    );
  });
});

describe("the task list (UXW-05, UXA-11, PERF-09)", () => {
  const row = (id: string, code: string, moderator: string | null, mode = "FACE_TO_FACE") => ({
    ...TASK_ROW,
    id,
    task_code: code,
    recording_mode: mode,
    moderator_name: moderator,
    participant_a_code: "P000196",
    participant_b_code: "P000197",
  });

  it("shows people who assign tasks who holds each task and its two people", async () => {
    const page = { items: [row("t1", "T000001", "Mona Moderator"), row("t2", "T000002", null)] };
    fakeApi(
      signedInAs(["tasks.view", "tasks.assign"], {
        "GET /api/v1/projects": () => [
          200,
          { items: [PROJECT], total: 1, page: 1, page_size: 100 },
        ],
        "GET /api/v1/tasks": () => [200, { ...page, total: 2, page: 1, page_size: 25 }],
      }),
    );
    renderAt("/tasks");
    const line = async (code: string) =>
      (await screen.findByRole("link", { name: code })).closest("tr") as HTMLElement;
    const first = await line("T000001");
    expect(within(first).getByText("Mona Moderator")).toBeInTheDocument();
    expect(within(first).getByText("P000196 · P000197")).toBeInTheDocument();
    expect(within(await line("T000002")).getByText("Not assigned")).toHaveClass("muted");
    const headers = screen.getAllByRole("columnheader").map((h) => h.textContent);
    expect(headers.slice(1)).toEqual([
      "Task",
      "Project",
      "Participants",
      "Recording type",
      "Status",
      "Moderator",
      "Priority",
      "Due",
    ]);
    cleanup();

    // A moderator's list holds only their own tasks: no such columns.
    fakeApi(
      signedInAs(["tasks.view"], {
        "GET /api/v1/projects": () => [
          200,
          { items: [PROJECT], total: 1, page: 1, page_size: 100 },
        ],
        "GET /api/v1/tasks": () => [200, { ...page, total: 2, page: 1, page_size: 25 }],
      }),
    );
    renderAt("/tasks");
    await screen.findByRole("link", { name: "T000001" });
    expect(screen.queryByRole("columnheader", { name: "Moderator" })).toBeNull();
    expect(screen.queryByRole("columnheader", { name: "Participants" })).toBeNull();
    expect(screen.queryByText("P000196 · P000197")).toBeNull();
  });

  it("has no recording type to choose on the Tasks tab of a one-type project", async () => {
    const phoneOnly = { ...PROJECT, allows_face_to_face: false };
    let items = [row("t1", "T000001", "Mona Moderator", "TELEPHONY")];
    const { calls } = fakeApi(
      signedInAs(ALL_PERMISSIONS, {
        ...worldHandlers(),
        "GET /api/v1/projects/p1": () => [200, phoneOnly],
        "GET /api/v1/tasks": () => [200, { items, total: items.length, page: 1, page_size: 25 }],
      }),
    );
    // An old link with a type in it changes nothing.
    renderAt("/projects/p1/tasks?mode=FACE_TO_FACE");
    expect(await screen.findByRole("link", { name: "T000001" })).toBeInTheDocument();
    expect(screen.getByText("1 task in this project")).toBeInTheDocument();
    expect(screen.queryByLabelText("Recording type")).toBeNull();
    expect(screen.queryByRole("columnheader", { name: "Recording type" })).toBeNull();
    expect(calls.find((c) => c.path.startsWith("/api/v1/tasks?"))?.path).not.toContain("mode=");
    cleanup();

    // A task of the other type, made before the project kept to one: the column says which.
    items = [...items, row("t2", "T000002", null, "FACE_TO_FACE")];
    renderAt("/projects/p1/tasks");
    expect(await screen.findByRole("columnheader", { name: "Recording type" })).toBeInTheDocument();
    expect(screen.queryByLabelText("Recording type")).toBeNull();
  });

  it("names the project of a task past the first 100 projects", async () => {
    const newer = Array.from({ length: 100 }, (_, i) => ({
      ...PROJECT,
      id: `n${i}`,
      code: `N${i}`,
    }));
    const { calls } = fakeApi(
      signedInAs(["tasks.view", "tasks.assign"], {
        "GET /api/v1/projects": (_body, url) =>
          url.searchParams.get("page") === "2"
            ? [
                200,
                { items: [{ ...PROJECT, code: "OLDEST" }], total: 101, page: 2, page_size: 100 },
              ]
            : [200, { items: newer, total: 101, page: 1, page_size: 100 }],
        "GET /api/v1/tasks": () => [
          200,
          { items: [row("t1", "T000001", null)], total: 1, page: 1, page_size: 25 },
        ],
      }),
    );
    renderAt("/tasks");
    const line = (await screen.findByRole("link", { name: "T000001" })).closest(
      "tr",
    ) as HTMLElement;
    await waitFor(() => expect(within(line).getByText("OLDEST")).toBeInTheDocument());
    expect(within(screen.getByLabelText("Project")).getAllByRole("option")).toHaveLength(102);
    expect(calls.filter((c) => c.path.startsWith("/api/v1/projects?"))).toHaveLength(2);
  });
});

describe("new task: finding participants in a large project (FEW-04)", () => {
  const proj = {
    id: "p1",
    code: "PRJ0001",
    name: "Voice",
    status: "ACTIVE",
    allows_telephony: false,
    allows_face_to_face: true,
    languages: [],
  };
  const person = (n: number) => ({
    id: `p${n}`,
    participant_code: `P${String(n).padStart(6, "0")}`,
    display_label: `Speaker ${n}`,
    has_phone: true,
    consent_status: "GIVEN",
  });
  // 150 people who all agreed; the server pages 25 at a time and searches code and name.
  const everyone = Array.from({ length: 150 }, (_, i) => person(i + 1));

  it("finds someone past the first page by code or name, and keeps the people chosen", async () => {
    const { calls } = fakeApi(
      signedInAs(["tasks.view", "tasks.assign", "projects.view"], {
        "GET /api/v1/projects": () => [200, { items: [proj], total: 1, page: 1, page_size: 100 }],
        "GET /api/v1/projects/p1": () => [200, proj],
        "GET /api/v1/projects/p1/participants": (_body, url) => {
          const term = (url.searchParams.get("search") ?? "").toLowerCase();
          const size = Number(url.searchParams.get("page_size"));
          const found = everyone.filter(
            (p) =>
              p.participant_code.toLowerCase().includes(term) ||
              p.display_label.toLowerCase().includes(term),
          );
          return [
            200,
            { items: found.slice(0, size), total: found.length, page: 1, page_size: size },
          ];
        },
        "GET /api/v1/projects/p1/members": () => [200, []],
        "POST /api/v1/tasks": () => [201, { ...TASK, id: "t9" }],
        "GET /api/v1/tasks/t9": () => [200, { ...TASK, id: "t9" }],
      }),
    );
    renderAt("/tasks/new");
    await userEvent.selectOptions(await screen.findByLabelText("Project (active projects)"), "p1");
    expect(
      await screen.findByText("Showing 25 of 150: type a code or name to find others."),
    ).toBeInTheDocument();
    // Everyone listed agreed: the 125 not listed are not "left out".
    expect(screen.queryByText(/Only people who agreed/)).toBeNull();
    const offered = (label: string) =>
      within(screen.getByLabelText(label))
        .getAllByRole("option")
        .slice(1)
        .map((o) => o.textContent);
    expect(offered("Participant A")).toHaveLength(25);
    await userEvent.selectOptions(screen.getByLabelText("Participant A"), "p2");
    await userEvent.selectOptions(screen.getByLabelText("Participant B"), "p3");
    // P000150 is past the first page: found by its code. Enter finds, it never sends the form.
    const find = screen.getByLabelText("Find participant (code or name)");
    await userEvent.type(find, "P000150{enter}");
    await waitFor(() =>
      expect(offered("Participant B")).toEqual(["P000003 Speaker 3", "P000150 Speaker 150"]),
    );
    // The people chosen stay chosen, at the top of their lists.
    expect(screen.getByLabelText("Participant A")).toHaveValue("p2");
    expect(offered("Participant A")).toEqual(["P000002 Speaker 2", "P000150 Speaker 150"]);
    await userEvent.selectOptions(screen.getByLabelText("Participant B"), "p150");
    // By name too.
    await userEvent.clear(find);
    await userEvent.type(find, "speaker 149");
    await waitFor(() => expect(offered("Participant A")).toContain("P000149 Speaker 149"));
    expect(screen.getByLabelText("Participant B")).toHaveValue("p150");
    expect(calls.filter((c) => c.method === "POST")).toHaveLength(0);
    await userEvent.click(screen.getByRole("button", { name: "Create task" }));
    await waitFor(() =>
      expect(calls.find((c) => c.method === "POST")?.body).toMatchObject({
        participant_a_id: "p2",
        participant_b_id: "p150",
      }),
    );
    expect(calls.filter((c) => c.method === "POST")).toHaveLength(1);
    expect(
      calls.some((c) => c.path.includes("search=P000150") && c.path.includes("page_size=25")),
    ).toBe(true);
  });

  it("says when nobody matches, and keeps the too-few notice for the whole project", async () => {
    fakeApi(
      signedInAs(["tasks.view", "tasks.assign", "projects.view"], {
        "GET /api/v1/projects": () => [200, { items: [proj], total: 1, page: 1, page_size: 100 }],
        "GET /api/v1/projects/p1": () => [200, proj],
        "GET /api/v1/projects/p1/participants": (_body, url) =>
          url.searchParams.get("search")
            ? [200, { items: [], total: 0, page: 1, page_size: 25 }]
            : [200, { items: everyone.slice(0, 25), total: 150, page: 1, page_size: 25 }],
        "GET /api/v1/projects/p1/members": () => [200, []],
      }),
    );
    renderAt("/tasks/new");
    await userEvent.selectOptions(await screen.findByLabelText("Project (active projects)"), "p1");
    await userEvent.type(await screen.findByLabelText("Find participant (code or name)"), "Nobody");
    expect(await screen.findByText("Nobody in this project matches “Nobody”.")).toBeInTheDocument();
    // An empty search result is not a project without participants.
    expect(screen.queryByText(/This project has no participants/)).toBeNull();
  });
});
