// Audio quality card on the task page (D-079): the automatic checks (those that need attention
// first), assigning a QC Executive, the player, and the decision: Pass, or Reject with a reason.
// Requirements: AQC-002, AQC-003, AQC-004, AQC-008, TASK-004
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { fakeApi, renderAt, signedInAs } from "../../test/fakeApi";
import { ALL_PERMISSIONS, MEMBER, TASK, worldHandlers } from "../../test/world";

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
  ],
};

function view(over: Record<string, unknown> = {}) {
  return {
    task_status: "AUDIO_QC",
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
    await userEvent.click(within(card).getByRole("button", { name: "Show all checks (3)" }));
    const all = within(card).getByRole("table", { name: "All automatic checks" });
    expect(within(all).getByText("Signal to noise")).toBeInTheDocument();
    expect(within(card).queryByRole("button", { name: "Pass" })).toBeNull();
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
      });
    });
  });

  it("passes a recording the automatic check passed at once", async () => {
    const { calls } = open(
      view({ can_decide: true, results: [{ ...AUTO, outcome: "PASS", checks: [] }] }),
      { "POST /api/v1/tasks/t1/audio-qc/decision": () => [200, view()] },
    );
    renderAt("/tasks/t1");
    await userEvent.click(await screen.findByRole("button", { name: "Pass" }, { timeout: 5000 }));
    expect(screen.queryByRole("dialog")).toBeNull();
    await waitFor(() =>
      expect(calls.find((c) => c.path.endsWith("/audio-qc/decision"))?.body).toEqual({
        outcome: "PASS",
        reason_code: null,
        comment: "",
      }),
    );
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
