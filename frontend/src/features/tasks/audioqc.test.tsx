// Audio quality card on the task page (D-079): the automatic checks (those that need attention
// first), assigning a QC Executive, the player, the QC checklist (D-146) and the decision: Pass,
// Reject with a reason, or Send back for consent where the project takes signed forms. Where QC
// pass is the final approval, the card says a pass approves the task (D-138).
// Requirements: AQC-002, AQC-003, AQC-004, AQC-008, TASK-004, PART-006
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { fakeApi, renderAt, signedInAs } from "../../test/fakeApi";
import {
  ALL_PERMISSIONS,
  DOCUMENT,
  MEMBER,
  QC_CHECKLIST,
  TASK,
  worldHandlers,
} from "../../test/world";

const AUTO = {
  id: "q1",
  recording_id: "r1",
  asset_id: "a2",
  automated: true,
  outcome: "FAIL",
  reason_code: "TOO_SHORT",
  comment: "Failed: duration",
  reviewer_name: null,
  created_at: "2026-11-10T09:00:00Z",
  duration_ms: 3000,
  silence_pct: 0,
  clip_pct: 0,
  peak_dbfs: -6,
  rms_dbfs: -9,
  dynamic_range_db: 4,
  duplicate_of_recording_id: null,
  checks: [
    {
      code: "DURATION",
      state: "FAIL",
      measured: "3.0 s",
      expected: "10 s or more",
      message: "Shorter than the project allows",
    },
    { code: "SILENCE", state: "PASS", measured: "0.0 %", expected: "25 % or less", message: "" },
    {
      code: "SNR",
      state: "NOT_APPLICABLE",
      measured: "Not measured",
      expected: "",
      message: "No validated method",
    },
    {
      code: "PAUSES",
      state: "INFO",
      measured: "2 over 3 s, longest 4.0 s",
      expected: "Shown, not judged",
      message: "Effective speech 6 s of 14 s",
    },
  ],
};

function view(over: Record<string, unknown> = {}) {
  return {
    task_status: "AUDIO_QC",
    pass_approves: false,
    qc_user_id: null,
    qc_name: null,
    can_decide: false,
    can_assign: false,
    can_recheck: false,
    reasons: { FAIL: ["AUDIO_QUALITY", "OTHER"] },
    results: [AUTO],
    ...over,
  };
}

function open(qcView: Record<string, unknown>, extra = {}) {
  return fakeApi(
    signedInAs(ALL_PERMISSIONS, {
      ...worldHandlers(),
      "GET /api/v1/tasks/t1": () => [200, { ...TASK, status: "AUDIO_QC", can_reassign: false }],
      "GET /api/v1/tasks/t1/recordings": () => [200, []],
      "GET /api/v1/tasks/t1/audio-qc": () => [200, qcView],
      "GET /api/v1/projects/p1/members": () => [
        200,
        [
          MEMBER,
          {
            ...MEMBER,
            user_id: "q9",
            email: "quinn@example.org",
            display_name: "Quinn QC",
            roles: ["QC_EXECUTIVE"],
          },
        ],
      ],
      ...extra,
    }),
  );
}

/** Every answer that lets the recording pass: the conversation's question, each speaker's. */
const ALL_PASSING = {
  conversation: { two_speakers: "yes" },
  speakers: { A: { echo_in_audio: "no" }, B: { echo_in_audio: "no" } },
  consent: {},
};
const NONE = { conversation: {}, speakers: {}, consent: {} };

// D-152: each answer is a Yes / No radio group, named by its question (and, for the speaker
// questions, "– Participant A" or "– Participant B": one matrix row per question).
const question = (name: string) => screen.getByRole("radiogroup", { name });
const press = (group: HTMLElement, answer: "Yes" | "No") =>
  userEvent.click(within(group).getByRole("radio", { name: answer }));
const ECHO = /^Is echo present\? – Participant [AB]$/;

