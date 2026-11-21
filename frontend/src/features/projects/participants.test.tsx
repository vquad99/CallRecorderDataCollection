// Requirements: PART-001, PART-005, PART-008, PART-009, PART-012
import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { fakeApi, renderAt, signedInAs } from "../../test/fakeApi";
import { SPEAKER_DETAILS, SPEAKER_INPUT } from "../../test/world";

afterEach(() => vi.unstubAllGlobals());

// What the server says once someone joins a project: the form went out by itself (D-129).
const EMAILED = "Consent form emailed.";

type Box = ReturnType<typeof within>;
const labelled = (form: Box, label: string) => form.getByLabelText(new RegExp(`^${label}( \\*)?$`));

/** Every speaker detail, as a person fills them in for someone new (D-143). */
async function fillSpeakerDetails(form: Box) {
  for (const f of SPEAKER_INPUT) {
    if (f.list) await userEvent.selectOptions(labelled(form, f.label), f.value);
    else await userEvent.type(labelled(form, f.label), f.value);
  }
}

const project = {
  id: "p1",
  code: "VOICE",
  name: "Voice",
  status: "ACTIVE",
  allows_telephony: true,
  allows_face_to_face: true,
  target_telephony_hours_per_day: "0.00",
  target_face_to_face_hours_per_day: "0.00",
  created_at: "",
  description: "",
  phone_visibility_policy: "ADMINS_ONLY",
  consent_policy_version: "1",
  consent_text: "",
  status_reason: null,
  status_changed_at: null,
  languages: [],
  audio_rules: [],
  retention_rules: [],
  accepts_new_work: true,
};
const asha = {
  id: "a1",
  participant_code: "P000001",
  language_code: "hi",
  dialect: "",
  display_label: "Asha",
  phone: "+919876543210",
  phone_masked: false,
  has_phone: true,
  consent_visible: true,
  notes: "",
  deleted: false,
  created_at: "",
};
const hidden = {
  ...asha,
  id: "b1",
  participant_code: "P000002",
  display_label: null,
  phone: null,
  consent_visible: false,
};

