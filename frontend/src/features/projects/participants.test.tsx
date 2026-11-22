// Requirements: PART-001, PART-005, PART-008, PART-009, PART-012
import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { SPEAKER_FIELDS } from "../../lib/speakers";
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
  speaker_min_age: 20,
  speaker_max_age: 60,
  required_speaker_details: SPEAKER_FIELDS.map((f) => f.key),
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
const MANAGERS = ["projects.view", "projects.manage", "participants.view", "participants.manage"];

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
    // One part only, the overview: no tabs to choose from (the Rules tab is for admins, D-145).
    expect(screen.queryByRole("navigation", { name: "Project sections" })).toBeNull();
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
    // One-word headings and the unit in each value, so the table fits a laptop (D-159).
    expect(await screen.findByRole("columnheader", { name: "Payable" })).toHaveAttribute(
      "title",
      "Half of approved: two participants share each conversation",
    );
    expect(
      screen
        .getAllByRole("columnheader")
        .map((h) => h.textContent)
        .slice(4, 7),
    ).toEqual(["Recorded", "Approved", "Payable"]);
    const row = screen.getByRole("row", { name: /P000001/ });
    const cells = within(row)
      .getAllByRole("cell")
      .map((c) => c.textContent);
    expect(cells.slice(4, 7)).toEqual(["9 min", "5 min", "2.5 min"]);
    // A code in one type everywhere, as on the Participants page (D-159).
    expect(within(row).getByRole("cell", { name: "P000001" })).toHaveClass("mono");
  });

  it("marks minutes the server did not send with a dash, without a unit (D-158)", async () => {
    const some = {
      conversations: 1,
      recorded_minutes: 0.07,
      approved_conversations: 0,
      approved_minutes: 0,
      payable_minutes: 0,
    };
    fakeApi(
      signedInAs(["projects.view", "projects.manage", "participants.view"], {
        "GET /api/v1/projects/p1": () => [200, project],
        "GET /api/v1/projects/p1/participants": () => [
          200,
          {
            items: [
              { ...asha, minutes: some },
              { ...hidden, minutes: null },
            ],
            total: 2,
            page: 1,
            page_size: 25,
          },
        ],
      }),
    );
    renderAt("/projects/p1/participants");
    const row = (code: string) =>
      within(screen.getByRole("row", { name: new RegExp(code) }))
        .getAllByRole("cell")
        .map((c) => c.textContent)
        .slice(4, 7);
    expect(await screen.findByRole("columnheader", { name: "Recorded" })).toBeInTheDocument();
    expect(row("P000001")).toEqual(["0.07 min", "0 min", "0 min"]);
    expect(row("P000002")).toEqual(["-", "-", "-"]);
  });

  it("has its buttons on the title row and the search in a filter bar, as the Participants page (D-158)", async () => {
    fakeApi(
      signedInAs([...MANAGERS, "participants.export"], {
        "GET /api/v1/projects/p1": () => [200, project],
        "GET /api/v1/projects/p1/participants": () => [
          200,
          { items: [asha], total: 1, page: 1, page_size: 25 },
        ],
      }),
    );
    renderAt("/projects/p1/participants");
    const add = await screen.findByRole("button", { name: "Add participant" });
    const header = screen
      .getByRole("heading", { level: 1, name: "Participants" })
      .closest(".page-header") as HTMLElement;
    // On the right of the title, the main one last.
    expect(header).toContainElement(add);
    expect(
      within(header)
        .getAllByRole("button")
        .map((b) => b.textContent),
    ).toEqual(["Add existing participant", "Export contacts", "Add participant"]);
    const filters = screen.getByRole("group", { name: "Filters" });
    expect(within(filters).queryByRole("button", { name: "Clear filters" })).toBeNull();
    const search = within(filters).getByRole("searchbox", { name: "Search by code or name" });
    await userEvent.type(search, "Asha");
    await userEvent.click(within(filters).getByRole("button", { name: "Clear filters" }));
    expect(search).toHaveValue("");
    expect(within(filters).queryByRole("button", { name: "Clear filters" })).toBeNull();
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
  }, 20000);

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
    expect(form.getByText("Correct the fields marked in red.")).toBeInTheDocument();
    await userEvent.type(form.getByLabelText(/Phone number/), "3210");
    await userEvent.selectOptions(form.getByLabelText("Country code"), "+44");
    await userEvent.click(form.getByRole("button", { name: "Add participant" }));
    expect(await screen.findByText("P000003 added. Consent form emailed.")).toBeInTheDocument();
    expect(calls.find((c) => c.method === "POST")?.body).toMatchObject({
      phone: "+449876543210",
      language_code: "ta",
    });
  }, 20000);

  it("checks a number by its country's length and never cuts a digit off (D-083)", async () => {
    const { calls } = fakeApi(
      signedInAs(MANAGERS, {
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
    await userEvent.type(form.getByLabelText(/Name or label/), "Mei");
    await userEvent.type(form.getByLabelText(/Email address/), "mei@example.org");
    await userEvent.selectOptions(form.getByLabelText(/^Language/), "hi");
    await fillSpeakerDetails(form);
    const phone = form.getByLabelText(/Phone number/);
    const add = form.getByRole("button", { name: "Add participant" });
    // India: exactly 10 digits. An eleventh is kept and said, not dropped without a word.
    await userEvent.type(phone, "09876543210");
    expect(phone).toHaveValue("09876543210");
    expect(form.getByText("Type exactly 10 digits (you typed 11).")).toBeInTheDocument();
    expect(add).toBeDisabled();
    // China: an 11-digit mobile is whole.
    await userEvent.selectOptions(form.getByLabelText("Country code"), "+86");
    await userEvent.clear(phone);
    await userEvent.type(phone, "13812345678");
    expect(phone).toHaveValue("13812345678");
    expect(form.queryByText(/digits \(you typed/)).toBeNull();
    expect(phone).toHaveAccessibleDescription("Without the country code.");
    // Singapore: 8 digits; too few is said in the country's own terms.
    await userEvent.selectOptions(form.getByLabelText("Country code"), "+65");
    await userEvent.clear(phone);
    await userEvent.type(phone, "9123");
    expect(form.getByText("Type 6 to 13 digits (you typed 4).")).toBeInTheDocument();
    await userEvent.type(phone, "4567");
    expect(add).toBeEnabled();
    await userEvent.click(add);
    expect(await screen.findByText("P000003 added. Consent form emailed.")).toBeInTheDocument();
    expect(calls.find((c) => c.method === "POST")?.body).toMatchObject({ phone: "+6591234567" });
  }, 20000);

  it("keeps a saved number from an unlisted country as it is when other details change", async () => {
    const polish = {
      ...asha,
      phone: "+48601234567",
      email: "asha@example.org",
      has_email: true,
    };
    const { calls } = fakeApi(
      signedInAs(MANAGERS, {
        "GET /api/v1/projects/p1": () => [200, project],
        "GET /api/v1/projects/p1/participants": () => [
          200,
          { items: [polish], total: 1, page: 1, page_size: 25 },
        ],
        "PATCH /api/v1/projects/p1/participants/a1": () => [200, polish],
      }),
    );
    renderAt("/projects/p1/participants");
    await userEvent.click(await screen.findByRole("button", { name: "Edit" }));
    const form = within(screen.getByRole("dialog", { name: "Edit P000001" }));
    // Not relabelled as India: "Other" holds the whole number with its country code.
    expect(form.getByLabelText("Country code")).toHaveValue("+");
    expect(form.getByRole("option", { name: "Other (type the country code too)" })).toBeTruthy();
    expect(form.getByLabelText(/Phone number/)).toHaveValue("48601234567");
    expect(form.getByLabelText(/Phone number/)).toHaveAccessibleDescription(
      "The whole number, starting with the country code.",
    );
    await userEvent.clear(form.getByLabelText(/Name or label/));
    await userEvent.type(form.getByLabelText(/Name or label/), "Asha K");
    await userEvent.click(form.getByRole("button", { name: "Save changes" }));
    expect(await screen.findByText("P000001 saved.")).toBeInTheDocument();
    expect(calls.find((c) => c.method === "PATCH")?.body).toMatchObject({
      display_label: "Asha K",
      phone: "+48601234567",
    });
  });

  it("opens each window clean, without the error of the window before", async () => {
    const withEmail = { ...asha, email: "asha@example.org", has_email: true };
    fakeApi(
      signedInAs(MANAGERS, {
        "GET /api/v1/projects/p1": () => [200, project],
        "GET /api/v1/projects/p1/participants": () => [
          200,
          { items: [withEmail], total: 1, page: 1, page_size: 25 },
        ],
        "PATCH /api/v1/projects/p1/participants/a1": () => [
          409,
          {
            error: {
              code: "DUPLICATE_PARTICIPANT",
              message: "A participant with this phone number already exists",
            },
          },
        ],
      }),
    );
    renderAt("/projects/p1/participants");
    await userEvent.click(await screen.findByRole("button", { name: "Edit" }));
    const edit = within(screen.getByRole("dialog", { name: "Edit P000001" }));
    await userEvent.click(edit.getByRole("button", { name: "Save changes" }));
    expect(await edit.findByText(/phone number already exists/)).toBeInTheDocument();
    await userEvent.click(edit.getByRole("button", { name: "Close" }));
    await userEvent.click(screen.getByRole("button", { name: "Add participant" }));
    const add = within(screen.getByRole("dialog", { name: "Add participant" }));
    expect(add.queryByText(/phone number already exists/)).toBeNull();
    expect(add.queryByRole("alert")).toBeNull();
    await userEvent.click(add.getByRole("button", { name: "Close" }));
    await userEvent.click(screen.getByRole("button", { name: "Edit" }));
    const again = within(screen.getByRole("dialog", { name: "Edit P000001" }));
    expect(again.queryByText(/phone number already exists/)).toBeNull();
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
    // How many are on offer beside the search box; the title bar holds the title and Add (N)
    // only, so it stays one row on a phone (D-159).
    const section = screen.getByRole("region", { name: "Add an existing participant" });
    const search = within(section).getByRole("searchbox", { name: "Search your other projects" });
    expect(search.closest(".pick__find")).toContainElement(within(section).getByText("1 person"));
    expect(section.querySelector(".card__head")?.textContent).toBe(
      "Add an existing participantAdd (0)",
    );
    // A code in one type everywhere, as on the Participants page (D-159).
    expect(within(section).getByRole("cell", { name: "P000009" })).toHaveClass("mono");
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
    expect(screen.getByRole("button", { name: "Add (0)" })).toBeDisabled();
    await userEvent.click(screen.getByLabelText("Select P000021"));
    await userEvent.click(screen.getByLabelText("Select P000023"));
    await userEvent.click(screen.getByRole("button", { name: "Add (2)" }));
    expect(
      await screen.findByText("2 participants added to this project. Consent form emailed."),
    ).toBeInTheDocument();
    expect(calls.filter((c) => c.path.endsWith("/link")).map((c) => c.body)).toEqual([
      { participant_code: "P000021" },
      { participant_code: "P000023" },
    ]);
    // Select all takes every one shown.
    await userEvent.click(screen.getByLabelText(/^Select all shown/));
    expect(screen.getByRole("button", { name: "Add (3)" })).toBeEnabled();
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
    const details = SPEAKER_INPUT.map((f) => f.label).join(", ");
    // The button says what it waits for (UXW-09), and the line shrinks as the form fills.
    expect(add).toHaveAccessibleDescription(
      `Still to fill: Name or label, Email address, Language, ${details}.`,
    );
    await userEvent.type(form.getByLabelText(/Name or label/), "Chitra");
    await userEvent.type(form.getByLabelText(/Email address/), "chitra@example.org");
    await userEvent.selectOptions(form.getByLabelText(/^Language/), "hi");
    expect(add).toHaveAccessibleDescription(`Still to fill: ${details}.`);
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
    expect(add).not.toHaveAccessibleDescription();
    expect(form.queryByText(/^Still to fill/)).toBeNull();
    // A wrong age or PIN code is said under the box and stops the form.
    await userEvent.clear(labelled(form, "Age"));
    await userEvent.type(labelled(form, "Age"), "61");
    expect(form.getByText("Age must be a whole number from 20 to 60.")).toBeInTheDocument();
    expect(add).toBeDisabled();
    expect(add).toHaveAccessibleDescription("Correct the fields marked in red.");
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
  }, 20000);

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

describe("participant form: the project's speaker rules (D-145)", () => {
  // Speakers aged 18 to 40; only age and gender are needed before a task.
  const narrow = {
    ...project,
    speaker_min_age: 18,
    speaker_max_age: 40,
    required_speaker_details: ["age", "gender"],
  };
  const managers = ["projects.view", "projects.manage", "participants.view", "participants.manage"];

  it("asks only for the details the project needs, and for an age in its range", async () => {
    const { calls } = fakeApi(
      signedInAs(managers, {
        "GET /api/v1/projects/p1": () => [200, narrow],
        "GET /api/v1/projects/p1/participants": () => [
          200,
          { items: [], total: 0, page: 1, page_size: 25 },
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
    expect(labelled(form, "Age")).toBeRequired();
    expect(labelled(form, "Gender")).toBeRequired();
    for (const f of SPEAKER_INPUT.slice(2)) expect(labelled(form, f.label)).not.toBeRequired();
    expect(form.getByText(/Those marked \* are needed/)).toBeInTheDocument();
    expect(labelled(form, "Age")).toHaveAccessibleDescription("Speakers aged 18 to 40.");
    await userEvent.type(form.getByLabelText(/Name or label/), "Chitra");
    await userEvent.type(form.getByLabelText(/Email address/), "chitra@example.org");
    await userEvent.selectOptions(form.getByLabelText(/^Language/), "hi");
    await userEvent.selectOptions(labelled(form, "Gender"), "FEMALE");
    await userEvent.type(labelled(form, "Age"), "41");
    expect(form.getByText("Age must be a whole number from 18 to 40.")).toBeInTheDocument();
    expect(add).toBeDisabled();
    await userEvent.clear(labelled(form, "Age"));
    await userEvent.type(labelled(form, "Age"), "18");
    expect(add).toBeEnabled(); // the other details may stay empty in this project
    await userEvent.click(add);
    expect(await screen.findByText("P000003 added. Consent form emailed.")).toBeInTheDocument();
    expect(calls.find((c) => c.method === "POST")?.body).toMatchObject({
      age: 18,
      gender: "FEMALE",
      current_state: null,
    });
  });

  it("keeps an age saved before outside the range, and says they cannot be put on a task", async () => {
    const older = {
      ...asha,
      email: "asha@example.org",
      has_email: true,
      age: 65,
      gender: "FEMALE",
      speaker_details_complete: true,
    };
    const { calls } = fakeApi(
      signedInAs(managers, {
        "GET /api/v1/projects/p1": () => [200, narrow],
        "GET /api/v1/projects/p1/participants": () => [
          200,
          { items: [older], total: 1, page: 1, page_size: 25 },
        ],
        "PATCH /api/v1/projects/p1/participants/a1": () => [200, older],
      }),
    );
    renderAt("/projects/p1/participants");
    await userEvent.click(await screen.findByRole("button", { name: "Edit" }));
    const form = within(screen.getByRole("dialog", { name: "Edit P000001" }));
    const save = form.getByRole("button", { name: "Save changes" });
    // Nothing is missing: only age and gender are needed here.
    expect(form.queryByRole("status")).toBeNull();
    expect(labelled(form, "Age")).toHaveAccessibleDescription(
      "Outside this project's speaker ages (18 to 40): they cannot be put on a task here.",
    );
    expect(save).toBeEnabled();
    await userEvent.clear(labelled(form, "Age"));
    await userEvent.type(labelled(form, "Age"), "66");
    expect(form.getByText("Age must be a whole number from 18 to 40.")).toBeInTheDocument();
    expect(save).toBeDisabled();
    await userEvent.clear(labelled(form, "Age"));
    await userEvent.type(labelled(form, "Age"), "65");
    await userEvent.click(save);
    expect(await screen.findByText("P000001 saved.")).toBeInTheDocument();
    expect(calls.find((c) => c.method === "PATCH")?.body).toMatchObject({ age: 65 });
  });
});
