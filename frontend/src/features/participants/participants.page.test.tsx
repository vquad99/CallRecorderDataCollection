// Participants section (D-073, D-129). Requirements: PART-006, PART-016
import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { fakeApi, renderAt, signedInAs } from "../../test/fakeApi";
import {
  ALL_PERMISSIONS,
  PARTICIPANT,
  PARTICIPANT_B,
  PROJECT,
  worldHandlers,
} from "../../test/world";

afterEach(() => vi.unstubAllGlobals());

const wait = { timeout: 5000 };

/** The page with its project chosen: nothing is chosen for the person (D-114). */
async function openList() {
  renderAt("/participants");
  await userEvent.selectOptions(await screen.findByLabelText("Project", {}, wait), "p1");
}

const DETAILS = {
  participant: { ...PARTICIPANT, notes: "Prefers evening calls" },
  updated_at: "2026-11-12T10:00:00Z",
  added_by: "Priya Admin",
  projects: [
    { id: "p1", code: "HINDI", name: "Hindi conversations" },
    { id: "p2", code: "TAMIL", name: "Tamil talks" },
  ],
  removed: null,
  link: {
    active: true,
    created_at: "2026-11-09T06:00:00Z",
    created_by: "Priya Admin",
    expires_at: "2026-12-09T06:00:00Z",
    last_used_at: "2026-11-10T08:00:00Z",
    handed_out: false,
  },
  consent_form: {
    participant_code: "P000001",
    project_code: "HINDI",
    project_name: "Hindi conversations",
    form_text: "I agree that my voice is recorded.",
    form_version: "2",
    answered: true,
    current: {
      status: "GIVEN",
      answered_at: "2026-11-10T08:00:00Z",
      policy_version: "2",
    },
    earlier: [
      {
        status: "REFUSED",
        answered_at: "2026-11-09T08:00:00Z",
        policy_version: "1",
      },
    ],
  },
  sessions: [
    {
      task_id: "t7",
      task_code: "T000007",
      mode: "TELEPHONY",
      slot: "A",
      status: "RECORDED",
      created_at: "2026-11-11T05:00:00Z",
      other_participant_code: "P000002",
      moderator: "Mohan",
      recordings: 1,
      recording_seconds: 420,
      recorded_at: "2026-11-11T05:12:00Z",
      phone_calls: 3,
    },
    {
      task_id: "t3",
      task_code: "T000003",
      mode: "FACE_TO_FACE",
      slot: "B",
      status: "ASSIGNED",
      created_at: "2026-11-10T05:00:00Z",
      other_participant_code: "P000004",
      moderator: null,
      recordings: 0,
      recording_seconds: null,
      recorded_at: null,
      phone_calls: 0,
    },
  ],
  sessions_total: 2,
  minutes: {
    conversations: 1,
    recorded_minutes: 7,
    approved_conversations: 1,
    approved_minutes: 7,
    payable_minutes: 3.5,
  },
  calls: {
    total: 3,
    recorded: 1,
    last_at: "2026-11-11T05:05:00Z",
    last_state: "RECORDED",
  },
};

function open(extra: Parameters<typeof signedInAs>[1] = {}) {
  return fakeApi(signedInAs(ALL_PERMISSIONS, { ...worldHandlers(), ...extra }));
}

