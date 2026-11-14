// Participants section (D-073). Requirements: PART-016, PART-017
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { fakeApi, renderAt, signedInAs } from "../../test/fakeApi";
import { ALL_PERMISSIONS, PARTICIPANT, worldHandlers } from "../../test/world";

afterEach(() => vi.unstubAllGlobals());

const wait = { timeout: 5000 };

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
      review_status: "REJECTED",
      review_note: "Wrong person",
      reviewed_at: "2026-11-10T09:00:00Z",
    },
    earlier: [
      {
        status: "REFUSED",
        answered_at: "2026-11-09T08:00:00Z",
        policy_version: "1",
        review_status: null,
        review_note: "",
        reviewed_at: null,
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
      consent_status: "GIVEN",
      consent_method: "VERBAL_NOTED",
      consent_at: "2026-11-11T05:10:00Z",
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
      consent_status: null,
      consent_method: null,
      consent_at: null,
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
  it("is in the menu and lists the project's participants with their consent state", async () => {
    open();
    renderAt("/participants");
    expect(await screen.findByText("P000001", {}, wait)).toBeInTheDocument();
    expect(screen.getByRole("navigation", { name: "Main" })).toHaveTextContent("Participants");
    const row = screen.getByText("P000001").closest("tr") as HTMLElement;
    expect(within(row).getByText("Agreed")).toBeInTheDocument();
    expect(within(row).getByText("Waiting for review")).toBeInTheDocument();
    expect(within(row).getByRole("button", { name: "Resend" })).toBeInTheDocument();
  });

  it("approves, and rejects only with a reason the participant will see", async () => {
    vi.stubGlobal("prompt", () => "Signature of the wrong person");
    const { calls } = open({
      "POST /api/v1/projects/p1/participants/a1/consent-review": () => [200, {}],
    });
    renderAt("/participants");
    const row = (await screen.findByText("P000001", {}, wait)).closest("tr") as HTMLElement;
    await userEvent.click(within(row).getByRole("button", { name: "Approve" }));
    expect(await screen.findByText("Consent of P000001 approved.")).toBeInTheDocument();
    await userEvent.click(
      within(screen.getByText("P000001").closest("tr") as HTMLElement).getByRole("button", {
        name: "Reject",
      }),
    );
    await waitFor(() =>
      expect(calls.filter((c) => c.path.endsWith("/consent-review")).map((c) => c.body)).toEqual([
        { decision: "APPROVED", note: "" },
        { decision: "REJECTED", note: "Signature of the wrong person" },
      ]),
    );
  });

  it("sends consent forms to the selected participants and names the ones that failed", async () => {
    const { calls } = open({
      "POST /api/v1/projects/p1/participants/bulk": () => [
        200,
        {
          results: [
            {
              participant_id: "a1",
              participant_code: "P000001",
              ok: true,
              message: "Consent form sent",
            },
            {
              participant_id: "b1",
              participant_code: "P000002",
              ok: false,
              message: "This participant has no email address",
            },
          ],
          done: 1,
          failed: 1,
        },
      ],
    });
    renderAt("/participants");
    await screen.findByText("P000001", {}, wait);
    await userEvent.click(screen.getByLabelText("Select all on this page"));
    const bar = screen.getByRole("group", { name: "Actions for selected participants" });
    expect(bar).toHaveTextContent("2 selected");
    await userEvent.click(within(bar).getByRole("button", { name: "Send consent form" }));
    expect(await screen.findByText("1 done, 1 not done.")).toBeInTheDocument();
    expect(screen.getByRole("list", { name: "Not done" })).toHaveTextContent(
      "P000002: This participant has no email address",
    );
    const sent = calls.find((c) => c.path.endsWith("/participants/bulk"))?.body as {
      action: string;
      participant_ids: string[];
    };
    expect(sent.action).toBe("send_consent");
    expect(sent.participant_ids).toHaveLength(2);
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
                message: confirm ? "Added" : "Ready to add",
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
    renderAt("/participants");
    await screen.findByText("P000001", {}, wait);
    await userEvent.click(screen.getByRole("button", { name: "Add many" }));
    await userEvent.type(screen.getByLabelText("Participants (CSV)"), "name,language");
    expect(screen.getByRole("button", { name: "Add 0 participants" })).toBeDisabled();
    await userEvent.click(screen.getByRole("button", { name: "Check rows" }));
    expect(await screen.findByText("1 of 2 rows are ready.")).toBeInTheDocument();
    expect(screen.getByText("Name is missing")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Add 1 participants" }));
    expect(await screen.findByText("1 added.")).toBeInTheDocument();
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
    renderAt("/participants");
    const row = (await screen.findByText("P000001", {}, wait)).closest("tr") as HTMLElement;
    await userEvent.click(within(row).getByRole("button", { name: "View" }));
    const panel = await screen.findByRole("region", { name: "Participant details" });
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
    expect(panel).toHaveTextContent("Sent back: Wrong person");
    expect(panel).toHaveTextContent("Did not agree · version 1");
    expect(within(panel).getByRole("button", { name: "Download consent form" })).toBeEnabled();
    // Every session, with a way to the task.
    const sessions = within(panel).getByRole("table", { name: "Sessions of this participant" });
    const first = within(sessions).getByRole("link", { name: "T000007" }).closest("tr");
    expect(within(sessions).getByRole("link", { name: "T000007" })).toHaveAttribute(
      "href",
      "/tasks/t7",
    );
    expect(first).toHaveTextContent("Telephony");
    expect(first).toHaveTextContent("Participant A");
    expect(first).toHaveTextContent("P000002");
    expect(first).toHaveTextContent("Mohan");
    expect(first).toHaveTextContent("Agreed");
    expect(first).toHaveTextContent("verbal noted");
    expect(first).toHaveTextContent("7.0 min");
    const second = within(sessions).getByRole("link", { name: "T000003" }).closest("tr");
    expect(second).toHaveTextContent("Face-to-face");
    expect(second).toHaveTextContent("Participant B");
    expect(second).toHaveTextContent("Nobody yet");
    expect(second).toHaveTextContent("Not noted");
    // One request brings it all.
    expect(calls.filter((c) => c.path.includes("/participants/a1/")).map((c) => c.path)).toEqual([
      "/api/v1/projects/p1/participants/a1/details",
    ]);
    await userEvent.click(within(panel).getByRole("button", { name: "Close" }));
    expect(screen.queryByRole("region", { name: "Participant details" })).toBeNull();
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
    renderAt("/participants");
    const row = (await screen.findByText("P000001", {}, wait)).closest("tr") as HTMLElement;
    await userEvent.click(within(row).getByRole("button", { name: "View" }));
    const panel = await screen.findByRole("region", { name: "Participant details" });
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
