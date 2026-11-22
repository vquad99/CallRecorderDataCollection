// A consent form QC sent back (D-146): the moderator sees whose form and what QC found, uploads a
// new scan and sends the same recording back to QC; the stepper shows the task waiting at Audio
// QC; QC reads the same card without the button.
// Requirements: PART-006, PART-016, TASK-003, TASK-004, AQC-008
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { fakeApi, renderAt, signedInAs } from "../../test/fakeApi";
import {
  ALL_PERMISSIONS,
  DOCUMENT,
  NO_DOCUMENTS,
  PARTICIPANT,
  TASK,
  worldHandlers,
} from "../../test/world";

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
    // The participants matrix agrees with the card (UXW-03): A's form is the one to replace.
    const people = screen.getByRole("table", { name: "Both participants" });
    const row = (name: string) =>
      within(people).getByRole("rowheader", { name }).closest("tr") as HTMLElement;
    expect(row("Consent")).toHaveTextContent("ConsentNew form neededForm uploaded");
    const form = within(row("Consent form")).getByRole("button", {
      name: "View the signed consent form of P000001",
    });
    expect(form).toHaveAttribute("title", "asha-consent.pdf · QC: Not signed on page 2");

    await userEvent.upload(
      within(card).getByLabelText("Upload a new consent form of P000001"),
      new File(["%PDF-1.7 signed"], "signed-again.pdf", { type: "application/pdf" }),
    );
    expect(await within(card).findByText("New form uploaded")).toBeInTheDocument();
    expect(row("Consent")).toHaveTextContent("ConsentForm uploadedForm uploaded");
    await userEvent.click(within(card).getByRole("button", { name: "Send back to QC" }));
    expect(await screen.findByText("Sent back to QC with the same recording.")).toBeInTheDocument();
    expect(calls.find((c) => c.path === "/api/v1/tasks/t1/consent-fix/send-to-qc")?.body).toEqual({
      comment: "",
    });
    expect(screen.queryByRole("region", { name: "Consent form to fix" })).toBeNull();
  });

  it("follows a new form uploaded in the participant's details window (FEW-13)", async () => {
    let replaced = false;
    const fixed = {
      ...FIX,
      forms_replaced: true,
      participants: [{ ...FIX.participants[0], replaced: true }],
    };
    const { calls } = fakeApi(
      signedInAs(ALL_PERMISSIONS, {
        ...worldHandlers(),
        "GET /api/v1/tasks/t1": () => [200, replaced ? waiting(fixed) : waiting()],
        "GET /api/v1/tasks/t1/audio-qc": () => [200, QC_VIEW],
        "GET /api/v1/projects/p1/participants/a1/details": () => [
          200,
          {
            participant: { ...PARTICIPANT, consent_status: "UPLOADED", has_consent_form: true },
            updated_at: "2026-11-12T10:00:00Z",
            added_by: null,
            projects: [],
            removed: null,
            link: null,
            consent_form: null,
            sessions: [],
            sessions_total: 0,
            minutes: null,
            calls: null,
          },
        ],
        "GET /api/v1/projects/p1/participants/a1/documents": () => [
          200,
          {
            ...NO_DOCUMENTS,
            consent_mode: "UPLOAD",
            consent_form: DOCUMENT,
            may_upload_consent_form: true,
          },
        ],
        "POST /api/v1/projects/p1/participants/a1/documents/consent-form": () => {
          replaced = true;
          return [201, { ...DOCUMENT, id: "d9", file_name: "signed-again.pdf" }];
        },
      }),
    );
    renderAt("/tasks/t1");
    const card = await screen.findByRole(
      "region",
      { name: "Consent form to fix" },
      { timeout: 5000 },
    );
    expect(within(card).getByRole("button", { name: "Send back to QC" })).toBeDisabled();
    await userEvent.click(screen.getByRole("button", { name: "View the details of P000001" }));
    const panel = within(await screen.findByRole("dialog", { name: "Participant details" }));
    await userEvent.upload(
      await panel.findByLabelText("Replace signed consent form"),
      new File(["%PDF-1.7 signed"], "signed-again.pdf", { type: "application/pdf" }),
    );
    expect(await panel.findByText("Signed consent form uploaded.")).toBeInTheDocument();
    // The task behind the window is loaded again: the card and the matrix follow at once.
    expect(await screen.findByText("Documents of P000001 updated.")).toBeInTheDocument();
    await waitFor(() =>
      expect(within(card).getByRole("button", { name: "Send back to QC" })).toBeEnabled(),
    );
    expect(within(card).getByText("New form uploaded")).toBeInTheDocument();
    expect(calls.filter((c) => c.method === "GET" && c.path === "/api/v1/tasks/t1")).toHaveLength(
      2,
    );
  });

  it("asks for an online answer once the project takes consent online (SECB-03)", async () => {
    fakeApi(
      signedInAs(ALL_PERMISSIONS, {
        ...worldHandlers(),
        "GET /api/v1/tasks/t1": () => [
          200,
          {
            ...waiting({ ...FIX, by_upload: false }),
            consent_mode: "ONLINE",
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
    expect(within(card).getByText(/This project now takes consent online/)).toBeInTheDocument();
    expect(within(card).getByText("Not agreed yet")).toBeInTheDocument();
    expect(within(card).queryByText("New form needed")).toBeNull();
    expect(within(card).queryByLabelText("Upload a new consent form of P000001")).toBeNull();
    expect(within(card).queryByText("Ask the moderator or your admin to upload it.")).toBeNull();
    expect(
      within(card).getByRole("button", { name: "Send back to QC" }),
    ).toHaveAccessibleDescription("They agree on their personal page first.");
    const people = screen.getByRole("table", { name: "Both participants" });
    const consentRow = within(people).getByRole("rowheader", { name: "Consent" }).closest("tr");
    expect(consentRow).toHaveTextContent("Not agreed yet");
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