describe("participants tab", () => {
  it("is not for people who do not manage the project: they have the overview only (D-104)", async () => {
    const { calls } = fakeApi(
      // What a moderator or client viewer holds: sees projects and participants, manages neither.
      signedInAs(["projects.view", "participants.view", "tasks.view", "exports.create"], {
        "GET /api/v1/projects/p1": () => [200, project],
        "GET /api/v1/projects/p1/participants": () => [
          200,
          { items: [asha], total: 1, page: 1, page_size: 25 },
        ],
      }),
    );
    renderAt("/projects/p1/participants");
    expect(await screen.findByRole("heading", { name: "No access" })).toBeInTheDocument();
    expect(screen.queryByText("P000001")).not.toBeInTheDocument();
    expect(calls.some((c) => c.path.startsWith("/api/v1/projects/p1/participants"))).toBe(false);
    // No tab bar at all: the overview is the only part they have.
    expect(screen.queryByRole("navigation", { name: "Project sections" })).not.toBeInTheDocument();
  });

  it("shows hidden fields as hidden and offers no editing without manage rights", async () => {
    fakeApi(
      // consent.view is held, but the server says this person's consent is not this user's to see.
      signedInAs(["projects.view", "projects.manage", "participants.view", "consent.view"], {
        "GET /api/v1/projects/p1": () => [200, project],
        "GET /api/v1/projects/p1/participants": () => [
          200,
          { items: [hidden], total: 1, page: 1, page_size: 25 },
        ],
      }),
    );
    renderAt("/projects/p1/participants");
    expect(await screen.findByText("P000002")).toBeInTheDocument();
    expect(screen.getAllByText("Hidden")).toHaveLength(2);
    expect(screen.queryByRole("button", { name: "Add participant" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Export contacts" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Consent history" })).not.toBeInTheDocument();
  });

  it("shows recorded, approved and payable minutes when the server sends them (D-095)", async () => {
    const minutes = {
      conversations: 2,
      recorded_minutes: 9,
      approved_conversations: 1,
      approved_minutes: 5,
      payable_minutes: 2.5,
    };
    fakeApi(
      signedInAs(["projects.view", "projects.manage", "participants.view"], {
        "GET /api/v1/projects/p1": () => [200, project],
        "GET /api/v1/projects/p1/participants": () => [
          200,
          { items: [{ ...asha, minutes }], total: 1, page: 1, page_size: 25 },
        ],
      }),
    );
    renderAt("/projects/p1/participants");
    expect(await screen.findByRole("columnheader", { name: /Payable min/ })).toBeInTheDocument();
    const row = screen.getByRole("row", { name: /P000001/ });
    expect(row).toHaveTextContent("9");
    expect(row).toHaveTextContent("5");
    expect(row).toHaveTextContent("2.5");
  });

  it("adds a participant and deletes one with a reason", async () => {
    const { calls } = fakeApi(
      signedInAs(["projects.view", "projects.manage", "participants.view", "participants.manage"], {
        "GET /api/v1/projects/p1": () => [200, project],
        "GET /api/v1/projects/p1/participants": () => [
          200,
          { items: [asha], total: 1, page: 1, page_size: 25 },
        ],
        "POST /api/v1/projects/p1/participants": () => [
          201,
          { ...asha, id: "c1", participant_code: "P000003", consent_email: EMAILED },
        ],
        "POST /api/v1/projects/p1/participants/a1/delete": () => [200, { ...asha, deleted: true }],
      }),
    );
    renderAt("/projects/p1/participants");
    await userEvent.click(await screen.findByRole("button", { name: "Add participant" }));
    const form = within(screen.getByRole("dialog", { name: "Add participant" }));
    await userEvent.type(form.getByLabelText(/Name or label/), "Chitra");
    await userEvent.type(form.getByLabelText(/Email address/), "chitra@example.org");
    await userEvent.selectOptions(form.getByLabelText(/^Language/), "hi");
    await fillSpeakerDetails(form);
    await userEvent.click(form.getByRole("button", { name: "Add participant" }));
    expect(await screen.findByText("P000003 added. Consent form emailed.")).toBeInTheDocument();
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(calls.find((c) => c.method === "POST")?.body).toEqual({
      display_label: "Chitra",
      phone: null,
      email: "chitra@example.org",
      language_code: "hi",
      dialect: "",
      notes: "",
      ...SPEAKER_DETAILS,
    });

    await userEvent.click(screen.getByRole("button", { name: "Delete" }));
    const box = within(screen.getByRole("dialog", { name: "Delete P000001?" }));
    await userEvent.type(
      box.getByLabelText(/Why is this participant deleted/),
      "Asked to be removed",
    );
    await userEvent.click(box.getByRole("button", { name: "Delete" }));
    expect(await screen.findByText("P000001 deleted.")).toBeInTheDocument();
    expect(calls.find((c) => c.path.endsWith("/delete"))?.body).toEqual({
      reason: "Asked to be removed",
    });
  });

  it("takes a 10-digit phone number with the country code chosen from a list", async () => {
    const { calls } = fakeApi(
      signedInAs(["projects.view", "projects.manage", "participants.view", "participants.manage"], {
        "GET /api/v1/projects/p1": () => [200, project],
        "GET /api/v1/projects/p1/participants": () => [
          200,
          { items: [asha], total: 1, page: 1, page_size: 25 },
        ],
        "POST /api/v1/projects/p1/participants": () => [
          201,
          { ...asha, id: "c1", participant_code: "P000003", consent_email: EMAILED },
        ],
      }),
    );
    renderAt("/projects/p1/participants");
    await userEvent.click(await screen.findByRole("button", { name: "Add participant" }));
    const form = within(screen.getByRole("dialog", { name: "Add participant" }));
    await userEvent.type(form.getByLabelText(/Name or label/), "Chitra");
    await userEvent.type(form.getByLabelText(/Email address/), "chitra@example.org");
    await userEvent.selectOptions(form.getByLabelText(/^Language/), "ta");
    await fillSpeakerDetails(form);
    await userEvent.type(form.getByLabelText(/Phone number/), "98765-4");
    expect(form.getByText("Type exactly 10 digits (you typed 6).")).toBeInTheDocument();
    expect(form.getByRole("button", { name: "Add participant" })).toBeDisabled();
    await userEvent.type(form.getByLabelText(/Phone number/), "32109");
    await userEvent.selectOptions(form.getByLabelText("Country code"), "+44");
    await userEvent.click(form.getByRole("button", { name: "Add participant" }));
    expect(await screen.findByText("P000003 added. Consent form emailed.")).toBeInTheDocument();
    expect(calls.find((c) => c.method === "POST")?.body).toMatchObject({
      phone: "+449876543210",
      language_code: "ta",
    });
  });

  it("adds an existing participant from another project (D-090)", async () => {
    const quinn = {
      id: "q1",
      participant_code: "P000009",
      display_label: "Quinn",
      language_code: "hi",
      dialect: "Awadhi",
    };
    const { calls } = fakeApi(
      signedInAs(["projects.view", "projects.manage", "participants.view", "participants.manage"], {
        "GET /api/v1/projects/p1": () => [200, project],
        "GET /api/v1/projects/p1/participants": () => [
          200,
          { items: [asha], total: 1, page: 1, page_size: 25 },
        ],
        "GET /api/v1/projects/p1/participants/link-candidates": () => [200, [quinn]],
        "POST /api/v1/projects/p1/participants/link": () => [
          201,
          { ...asha, id: "q1", participant_code: "P000009", consent_email: EMAILED },
        ],
      }),
    );
    renderAt("/projects/p1/participants");
    await userEvent.click(await screen.findByRole("button", { name: "Add existing participant" }));
    expect(await screen.findByText("Quinn")).toBeInTheDocument();
    expect(screen.getByText("Hindi (hi) · Awadhi")).toBeInTheDocument();
    expect(screen.getByText("1 person")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Add P000009" }));
    expect(
      await screen.findByText("P000009 added to this project. Consent form emailed."),
    ).toBeInTheDocument();
    expect(calls.find((c) => c.path.endsWith("/link"))?.body).toEqual({
      participant_code: "P000009",
    });
  });

  it("adds several existing participants at once (D-116)", async () => {
    const others = ["P000021", "P000022", "P000023"].map((code, i) => ({
      language_code: "hi",
      dialect: "",
      id: `x${i}`,
      participant_code: code,
      display_label: `Person ${i + 1}`,
    }));
    const { calls } = fakeApi(
      signedInAs(["projects.view", "projects.manage", "participants.view", "participants.manage"], {
        "GET /api/v1/projects/p1": () => [200, project],
        "GET /api/v1/projects/p1/participants": () => [
          200,
          { items: [asha], total: 1, page: 1, page_size: 25 },
        ],
        "GET /api/v1/projects/p1/participants/link-candidates": () => [200, others],
        "POST /api/v1/projects/p1/participants/link": (body) => [
          201,
          {
            ...asha,
            participant_code: (body as { participant_code: string }).participant_code,
            consent_email: EMAILED,
          },
        ],
      }),
    );
    renderAt("/projects/p1/participants");
    await userEvent.click(await screen.findByRole("button", { name: "Add existing participant" }));
    expect(await screen.findByText("Person 1")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Add selected (0)" })).toBeDisabled();
    await userEvent.click(screen.getByLabelText("Select P000021"));
    await userEvent.click(screen.getByLabelText("Select P000023"));
    await userEvent.click(screen.getByRole("button", { name: "Add selected (2)" }));
    expect(
      await screen.findByText("2 participants added to this project. Consent form emailed."),
    ).toBeInTheDocument();
    expect(calls.filter((c) => c.path.endsWith("/link")).map((c) => c.body)).toEqual([
      { participant_code: "P000021" },
      { participant_code: "P000023" },
    ]);
    // Select all takes every one shown.
    await userEvent.click(screen.getByLabelText(/^Select all shown/));
    expect(screen.getByRole("button", { name: "Add selected (3)" })).toBeEnabled();
  });

  it("edits a participant without sending a masked phone back as the number", async () => {
    const masked = { ...asha, phone: "••••••3210", phone_masked: true, has_email: false };
    const { calls } = fakeApi(
      signedInAs(["projects.view", "projects.manage", "participants.view", "participants.manage"], {
        "GET /api/v1/projects/p1": () => [200, project],
        "GET /api/v1/projects/p1/participants": () => [
          200,
          { items: [masked], total: 1, page: 1, page_size: 25 },
        ],
        "PATCH /api/v1/projects/p1/participants/a1": () => [200, masked],
      }),
    );
    renderAt("/projects/p1/participants");
    await userEvent.click(await screen.findByRole("button", { name: "Edit" }));
    const form = within(screen.getByRole("dialog", { name: "Edit P000001" }));
    expect(form.getByLabelText(/Phone number/)).toHaveValue("");
    // D-128: someone saved without an email gets one before the change is saved.
    expect(form.getByLabelText(/Email address/)).toBeRequired();
    await userEvent.type(form.getByLabelText(/Email address/), "asha@example.org");
    await userEvent.click(form.getByRole("button", { name: "Save changes" }));
    expect(await screen.findByText("P000001 saved.")).toBeInTheDocument();
    expect(calls.find((c) => c.method === "PATCH")?.body).toMatchObject({
      phone: null,
      email: "asha@example.org",
    });
  });

  it("needs every speaker detail for someone new and says what is wrong (D-143)", async () => {
    const { calls } = fakeApi(
      signedInAs(["projects.view", "projects.manage", "participants.view", "participants.manage"], {
        "GET /api/v1/projects/p1": () => [200, project],
        "GET /api/v1/projects/p1/participants": () => [
          200,
          { items: [asha], total: 1, page: 1, page_size: 25 },
        ],
        "POST /api/v1/projects/p1/participants": () => [
          201,
          { ...asha, id: "c1", participant_code: "P000003", consent_email: EMAILED },
        ],
      }),
    );
    renderAt("/projects/p1/participants");
    await userEvent.click(await screen.findByRole("button", { name: "Add participant" }));
    const form = within(screen.getByRole("dialog", { name: "Add participant" }));
    const add = form.getByRole("button", { name: "Add participant" });
    await userEvent.type(form.getByLabelText(/Name or label/), "Chitra");
    await userEvent.type(form.getByLabelText(/Email address/), "chitra@example.org");
    await userEvent.selectOptions(form.getByLabelText(/^Language/), "hi");
    expect(form.getByRole("group", { name: "Speaker details" })).toBeInTheDocument();
    // Short fields side by side; every one is required.
    for (const f of SPEAKER_INPUT) expect(labelled(form, f.label)).toBeRequired();
    expect(labelled(form, "Current state").closest(".form-grid")).toContainElement(
      labelled(form, "Current PIN code"),
    );
    // The states of India, the education levels and the two media, in words.
    const states = within(labelled(form, "Native state")).getAllByRole("option");
    expect(states).toHaveLength(37);
    expect(states.map((o) => o.textContent)).toContain("Dadra and Nagar Haveli and Daman and Diu");
    expect(
      within(labelled(form, "Education"))
        .getAllByRole("option")
        .map((o) => o.textContent),
    ).toEqual([
      "Choose",
      "Primary School",
      "Secondary School",
      "Higher Secondary",
      "Diploma",
      "Bachelor's Degree",
      "Master's Degree",
      "PhD",
      "Other",
    ]);
    expect(
      within(labelled(form, "Medium of education"))
        .getAllByRole("option")
        .map((o) => o.textContent),
    ).toEqual(["Choose", "English", "Non-English"]);
    expect(add).toBeDisabled();
    await fillSpeakerDetails(form);
    expect(add).toBeEnabled();
    // A wrong age or PIN code is said under the box and stops the form.
    await userEvent.clear(labelled(form, "Age"));
    await userEvent.type(labelled(form, "Age"), "61");
    expect(form.getByText("Age must be a whole number from 20 to 60.")).toBeInTheDocument();
    expect(add).toBeDisabled();
    await userEvent.clear(labelled(form, "Age"));
    await userEvent.type(labelled(form, "Age"), "20");
    await userEvent.clear(labelled(form, "Native PIN code"));
    await userEvent.type(labelled(form, "Native PIN code"), "0a12345");
    expect(labelled(form, "Native PIN code")).toHaveValue("012345");
    expect(
      form.getByText("Type the 6 digits of the PIN code; it cannot start with 0."),
    ).toBeInTheDocument();
    expect(add).toBeDisabled();
    await userEvent.clear(labelled(form, "Native PIN code"));
    await userEvent.type(labelled(form, "Native PIN code"), "403601");
    await userEvent.click(add);
    expect(await screen.findByText("P000003 added. Consent form emailed.")).toBeInTheDocument();
    expect(calls.find((c) => c.method === "POST")?.body).toMatchObject({
      ...SPEAKER_DETAILS,
      age: 20,
    });
  });

  it("saves someone added before without speaker details and says what is missing (D-143)", async () => {
    const old = {
      ...asha,
      email: "asha@example.org",
      has_email: true,
      district: "Pune",
      age: 41,
      speaker_details_complete: false,
    };
    const { calls } = fakeApi(
      signedInAs(["projects.view", "projects.manage", "participants.view", "participants.manage"], {
        "GET /api/v1/projects/p1": () => [200, project],
        "GET /api/v1/projects/p1/participants": () => [
          200,
          { items: [old], total: 1, page: 1, page_size: 25 },
        ],
        "PATCH /api/v1/projects/p1/participants/a1": () => [200, old],
      }),
    );
    renderAt("/projects/p1/participants");
    await userEvent.click(await screen.findByRole("button", { name: "Edit" }));
    const form = within(screen.getByRole("dialog", { name: "Edit P000001" }));
    expect(labelled(form, "Age")).toHaveValue(41);
    expect(labelled(form, "Native district")).toHaveValue("Pune");
    expect(labelled(form, "Gender")).not.toBeRequired();
    expect(form.getByRole("status")).toHaveTextContent(
      "Missing: Gender, Current state, Current district, Current PIN code, Native state, " +
        "Native PIN code, Native language, Education, Medium of education, Recording state, " +
        "Recording district, Recording PIN code.",
    );
    await userEvent.selectOptions(labelled(form, "Gender"), "MALE");
    expect(form.getByRole("status")).not.toHaveTextContent("Gender,");
    await userEvent.click(form.getByRole("button", { name: "Save changes" }));
    expect(await screen.findByText("P000001 saved.")).toBeInTheDocument();
    expect(calls.find((c) => c.method === "PATCH")?.body).toMatchObject({
      age: 41,
      gender: "MALE",
      district: "Pune",
      current_state: null,
      recording_pincode: null,
    });
  });

  it("marks people whose speaker details are missing (D-143)", async () => {
    fakeApi(
      signedInAs(["projects.view", "projects.manage", "participants.view", "participants.manage"], {
        "GET /api/v1/projects/p1": () => [200, project],
        "GET /api/v1/projects/p1/participants": () => [
          200,
          {
            items: [
              { ...asha, speaker_details_complete: true },
              { ...hidden, display_label: "Bina", speaker_details_complete: false },
            ],
            total: 2,
            page: 1,
            page_size: 25,
          },
        ],
      }),
    );
    renderAt("/projects/p1/participants");
    const missing = (await screen.findByText("P000002")).closest("tr") as HTMLElement;
    expect(within(missing).getByText("Details missing")).toBeInTheDocument();
    const complete = screen.getByText("P000001").closest("tr") as HTMLElement;
    expect(within(complete).queryByText("Details missing")).toBeNull();
  });
});
