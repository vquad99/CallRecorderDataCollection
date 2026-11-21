// A consent form QC sent back (D-146): the moderator sees whose form and what QC found, uploads a
// new scan and sends the same recording back to QC; the stepper shows the task waiting at Audio
// QC; QC reads the same card without the button.
// Requirements: PART-006, PART-016, TASK-003, TASK-004, AQC-008
import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { fakeApi, renderAt, signedInAs } from "../../test/fakeApi";
import { ALL_PERMISSIONS, DOCUMENT, TASK, worldHandlers } from "../../test/world";

afterEach(() => vi.unstubAllGlobals());

const FIX = {
  comment: "Not signed on page 2",
  by: "Quinn QC",
  at: "2026-11-21T09:00:00Z",
  participants: [{ side: "A", participant_id: "a1", participant_code: "P000001", replaced: false }],
  forms_replaced: false,
  can_send_back: true,
};

const QC_VIEW = {
  task_status: "CONSENT_FIX",
  pass_approves: false,
  qc_user_id: "q9",
  qc_name: "Quinn QC",
  can_decide: false,
  can_assign: false,
  can_recheck: false,
  reasons: { FAIL: ["AUDIO_QUALITY"] },
  results: [],
};

function waiting(fix: Record<string, unknown> = FIX) {
  return {
    ...TASK,
    status: "CONSENT_FIX",
    consent_mode: "UPLOAD",
    allowed_transitions: ["AUDIO_QC"],
    can_reassign: false,
    participant_a: {
      ...TASK.participant_a,
      consent_status: "UPLOADED",
      consent_form: DOCUMENT,
      can_upload_consent_form: true,
    },
    participant_b: { ...TASK.participant_b, consent_status: "UPLOADED" },
    consent_fix: fix,
  };
}

describe("a consent form to fix (D-146)", () => {
  it("lets the moderator upload a new scan and send the same recording back to QC", async () => {
    let replaced = false;
    const { calls } = fakeApi(
      signedInAs(ALL_PERMISSIONS, {
        ...worldHandlers(),
        "GET /api/v1/tasks/t1": () => [
          200,
          replaced
            ? waiting({
                ...FIX,
                forms_replaced: true,
                participants: [{ ...FIX.participants[0], replaced: true }],
              })
            : waiting(),
        ],
        "GET /api/v1/tasks/t1/audio-qc": () => [200, QC_VIEW],
        "POST /api/v1/projects/p1/participants/a1/documents/consent-form": () => {
          replaced = true;
          return [201, { ...DOCUMENT, id: "d9", file_name: "signed-again.pdf" }];
        },
        "POST /api/v1/tasks/t1/consent-fix/send-to-qc": () => [
          200,
          { ...waiting(), status: "AUDIO_QC", consent_fix: null, allowed_transitions: [] },
        ],
      }),
    );
    renderAt("/tasks/t1");
    const card = await screen.findByRole(
      "region",
      { name: "Consent form to fix" },
      { timeout: 5000 },
    );
    expect(within(card).getByText("Not signed on page 2")).toBeInTheDocument();
    expect(within(card).getByText(/Quinn QC/)).toBeInTheDocument();
    expect(within(card).getByText("New form needed")).toBeInTheDocument();
    const send = within(card).getByRole("button", { name: "Send back to QC" });
    expect(send).toBeDisabled();
    expect(send).toHaveAccessibleDescription("Upload the new form first.");
    // The stepper waits at Audio QC; the status says what is going on.
    expect(
      screen.getByRole("img", { name: "Workflow progress: Consent form to fix" }),
    ).toBeInTheDocument();

    await userEvent.upload(
      within(card).getByLabelText("Upload a new consent form of P000001"),
      new File(["%PDF-1.7 signed"], "signed-again.pdf", { type: "application/pdf" }),
    );
    expect(await within(card).findByText("New form uploaded")).toBeInTheDocument();
    await userEvent.click(within(card).getByRole("button", { name: "Send back to QC" }));
    expect(await screen.findByText("Sent back to QC with the same recording.")).toBeInTheDocument();
    expect(calls.find((c) => c.path === "/api/v1/tasks/t1/consent-fix/send-to-qc")?.body).toEqual({
      comment: "",
    });
    expect(screen.queryByRole("region", { name: "Consent form to fix" })).toBeNull();
  });

  it("shows QC whose form and what is wrong, without the button", async () => {
    fakeApi(
      signedInAs(["tasks.view", "recordings.view"], {
        ...worldHandlers(),
        "GET /api/v1/tasks/t1": () => [
          200,
          {
            ...waiting({ ...FIX, can_send_back: false }),
            allowed_transitions: [],
            is_moderator: false,
            can_assign: false,
            participant_a: { ...waiting().participant_a, can_upload_consent_form: false },
          },
        ],
        "GET /api/v1/tasks/t1/audio-qc": () => [200, QC_VIEW],
      }),
    );
    renderAt("/tasks/t1");
    const card = await screen.findByRole(
      "region",
      { name: "Consent form to fix" },
      { timeout: 5000 },
    );
    expect(within(card).getByText("Not signed on page 2")).toBeInTheDocument();
    expect(within(card).queryByRole("button", { name: "Send back to QC" })).toBeNull();
    expect(
      within(card).getByText("Ask the moderator or your admin to upload it."),
    ).toBeInTheDocument();
  });
});