/** Ticks every question so that the recording passes (D-146). */
async function answerAll() {
  await press(
    await screen.findByRole(
      "radiogroup",
      { name: "The conversation is between exactly two speakers" },
      { timeout: 5000 },
    ),
    "Yes",
  );
  for (const group of screen.getAllByRole("radiogroup", { name: ECHO })) await press(group, "No");
}

describe("audio quality card", () => {
  it("shows the checks that need attention first, and every check on request", async () => {
    open(view());
    renderAt("/tasks/t1");
    const card = await screen.findByRole("region", { name: "Audio quality" }, { timeout: 5000 });
    expect(within(card).getAllByText("Failed").length).toBeGreaterThan(0);
    expect(within(card).getByText("1 check needs attention:")).toBeInTheDocument();
    const table = within(card).getByRole("table", { name: "Checks that need attention" });
    expect(within(table).getByText("Length")).toBeInTheDocument();
    expect(within(table).getByText("3.0 s")).toBeInTheDocument();
    expect(within(table).getByText("10 s or more")).toBeInTheDocument();
    expect(within(table).queryByText("Signal to noise")).toBeNull();
    await userEvent.click(within(card).getByRole("button", { name: "Show all checks (4)" }));
    const all = within(card).getByRole("table", { name: "All automatic checks" });
    expect(within(all).getByText("Signal to noise")).toBeInTheDocument();
    // D-148: the long pauses, with the effective speech under the check's name.
    const pauses = within(all).getByText("Long pauses").closest("tr");
    expect(pauses).toHaveTextContent("2 over 3 s, longest 4.0 s");
    expect(pauses).toHaveTextContent("Effective speech 6 s of 14 s");
    expect(pauses).toHaveTextContent("Shown");
    expect(within(card).queryByRole("button", { name: "Pass" })).toBeNull();
  });

  it("keeps its title bar to the title and the result, listening under it (D-159)", async () => {
    open(view({ can_decide: true, can_recheck: true }));
    renderAt("/tasks/t1");
    const card = await screen.findByRole("region", { name: "Audio quality" }, { timeout: 5000 });
    const bar = within(card).getByRole("heading", { name: "Audio quality" }).closest(".card__head");
    // One row on a phone too: no button on the bar.
    expect(bar).toHaveTextContent(/^Audio quality/);
    expect(within(bar as HTMLElement).queryByRole("button")).toBeNull();
    // Listen and Check the stored file again: the section's first row, even on a phone.
    const row = within(card).getByRole("button", { name: "Listen" }).closest(".actions");
    expect(row).toHaveClass("page-actions");
    expect(bar?.nextElementSibling).toBe(row);
    expect(
      within(row as HTMLElement).getByRole("button", { name: "Check the stored file again" }),
    ).toBeInTheDocument();
  });

  it("lets a manager assign a QC Executive, never the session's moderator", async () => {
    const { calls } = open(view({ can_assign: true }), {
      "POST /api/v1/tasks/t1/assign-qc": () => [
        200,
        view({ can_assign: true, qc_user_id: "q9", qc_name: "Quinn QC" }),
      ],
    });
    renderAt("/tasks/t1");
    const select = await screen.findByLabelText("QC Executive", {}, { timeout: 5000 });
    await within(select).findByRole("option", { name: /Quinn QC/ });
    expect(within(select).queryByText(/Mona Moderator/)).toBeNull();
    await userEvent.selectOptions(select, "q9");
    await userEvent.click(screen.getByRole("button", { name: "Assign QC" }));
    expect(await screen.findByText("Quinn QC")).toBeInTheDocument();
    expect(calls.find((c) => c.path === "/api/v1/tasks/t1/assign-qc")?.body).toEqual({
      user_id: "q9",
      reason: null,
    });
  });

  it("asks for a comment before passing a recording the automatic check failed", async () => {
    const { calls } = open(view({ can_decide: true, can_recheck: true, qc_name: "Quinn QC" }), {
      "POST /api/v1/tasks/t1/audio-qc/decision": () => [200, view({ task_status: "APPROVED" })],
    });
    renderAt("/tasks/t1");
    await answerAll();
    await userEvent.click(await screen.findByRole("button", { name: "Pass" }, { timeout: 5000 }));
    const window = screen.getByRole("dialog", {
      name: "Pass a recording that failed the automatic check?",
    });
    const save = within(window).getByRole("button", { name: "Pass" });
    expect(save).toBeDisabled();
    await userEvent.type(
      within(window).getByLabelText(/Why does it pass/),
      "Client accepts short greetings",
    );
    await userEvent.click(save);
    await waitFor(() => {
      expect(calls.find((c) => c.path === "/api/v1/tasks/t1/audio-qc/decision")?.body).toEqual({
        outcome: "PASS",
        reason_code: null,
        comment: "Client accepts short greetings",
        answers: ALL_PASSING,
      });
    });
  });

  it("passes a recording the automatic check passed at once", async () => {
    const { calls } = open(
      view({ can_decide: true, results: [{ ...AUTO, outcome: "PASS", checks: [] }] }),
      { "POST /api/v1/tasks/t1/audio-qc/decision": () => [200, view()] },
    );
    renderAt("/tasks/t1");
    await answerAll();
    await userEvent.click(await screen.findByRole("button", { name: "Pass" }, { timeout: 5000 }));
    expect(screen.queryByRole("dialog")).toBeNull();
    await waitFor(() =>
      expect(calls.find((c) => c.path.endsWith("/audio-qc/decision"))?.body).toEqual({
        outcome: "PASS",
        reason_code: null,
        comment: "",
        answers: ALL_PASSING,
      }),
    );
  });

  it("says where a pass goes: to the admin, or straight to approved (D-138)", async () => {
    open(view({ can_decide: true }));
    renderAt("/tasks/t1");
    expect(
      await screen.findByText(
        /Pass sends it to the project admin for final approval\./,
        {},
        {
          timeout: 5000,
        },
      ),
    ).toBeInTheDocument();
  });

  it("says a pass approves the task where the project has no admin review (D-138)", async () => {
    open(view({ can_decide: true, pass_approves: true }));
    renderAt("/tasks/t1");
    expect(
      await screen.findByText(
        /Pass approves the task: this project has no admin review\./,
        {},
        {
          timeout: 5000,
        },
      ),
    ).toBeInTheDocument();
  });

  it("needs a reason to reject a recording, and offers no return (D-118)", async () => {
    const { calls } = open(view({ can_decide: true }), {
      "POST /api/v1/tasks/t1/audio-qc/decision": () => [200, view()],
    });
    renderAt("/tasks/t1");
    await userEvent.click(await screen.findByRole("button", { name: "Reject" }, { timeout: 5000 }));
    expect(screen.queryByRole("button", { name: /Return/ })).not.toBeInTheDocument();
    const window = screen.getByRole("dialog");
    expect(within(window).getByRole("button", { name: "Reject" })).toBeDisabled();
    await userEvent.selectOptions(within(window).getByLabelText(/^Reason/), "AUDIO_QUALITY");
    expect(within(window).getByRole("button", { name: "Reject" })).toBeEnabled();
    await userEvent.click(within(window).getByRole("button", { name: "Reject" }));
    await waitFor(() =>
      expect(calls.find((c) => c.path.endsWith("/audio-qc/decision"))?.body).toEqual({
        outcome: "FAIL",
        reason_code: "AUDIO_QUALITY",
        comment: "",
        answers: NONE,
      }),
    );
  });

  it("plays the recording being checked from a short-lived link", async () => {
    const { calls } = open(view({ can_decide: true }), {
      "POST /api/v1/assets/a2/url": () => [
        200,
        { url: "https://storage.example/a2.wav", expires_in: 300 },
      ],
    });
    renderAt("/tasks/t1");
    await userEvent.click(await screen.findByRole("button", { name: "Listen" }, { timeout: 5000 }));
    expect(await screen.findByLabelText("Recording")).toHaveAttribute(
      "src",
      "https://storage.example/a2.wav",
    );
    expect(calls.find((c) => c.path === "/api/v1/assets/a2/url")?.body).toEqual({
      purpose: "play",
    });
  });
});