describe("participants section", () => {
  it("shows nothing and offers no action until a project is chosen (D-114)", async () => {
    const { calls } = open();
    renderAt("/participants");
    expect(
      await screen.findByRole("heading", { name: "Choose a project" }, wait),
    ).toBeInTheDocument();
    expect(screen.getByLabelText("Project")).toHaveValue("");
    expect(screen.getByRole("button", { name: "Add participant" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Add many" })).toBeDisabled();
    expect(screen.queryByText("P000001")).toBeNull();
    expect(screen.queryByLabelText("Select all on this page")).toBeNull();
    expect(calls.some((c) => c.path.startsWith("/api/v1/projects/p1/participants"))).toBe(false);
    await userEvent.selectOptions(screen.getByLabelText("Project"), "p1");
    expect(await screen.findByText("P000001", {}, wait)).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Choose a project" })).toBeNull();
  });

  it("is in the menu and lists the project's participants with their consent state", async () => {
    open();
    await openList();
    expect(await screen.findByText("P000001", {}, wait)).toBeInTheDocument();
    expect(screen.getByRole("navigation", { name: "Main" })).toHaveTextContent("Participants");
    const row = screen.getByText("P000001").closest("tr") as HTMLElement;
    expect(within(row).getByText("Agreed")).toBeInTheDocument();
    // The language in words, not its code.
    expect(within(row).getByText("Hindi (hi)")).toBeInTheDocument();
  });

  it("has nothing to review and sends the form again only to people who have not agreed (D-129)", async () => {
    const waiting = { ...PARTICIPANT_B, consent_status: "NONE" };
    const { calls } = open({
      "GET /api/v1/projects/p1/participants": () => [
        200,
        { items: [PARTICIPANT, waiting], total: 2, page: 1, page_size: 25 },
      ],
      "POST /api/v1/projects/p1/participants/b1/portal-link/email": () => [
        200,
        { sent: true, expires_at: "2026-12-09T00:00:00Z" },
      ],
    });
    await openList();
    const agreed = (await screen.findByText("P000001", {}, wait)).closest("tr") as HTMLElement;
    expect(within(agreed).queryByRole("button", { name: /consent form/i })).toBeNull();
    for (const gone of ["Approve consent", "Reject consent", "Email consent form"]) {
      expect(screen.queryByRole("button", { name: gone })).toBeNull();
    }
    expect(screen.queryByText("Waiting for review")).toBeNull();
    const row = screen.getByText("P000002").closest("tr") as HTMLElement;
    expect(within(row).getByText("No answer yet")).toBeInTheDocument();
    await userEvent.click(within(row).getByRole("button", { name: "Email consent form again" }));
    expect(await screen.findByText("Consent form emailed to Bina.")).toBeInTheDocument();
    expect(calls.some((c) => c.path.endsWith("/b1/portal-link/email"))).toBe(true);
  });

  it("adds the selected people to another project, saying what happened to each", async () => {
    const { calls } = open({
      "GET /api/v1/projects": () => [
        200,
        {
          items: [PROJECT, { ...PROJECT, id: "p2", code: "TAMIL", name: "Tamil talks" }],
          total: 2,
          page: 1,
          page_size: 100,
        },
      ],
      "POST /api/v1/projects/p1/participants/bulk": () => [
        200,
        {
          results: [
            {
              participant_id: "a1",
              participant_code: "P000001",
              ok: true,
              message: "Assigned. Consent form emailed.",
            },
            {
              participant_id: "b1",
              participant_code: "P000002",
              ok: false,
              message: "Already in this project",
            },
          ],
          done: 1,
          failed: 1,
        },
      ],
    });
    await openList();
    await screen.findByText("P000001", {}, wait);
    await userEvent.click(screen.getByLabelText("Select all on this page"));
    const bar = screen.getByRole("group", { name: "Actions for selected participants" });
    expect(bar).toHaveTextContent("2 selected");
    // The consent form goes out by itself when someone joins a project (D-129).
    expect(within(bar).queryByRole("button", { name: /consent/i })).toBeNull();
    await userEvent.selectOptions(
      within(bar).getByLabelText("Also add them to another project"),
      "p2",
    );
    await userEvent.click(within(bar).getByRole("button", { name: "Add to that project" }));
    expect(await screen.findByText("1 done, 1 not done.")).toBeInTheDocument();
    expect(screen.getByRole("list", { name: "Not done" })).toHaveTextContent(
      "P000002: Already in this project",
    );
    expect(screen.getByRole("list", { name: "Added to the other project" })).toHaveTextContent(
      "P000001: Assigned. Consent form emailed.",
    );
    const sent = calls.find((c) => c.path.endsWith("/participants/bulk"))?.body as {
      action: string;
      participant_ids: string[];
      target_project_id: string;
    };
    expect(sent).toEqual({
      action: "assign",
      participant_ids: ["a1", "b1"],
      target_project_id: "p2",
    });
  });

  it("checks a pasted file before adding anyone", async () => {
    const { calls } = open({
      "POST /api/v1/projects/p1/participants/import": (body) => {
        const confirm = (body as { confirm: boolean }).confirm;
        return [
          200,
          {
            rows: [
              {
                line: 2,
                name: "Kiran",
                ok: true,
                message: confirm ? "Added. Consent form emailed." : "Ready to add",
                participant_code: confirm ? "P000010" : null,
              },
              { line: 3, name: "", ok: false, message: "Name is missing", participant_code: null },
            ],
            ready: 1,
            created: confirm ? 1 : 0,
          },
        ];
      },
    });
    await openList();
    await screen.findByText("P000001", {}, wait);
    await userEvent.click(screen.getByRole("button", { name: "Add many" }));
    await userEvent.type(screen.getByLabelText("Participants (CSV)"), "name,language");
    expect(screen.getByRole("button", { name: "Add 0 participants" })).toBeDisabled();
    await userEvent.click(screen.getByRole("button", { name: "Check rows" }));
    expect(await screen.findByText("1 of 2 rows are ready.")).toBeInTheDocument();
    expect(screen.getByText("Name is missing")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Add 1 participants" }));
    expect(await screen.findByText("1 added.")).toBeInTheDocument();
    expect(screen.getByText("Added. Consent form emailed. (P000010)")).toBeInTheDocument();
    expect(
      calls
        .filter((c) => c.path.endsWith("/import"))
        .map((c) => (c.body as { confirm: boolean }).confirm),
    ).toEqual([false, true]);
  });

  it("opens everything about one participant, not only the consent form (D-104)", async () => {
    const { calls } = open({
      "GET /api/v1/projects/p1/participants/a1/details": () => [200, DETAILS],
    });
    await openList();
    const row = (await screen.findByText("P000001", {}, wait)).closest("tr") as HTMLElement;
    await userEvent.click(within(row).getByRole("button", { name: "View" }));
    // A window next to the row, not a panel far down the page.
    const panel = await screen.findByRole("dialog", { name: "Participant details" });
    expect(await within(panel).findByRole("heading", { name: "P000001 · Asha" })).toBeVisible();
    for (const title of [
      "Profile",
      "Work in this project",
      "Personal link",
      "Consent form",
      "Sessions",
    ]) {
      expect(within(panel).getByRole("heading", { name: title })).toBeInTheDocument();
    }
    // Profile: who they are, who added them, where else they are.
    expect(panel).toHaveTextContent("Added byPriya Admin");
    expect(panel).toHaveTextContent("ProjectsHINDI · Hindi conversations, TAMIL · Tamil talks");
    expect(panel).toHaveTextContent("NotesPrefers evening calls");
    // Work: minutes and the phone calls made to them.
    expect(panel).toHaveTextContent("Sessions2");
    expect(panel).toHaveTextContent("Payable minutes3.5 min");
    expect(panel).toHaveTextContent("Phone calls to them3");
    expect(panel).toHaveTextContent("Calls with a recording1");
    // Personal link.
    expect(panel).toHaveTextContent("StateWorking");
    expect(panel).toHaveTextContent("Given byEmail only");
    // The consent form, as before.
    expect(within(panel).getByText("I agree that my voice is recorded.")).toBeInTheDocument();
    expect(panel).toHaveTextContent("AnswerAgreed");
    expect(panel).not.toHaveTextContent("Review");
    expect(panel).toHaveTextContent("Did not agree · version 1");
    expect(within(panel).getByRole("button", { name: "Download consent form" })).toBeEnabled();
    // Every session, with a way to the task.
    const sessions = within(panel).getByRole("table", { name: "Sessions of this participant" });
    const first = within(sessions).getByRole("link", { name: "T000007" }).closest("tr");
    expect(within(sessions).getByRole("link", { name: "T000007" })).toHaveAttribute(
      "href",
      "/tasks/t7",
    );
    expect(first).toHaveTextContent("Phone call");
    expect(first).toHaveTextContent("Participant A");
    expect(first).toHaveTextContent("P000002");
    expect(first).toHaveTextContent("Mohan");
    expect(first).toHaveTextContent("7.0 min");
    const second = within(sessions).getByRole("link", { name: "T000003" }).closest("tr");
    expect(second).toHaveTextContent("Face-to-face");
    expect(second).toHaveTextContent("Participant B");
    expect(second).toHaveTextContent("Nobody yet");
    // Consent is the form's answer above, not a column per session (D-129).
    expect(within(sessions).queryByRole("columnheader", { name: /consent/i })).toBeNull();
    // One request brings it all.
    expect(calls.filter((c) => c.path.includes("/participants/a1/")).map((c) => c.path)).toEqual([
      "/api/v1/projects/p1/participants/a1/details",
    ]);
    await userEvent.click(within(panel).getByRole("button", { name: "Close" }));
    expect(screen.queryByRole("dialog", { name: "Participant details" })).toBeNull();
  });

  it("says so when a participant has no link, no calls and no sessions yet", async () => {
    open({
      "GET /api/v1/projects/p1/participants/a1/details": () => [
        200,
        {
          ...DETAILS,
          link: null,
          calls: null,
          minutes: null,
          consent_form: null,
          sessions: [],
          sessions_total: 0,
        },
      ],
    });
    await openList();
    const row = (await screen.findByText("P000001", {}, wait)).closest("tr") as HTMLElement;
    await userEvent.click(within(row).getByRole("button", { name: "View" }));
    const panel = await screen.findByRole("dialog", { name: "Participant details" });
    expect(
      await within(panel).findByText("No personal link has been made for this participant."),
    ).toBeInTheDocument();
    expect(
      within(panel).getByText("This participant has not been part of a session yet."),
    ).toBeInTheDocument();
    expect(panel).toHaveTextContent("Phone calls to them0");
    expect(panel).not.toHaveTextContent("Payable minutes");
    expect(within(panel).queryByRole("heading", { name: "Consent form" })).toBeNull();
    expect(within(panel).queryByRole("button", { name: "Download consent form" })).toBeNull();
  });
});