describe("the QC checklist (D-146)", () => {
  it("keeps the answers as a draft while ticking, and starts from the saved draft", async () => {
    const { calls } = open(view({ can_decide: true }), {
      "GET /api/v1/tasks/t1/audio-qc/checklist": () => [
        200,
        {
          ...QC_CHECKLIST,
          draft: {
            answers: { conversation: { two_speakers: "yes" }, speakers: {}, consent: {} },
            saved_at: "2026-11-21T10:00:00Z",
            saved_by_name: "Quinn QC",
          },
        },
      ],
    });
    renderAt("/tasks/t1");
    const two = await screen.findByRole(
      "radiogroup",
      { name: "The conversation is between exactly two speakers" },
      { timeout: 5000 },
    );
    expect(within(two).getByRole("radio", { name: "Yes" })).toBeChecked();
    // Speaker questions: one row each, a column per person by code and name.
    const speakers = screen.getByRole("table", { name: "Questions about each speaker" });
    for (const name of ["Participant A P000001 Asha", "Participant B P000002 Bina"])
      expect(within(speakers).getByRole("columnheader", { name })).toBeInTheDocument();
    expect(within(speakers).getAllByRole("row")).toHaveLength(2); // the heading and one question
    expect(screen.getByText("Answered 1 / 3")).toBeInTheDocument();
    await press(question("Is echo present? – Participant A"), "Yes");
    await waitFor(() => expect(calls.filter((c) => c.method === "PUT")).toHaveLength(1));
    expect(calls.find((c) => c.method === "PUT")?.path).toBe("/api/v1/tasks/t1/audio-qc/draft");
    expect(calls.find((c) => c.method === "PUT")?.body).toEqual({
      conversation: { two_speakers: "yes" },
      speakers: { A: { echo_in_audio: "yes" } },
      consent: {},
    });
    expect(await screen.findByText("Answers saved.")).toBeInTheDocument();
  });

  it("waits for every answer and none failing before Pass, and says why", async () => {
    open(view({ can_decide: true }));
    renderAt("/tasks/t1");
    const pass = await screen.findByRole("button", { name: "Pass" }, { timeout: 5000 });
    expect(pass).toBeDisabled();
    // Why Pass waits is said beside it, and read with it.
    expect(screen.getByText("3 questions still to answer.")).toBeInTheDocument();
    expect(pass).toHaveAccessibleDescription("3 questions still to answer.");
    expect(screen.getByText("Answered 0 / 3")).toBeInTheDocument();
    expect(screen.getByRole("progressbar", { name: "Questions answered" })).toHaveAttribute(
      "aria-valuenow",
      "0",
    );
    const two = question("The conversation is between exactly two speakers");
    await press(two, "No");
    expect(screen.getByText("Fails")).toBeInTheDocument();
    expect(two.closest("td")).toHaveClass("is-fail");
    expect(screen.getByText("· 1 failing", { exact: false })).toBeInTheDocument();
    expect(
      screen.getByText(
        "The recording fails the checklist (The conversation is between exactly two speakers): reject it.",
      ),
    ).toBeInTheDocument();
    // Observations never fail: "Yes, there is echo" is recorded, nothing more.
    for (const group of screen.getAllByRole("radiogroup", { name: ECHO }))
      await press(group, "Yes");
    expect(pass).toBeDisabled();
    await press(two, "Yes");
    expect(screen.queryByText("Fails")).toBeNull();
    expect(pass).toBeEnabled();
    expect(pass).not.toHaveAccessibleDescription();
    expect(screen.getByText("Answered 3 / 3")).toBeInTheDocument();
    expect(screen.getByText("Every answer lets the recording pass.")).toBeInTheDocument();
    // An Online project: the platform recorded each answer; nothing to tick, no send-back.
    const consent = screen.getByRole("region", { name: "Consent" });
    expect(within(consent).getByText(/nothing to check here/)).toBeInTheDocument();
    expect(within(consent).getAllByText("Agreed")).toHaveLength(2);
    expect(within(consent).queryByRole("radio")).toBeNull();
    expect(screen.queryByRole("button", { name: "Send back for consent" })).toBeNull();
    expect(screen.getByRole("button", { name: "Reject" })).toBeEnabled();
  });

  it("answers from the keyboard: Space picks, arrows move between Yes and No (D-152)", async () => {
    open(view({ can_decide: true }));
    renderAt("/tasks/t1");
    const echoA = await screen.findByRole(
      "radiogroup",
      { name: "Is echo present? – Participant A" },
      { timeout: 5000 },
    );
    const yes = within(echoA).getByRole("radio", { name: "Yes" });
    const no = within(echoA).getByRole("radio", { name: "No" });
    yes.focus();
    await userEvent.keyboard(" ");
    expect(yes).toBeChecked();
    await userEvent.keyboard("{ArrowRight}");
    expect(no).toBeChecked();
    expect(yes).not.toBeChecked();
    // Each person's answer is its own group.
    const echoB = question("Is echo present? – Participant B");
    expect(within(echoB).getByRole("radio", { name: "No" })).not.toBeChecked();
    expect(screen.getByText("Answered 1 / 3")).toBeInTheDocument();
  });

  it("gives the checklist and the decision a section of their own, the decision first (D-158)", async () => {
    open(view({ can_decide: true }));
    renderAt("/tasks/t1");
    const card = await screen.findByRole("region", { name: "QC checklist" }, { timeout: 5000 });
    const decision = await within(card).findByRole("region", { name: "Your decision" });
    expect(within(decision).getByRole("button", { name: "Pass" })).toBeDisabled();
    // Under the title bar, before the questions: it stays in view while they scroll.
    const speakers = within(card).getByRole("table", { name: "Questions about each speaker" });
    expect(
      decision.compareDocumentPosition(speakers) & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
    // Each part under its own heading; the audio check holds no question and no decision.
    for (const name of ["The conversation", "Each speaker", "Consent"])
      expect(within(card).getByRole("heading", { name })).toBeInTheDocument();
    const audio = screen.getByRole("region", { name: "Audio quality" });
    expect(within(audio).queryByRole("radio")).toBeNull();
    expect(within(audio).queryByRole("button", { name: "Pass" })).toBeNull();
  });

  it("checks both signed forms where the project takes them, and sends a wrong one back", async () => {
    const uploads = {
      ...TASK,
      status: "AUDIO_QC",
      can_reassign: false,
      consent_mode: "UPLOAD",
      participant_a: { ...TASK.participant_a, consent_status: "UPLOADED", consent_form: DOCUMENT },
      participant_b: { ...TASK.participant_b, consent_status: "UPLOADED", consent_form: null },
    };
    const { calls } = open(
      view({ can_decide: true, results: [{ ...AUTO, outcome: "PASS", checks: [] }] }),
      {
        "GET /api/v1/tasks/t1": () => [200, uploads],
        "GET /api/v1/tasks/t1/audio-qc/checklist": () => [
          200,
          { ...QC_CHECKLIST, consent_check: true },
        ],
        "POST /api/v1/tasks/t1/audio-qc/decision": () => [200, view()],
      },
    );
    renderAt("/tasks/t1");
    // The open questions and the forms still to check add up with "Answered 0 / 5" (UXW-02).
    expect(
      await screen.findByText(
        "3 questions and 2 consent forms still to answer.",
        {},
        { timeout: 5000 },
      ),
    ).toBeInTheDocument();
    expect(screen.getByText("Answered 0 / 5")).toBeInTheDocument();
    await answerAll();
    const forms = screen.getByRole("region", { name: "Signed consent forms" });
    expect(
      within(forms).getByRole("button", { name: "View the signed consent form of P000001" }),
    ).toBeInTheDocument();
    expect(within(forms).getByText("No form uploaded")).toBeInTheDocument();
    const pass = screen.getByRole("button", { name: "Pass" });
    const sendBack = screen.getByRole("button", { name: "Send back for consent" });
    expect(pass).toBeDisabled();
    expect(sendBack).toBeDisabled();
    expect(
      screen.getByText("Check the signed consent form of P000001 and P000002."),
    ).toBeInTheDocument();
    await press(question("Consent form of P000001 checked"), "Yes");
    await press(question("Consent form of P000002 checked"), "No");
    expect(pass).toBeDisabled();
    expect(sendBack).toBeEnabled();
    expect(
      screen.getByText(
        "The consent form of P000002 is not right: send the task back for its consent form.",
      ),
    ).toBeInTheDocument();
    await userEvent.click(sendBack);
    const dialog = screen.getByRole("dialog", {
      name: "Send task T000001 back for its consent form?",
    });
    const confirm = within(dialog).getByRole("button", { name: "Send back" });
    expect(confirm).toBeDisabled();
    await userEvent.type(within(dialog).getByLabelText(/What is wrong with the form/), "Unsigned");
    await userEvent.click(confirm);
    await waitFor(() =>
      expect(calls.find((c) => c.path.endsWith("/audio-qc/decision"))?.body).toEqual({
        outcome: "SEND_BACK_CONSENT",
        reason_code: null,
        comment: "Unsigned",
        answers: { ...ALL_PASSING, consent: { A: "yes", B: "no" } },
      }),
    );
  });

  it("shows everyone the newest decision's answers, read only, with who and when", async () => {
    const decision = {
      ...AUTO,
      id: "q2",
      automated: false,
      outcome: "FAIL",
      reason_code: "WRONG_SPEAKERS",
      comment: "",
      reviewer_name: "Quinn QC",
      created_at: "2026-11-20T09:00:00Z",
      checks: [],
    };
    const latest = {
      outcome: "FAIL",
      reason_code: "WRONG_SPEAKERS",
      comment: "",
      reviewer_name: "Quinn QC",
      decided_at: "2026-11-20T09:00:00Z",
      items: QC_CHECKLIST.items,
      consent_check: false,
      conversation: { two_speakers: "no" },
      participants: [
        {
          side: "A",
          participant_id: "a1",
          participant_code: "P000001",
          answers: { echo_in_audio: "yes" },
          consent: null,
          consent_form_id: null,
        },
        {
          side: "B",
          participant_id: "b1",
          participant_code: "P000002",
          answers: {},
          consent: null,
          consent_form_id: null,
        },
      ],
      failing: [{ key: "two_speakers", side: null, answer: "no" }],
    };
    open(view({ results: [decision, AUTO] }), {
      "GET /api/v1/tasks/t1/audio-qc/checklist": () => [
        200,
        { ...QC_CHECKLIST, can_answer: false, latest },
      ],
    });
    renderAt("/tasks/t1");
    // D-158: the checklist is a section of its own after the audio check, the decisions in it.
    const card = await screen.findByRole("region", { name: "QC checklist" }, { timeout: 5000 });
    expect(
      await within(card).findByText(/Failed · answered by Quinn QC · 20 Nov 2026/),
    ).toBeInTheDocument();
    const audio = screen.getByRole("region", { name: "Audio quality" });
    expect(within(audio).queryByRole("heading", { name: "QC checklist" })).toBeNull();
    expect(within(audio).queryByRole("heading", { name: "Decisions" })).toBeNull();
    expect(within(card).getByRole("heading", { name: "Decisions" })).toBeInTheDocument();
    expect(within(card).getByText("1 answer fails the recording.")).toBeInTheDocument();
    expect(within(card).queryByRole("radio")).toBeNull();
    await userEvent.click(within(card).getByRole("button", { name: "Show every answer" }));
    const talk = within(card).getByRole("table", { name: "Answers about the conversation" });
    expect(talk).toHaveTextContent(/exactly two speakers\s*No\s*Fails/);
    const speakers = within(card).getByRole("table", { name: "Answers about each speaker" });
    expect(
      within(speakers).getByRole("columnheader", { name: "Participant B P000002" }),
    ).toBeInTheDocument();
    expect(within(talk).getByText("No").closest("td")).toHaveClass("is-fail");
    expect(speakers).toHaveTextContent(/Is echo present\?\s*Yes\s*Not answered/);
    // An observation is the word alone: "Yes, there is echo" gets no green tick (UXW-02).
    const echo = within(speakers).getByText("Yes").closest("td") as HTMLElement;
    expect(echo.querySelector(".mark--ok")).toBeNull();
    expect(echo.querySelector("svg")).toBeNull();
    // A question that can fail keeps its cross.
    expect(within(talk).getByText("No").closest("td")?.querySelector("svg")).not.toBeNull();
    // D-159: both tables straight in their grid, so the last one leaves its bottom line to the
    // Decisions heading right after the grid (the shared rule for a table before a sub-heading).
    const grid = speakers.closest(".table-wrap")?.parentElement as HTMLElement;
    expect(grid).toHaveClass("qc-matrix__grid");
    expect(talk.closest(".table-wrap")?.parentElement).toBe(grid);
    expect(grid.parentElement?.nextElementSibling).toHaveTextContent(/^Decisions$/);
  });
});

describe("after Send to QC (FEW-06)", () => {
  it("names the QC Executive the platform assigned, without opening the page again", async () => {
    let status = "RECORDED";
    const recorded = {
      ...TASK,
      status: "RECORDED",
      allowed_transitions: ["AUDIO_QC", "IN_PROGRESS"],
      can_assign: false,
      can_reassign: false,
      can_delete: false,
    };
    const recording = {
      id: "r1",
      task_id: "t1",
      state: "READY",
      current: true,
      saved_seconds: 120,
      assets: [{ id: "a2", kind: "FTF_DERIVED_PCM" }],
    };
    const { calls } = fakeApi(
      signedInAs(ALL_PERMISSIONS, {
        ...worldHandlers(),
        "GET /api/v1/tasks/t1": () => [200, recorded],
        "GET /api/v1/tasks/t1/recordings": () => [200, [recording]],
        // The server assigns a QC Executive in the same step as Send to QC (D-116).
        "GET /api/v1/tasks/t1/audio-qc": () => [
          200,
          status === "RECORDED"
            ? view({ task_status: "RECORDED", results: [{ ...AUTO, outcome: "PASS" }] })
            : view({
                qc_user_id: "q9",
                qc_name: "Quinn QC",
                results: [{ ...AUTO, outcome: "PASS" }],
              }),
        ],
        "POST /api/v1/tasks/t1/transition": () => {
          status = "AUDIO_QC";
          return [200, { ...recorded, status: "AUDIO_QC", allowed_transitions: [] }];
        },
      }),
    );
    renderAt("/tasks/t1");
    const summary = await screen.findByRole("region", { name: "Summary" });
    await waitFor(() => expect(summary).toHaveTextContent("QC ExecutiveNot assigned"), {
      timeout: 5000,
    });
    await userEvent.click(screen.getByRole("button", { name: "Send to QC" }));
    await waitFor(() => expect(summary).toHaveTextContent("QC ExecutiveQuinn QC"));
    expect(screen.getByRole("region", { name: "Next step" })).toHaveTextContent(
      "Waiting for QC: Quinn QC checks the recording.",
    );
    expect(calls.filter((c) => c.path === "/api/v1/tasks/t1/audio-qc")).toHaveLength(2);
  });
});
