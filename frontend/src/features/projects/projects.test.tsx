// Requirements: PROJ-009, PROJ-013, ROLE-011, USER-003, EXP-008, EXP-009, EXP-010, PART-006, AQC-008, PROJ-011
import { act, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { SPEAKER_FIELDS } from "../../lib/speakers";
import { fakeApi, renderAt, signedInAs } from "../../test/fakeApi";
import { PROJECT } from "../../test/world";
import { CLIENT_QC_CHECKLIST } from "./qcChecklist";
import { CLIENT_REMINDERS } from "./reminders";

afterEach(() => vi.unstubAllGlobals());

/** Audio, progress and targets (D-148), as a new project starts. */
const TARGETS = {
  pause_limit_seconds: PROJECT.pause_limit_seconds,
  long_pauses_need_review: PROJECT.long_pauses_need_review,
  progress_counts: PROJECT.progress_counts,
  target_hours: PROJECT.target_hours,
  target_speakers: PROJECT.target_speakers,
  target_conversations: PROJECT.target_conversations,
  target_age_bands: PROJECT.target_age_bands,
  target_gender: PROJECT.target_gender,
  target_modes: PROJECT.target_modes,
  target_districts: PROJECT.target_districts,
};

/** How exports are laid out and named (D-149), as a new project starts. */
const DELIVERY = {
  export_layout: PROJECT.export_layout,
  speaker_id_style: PROJECT.speaker_id_style,
  conversation_id_style: PROJECT.conversation_id_style,
  audio_name_pattern: PROJECT.audio_name_pattern,
};

const SUMMARY = {
  recordings: 3,
  face_to_face: 2,
  telephony: 1,
  audio_bytes: 240_000_000,
  file_name: "audio_HINDI_20261111_0900.zip",
  layout: "CLIENT",
  missing: 0,
};
const JOB = {
  id: "x1",
  state: "READY",
  content: "audio",
  scope: "finished",
  table_format: "tsv",
  filters: {},
  file_name: "audio_HINDI_20261111_0900.zip",
  recordings: 3,
  files: 12,
  missing: 0,
  size_bytes: 240_000_000,
  sha256: "ab".repeat(32),
  error: null,
  requested_by: "Priya Admin",
  created_at: "2026-11-11T09:00:00Z",
  finished_at: "2026-11-11T09:01:00Z",
  expires_at: "2026-11-12T09:01:00Z",
  downloads: 0,
  last_downloaded_at: null,
};

const project = {
  id: "p1",
  code: "HINDI",
  name: "Hindi conversations",
  status: "DRAFT",
  allows_telephony: true,
  allows_face_to_face: false,
  target_telephony_hours_per_day: "10.00",
  target_face_to_face_hours_per_day: "0.00",
  created_at: "2026-11-09T00:00:00Z",
  description: "",
  phone_visibility_policy: "ADMINS_ONLY",
  consent_policy_version: "1",
  consent_text: "",
  qc_final_approval: false,
  max_conversations_per_speaker: 3,
  unique_pairs: true,
  consent_mode: "ONLINE",
  speaker_min_age: 20,
  speaker_max_age: 60,
  required_speaker_details: SPEAKER_FIELDS.map((f) => f.key),
  qc_checklist: PROJECT.qc_checklist,
  device_fields: PROJECT.device_fields,
  recording_reminders: PROJECT.recording_reminders,
  ...TARGETS,
  ...DELIVERY,
  status_reason: null,
  status_changed_at: null,
  languages: [{ language_code: "hi", dialect: "Awadhi" }],
  audio_rules: [
    {
      mode: "TELEPHONY",
      sample_rate: 16000,
      bit_depth: 16,
      channels: 2,
      max_silence_pct: "25.00",
      max_clipping_pct: null,
      min_duration_seconds: 0,
      max_duration_seconds: null,
    },
  ],
  retention_rules: [],
  accepts_new_work: false,
};

describe("project detail", () => {
  it("lets a project manager change status through the API", async () => {
    const { calls } = fakeApi(
      signedInAs(["projects.view", "projects.manage", "projects.members"], {
        "GET /api/v1/projects/p1": () => [200, project],
        "POST /api/v1/projects/p1/status": () => [
          200,
          { ...project, status: "ACTIVE", accepts_new_work: true },
        ],
      }),
    );
    renderAt("/projects/p1");
    expect(
      await screen.findByRole("heading", { name: "HINDI · Hindi conversations" }),
    ).toBeInTheDocument();
    // The Overview tab loads on first visit (O11): wait for it, not just the page heading.
    // One button for each status the project can move to; no list to pick from first.
    expect(screen.queryByLabelText("Change status to")).not.toBeInTheDocument();
    await userEvent.click(await screen.findByRole("button", { name: "Make active" }));
    await userEvent.click(
      within(screen.getByRole("dialog")).getByRole("button", { name: "Make active" }),
    );
    expect(await screen.findByText("Status changed to Active.")).toBeInTheDocument();
    expect(screen.getByText("This project accepts new work.")).toBeInTheDocument();
    expect(calls.find((c) => c.path === "/api/v1/projects/p1/status")?.body).toEqual({
      status: "ACTIVE",
      reason: null,
    });
  });

  it("keeps the rules off the Overview form and sends them back as they are (D-145)", async () => {
    const { calls } = fakeApi(
      signedInAs(["projects.view", "projects.manage"], {
        "GET /api/v1/projects/p1": () => [200, { ...project, qc_final_approval: true }],
        "PATCH /api/v1/projects/p1": (body) => [200, { ...project, ...(body as object) }],
      }),
    );
    renderAt("/projects/p1");
    const name = await screen.findByLabelText(/^Name/);
    // The pairing, consent and approval rules moved to the Rules tab.
    expect(screen.queryByRole("checkbox", { name: /QC pass is the final approval/ })).toBeNull();
    expect(screen.queryByLabelText("Conversations per speaker (at most)")).toBeNull();
    expect(screen.queryByRole("checkbox", { name: "Each pair of speakers only once" })).toBeNull();
    expect(screen.queryByRole("radio", { name: /^Online/ })).toBeNull();
    expect(screen.queryByLabelText("Youngest speaker age")).toBeNull();
    await userEvent.type(name, " 2");
    await userEvent.click(screen.getByRole("button", { name: "Save project" }));
    await waitFor(() =>
      expect(calls.find((c) => c.method === "PATCH")?.body).toEqual({
        name: "Hindi conversations 2",
        description: "",
        allows_telephony: true,
        allows_face_to_face: false,
        target_telephony_hours_per_day: "10.00",
        target_face_to_face_hours_per_day: "0.00",
        phone_visibility_policy: "ADMINS_ONLY",
        consent_policy_version: "1",
        consent_text: "",
        qc_final_approval: true,
        max_conversations_per_speaker: 3,
        unique_pairs: true,
        consent_mode: "ONLINE",
        speaker_min_age: 20,
        speaker_max_age: 60,
        required_speaker_details: project.required_speaker_details,
        qc_checklist: project.qc_checklist, // D-146: the checklist goes back as it is too
        device_fields: project.device_fields, // D-147: and what the moderator fills and reads
        recording_reminders: project.recording_reminders,
        ...TARGETS, // D-148: and the audio, progress and target settings
        ...DELIVERY, // D-149: and how exports are laid out and named
      }),
    );
  });

  it("loads the rules one section at a time and saves each with the rest as it is (D-145, D-150)", async () => {
    const { calls } = fakeApi(
      signedInAs(["projects.view", "projects.manage"], {
        "GET /api/v1/projects/p1": () => [200, project],
        "PATCH /api/v1/projects/p1": (body) => [200, { ...project, ...(body as object) }],
      }),
    );
    // The Rules page's own address opens its first section.
    const router = renderAt("/projects/p1/rules");
    const youngest = await screen.findByRole("spinbutton", { name: "Youngest speaker age" });
    expect(router.state.location.pathname).toBe("/projects/p1/rules/speakers");
    expect(screen.getByRole("heading", { level: 1, name: "Rules" })).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Speakers" })).toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "Consent" })).toBeNull();
    // Its sections are under Rules in the project's menu, the open one marked.
    const menu = screen.getByRole("navigation", { name: "Project sections" });
    expect(within(menu).getByRole("link", { name: "Rules" })).toHaveAttribute(
      "aria-current",
      "true",
    );
    const rulesItem = within(menu).getByRole("link", { name: "Rules" }).closest("li");
    const sections = within(rulesItem as HTMLElement)
      .getAllByRole("link")
      .slice(1);
    expect(sections.map((l) => l.textContent)).toEqual([
      "Speakers",
      "Consent",
      "Approval",
      "QC checklist",
      "Device details",
      "Reminders for moderators",
      "Audio and progress",
      "Targets",
      "Export format",
    ]);
    expect(within(menu).getByRole("link", { name: "Speakers" })).toHaveAttribute(
      "aria-current",
      "page",
    );
    const oldest = screen.getByRole("spinbutton", { name: "Oldest speaker age" });
    expect(youngest).toHaveValue(20);
    expect(oldest).toHaveValue(60);
    const details = screen.getByRole("group", { name: "Speaker details needed before a task" });
    const boxes = within(details).getAllByRole("checkbox");
    expect(boxes).toHaveLength(14);
    for (const box of boxes) expect(box).toBeChecked();
    // Grouped like the participant form.
    expect(
      within(within(details).getByRole("group", { name: "Where they were born" }))
        .getAllByRole("checkbox")
        .map((b) => b.closest("label")?.textContent),
    ).toEqual(["Native state", "Native district", "Native PIN code"]);
    const limit = screen.getByRole("spinbutton", { name: "Conversations per speaker (at most)" });
    const once = screen.getByRole("checkbox", { name: "Each pair of speakers only once" });
    expect(limit).toHaveValue(3);
    expect(once).toBeChecked();

    await userEvent.clear(youngest);
    await userEvent.type(youngest, "18");
    await userEvent.clear(oldest);
    await userEvent.type(oldest, "70");
    await userEvent.click(within(details).getByRole("checkbox", { name: "Education" }));
    await userEvent.click(within(details).getByRole("checkbox", { name: "Medium of education" }));
    await userEvent.clear(limit);
    await userEvent.type(limit, "5");
    await userEvent.click(once);
    await userEvent.click(screen.getByRole("button", { name: "Save rules" }));
    expect(await screen.findByText("Rules saved.")).toBeInTheDocument();
    const patches = () => calls.filter((c) => c.method === "PATCH");
    expect(patches()).toHaveLength(1);
    expect(patches()[0]?.body).toMatchObject({
      name: "Hindi conversations", // the Overview's settings go back as they are
      consent_text: "",
      speaker_min_age: 18,
      speaker_max_age: 70,
      required_speaker_details: project.required_speaker_details.filter(
        (k) => k !== "education" && k !== "education_medium",
      ),
      max_conversations_per_speaker: 5,
      unique_pairs: false,
      consent_mode: "ONLINE", // the other sections go back as they are
      qc_final_approval: false,
    });
    // Empty means no limit.
    await userEvent.clear(limit);
    await userEvent.click(screen.getByRole("button", { name: "Save rules" }));
    await waitFor(() => expect(patches()).toHaveLength(2));
    expect(patches()[1]?.body).toMatchObject({ max_conversations_per_speaker: null });

    // Consent, on its own page: it starts from what was just saved.
    await userEvent.click(within(menu).getByRole("link", { name: "Consent" }));
    const consent = await screen.findByRole("group", { name: "How participants give consent" });
    expect(router.state.location.pathname).toBe("/projects/p1/rules/consent");
    expect(screen.queryByRole("region", { name: "Speakers" })).toBeNull();
    expect(within(consent).getByRole("radio", { name: /^Online/ })).toBeChecked();
    expect(consent).toHaveAccessibleDescription(/is emailed the consent form/);
    await userEvent.click(
      within(consent).getByRole("radio", { name: "Upload (scanned signed form)" }),
    );
    expect(consent).toHaveAccessibleDescription(/No consent form is emailed/);
    await userEvent.click(screen.getByRole("button", { name: "Save rules" }));
    await waitFor(() => expect(patches()).toHaveLength(3));
    expect(patches()[2]?.body).toMatchObject({
      speaker_min_age: 18,
      max_conversations_per_speaker: null,
      consent_mode: "UPLOAD",
      qc_final_approval: false,
    });

    // Approval.
    await userEvent.click(within(menu).getByRole("link", { name: "Approval" }));
    const qc = await screen.findByRole("checkbox", {
      name: "QC pass is the final approval (no admin review)",
    });
    expect(qc).not.toBeChecked();
    await userEvent.click(qc);
    await userEvent.click(screen.getByRole("button", { name: "Save rules" }));
    await waitFor(() => expect(patches()).toHaveLength(4));
    expect(patches()[3]?.body).toMatchObject({ consent_mode: "UPLOAD", qc_final_approval: true });
  });

  it("opens the first section for an unknown one (D-150)", async () => {
    fakeApi(
      signedInAs(["projects.view", "projects.manage"], {
        "GET /api/v1/projects/p1": () => [200, project],
      }),
    );
    const router = renderAt("/projects/p1/rules/no-such-section");
    expect(await screen.findByRole("region", { name: "Speakers" })).toBeInTheDocument();
    expect(router.state.location.pathname).toBe("/projects/p1/rules/speakers");
  });

  it("says when the speaker ages are wrong and sends nothing (D-145)", async () => {
    const { calls } = fakeApi(
      signedInAs(["projects.view", "projects.manage"], {
        "GET /api/v1/projects/p1": () => [200, project],
      }),
    );
    renderAt("/projects/p1/rules");
    const youngest = await screen.findByRole("spinbutton", { name: "Youngest speaker age" });
    const oldest = screen.getByRole("spinbutton", { name: "Oldest speaker age" });
    const save = screen.getByRole("button", { name: "Save rules" });
    await userEvent.clear(youngest);
    await userEvent.type(youngest, "61");
    expect(oldest).toHaveAccessibleDescription("Must be at least the youngest speaker age (61).");
    expect(oldest).toBeInvalid();
    expect(save).toBeDisabled();
    await userEvent.clear(youngest);
    await userEvent.type(youngest, "0");
    expect(youngest).toHaveAccessibleDescription("Type a whole number from 1 to 120.");
    expect(save).toBeDisabled();
    await userEvent.clear(youngest);
    await userEvent.type(youngest, "60");
    expect(save).toBeEnabled(); // one age is allowed: youngest = oldest
    await userEvent.clear(oldest);
    expect(oldest).toHaveAccessibleDescription("Type a whole number from 1 to 120.");
    expect(save).toBeDisabled();
    expect(calls.filter((c) => c.method === "PATCH")).toHaveLength(0);
  });

  it("edits the QC checklist and saves it with the rules (D-146)", async () => {
    const { calls } = fakeApi(
      signedInAs(["projects.view", "projects.manage"], {
        "GET /api/v1/projects/p1": () => [200, project],
        "PATCH /api/v1/projects/p1": (body) => [200, { ...project, ...(body as object) }],
      }),
    );
    renderAt("/projects/p1/rules/qc-checklist");
    const card = await screen.findByRole("region", { name: "QC checklist" });
    const first = within(card).getByRole("group", { name: "1. two_speakers" });
    const second = within(card).getByRole("group", { name: "2. echo_in_audio" });
    expect(within(first).getByLabelText("Question")).toHaveValue(
      "The conversation is between exactly two speakers",
    );
    expect(within(first).getByLabelText("Applies to")).toHaveValue("conversation");
    expect(within(first).getByLabelText("Fails when the answer is")).toHaveValue("no");
    expect(within(second).getByLabelText("Fails when the answer is")).toHaveValue("");
    expect(within(first).getByRole("button", { name: "Move two_speakers up" })).toBeDisabled();
    expect(within(second).getByRole("button", { name: "Move echo_in_audio down" })).toBeDisabled();

    // Change the words, when it fails, what it applies to and whether it is required.
    const words = within(first).getByLabelText("Question");
    await userEvent.clear(words);
    expect(screen.getByRole("button", { name: "Save rules" })).toBeDisabled();
    expect(words).toHaveAccessibleDescription("Write the question.");
    await userEvent.type(words, "Only two people talk");
    await userEvent.click(within(first).getByRole("checkbox", { name: /Required/ }));
    await userEvent.selectOptions(within(second).getByLabelText("Fails when the answer is"), "yes");
    await userEvent.selectOptions(within(second).getByLabelText("Applies to"), "conversation");
    await userEvent.click(within(second).getByRole("button", { name: "Move echo_in_audio up" }));
    expect(within(card).getByRole("group", { name: "1. echo_in_audio" })).toBeInTheDocument();

    // A new question needs a key in the client's form, used once.
    const key = within(card).getByLabelText("Key");
    await userEvent.type(key, "Two Speakers");
    await userEvent.type(within(card).getByLabelText("New question"), "Is music playing?");
    await userEvent.click(within(card).getByRole("button", { name: "Add question" }));
    expect(key).toHaveAccessibleDescription(/Lowercase letters, digits and _ only/);
    await userEvent.clear(key);
    await userEvent.type(key, "echo_in_audio");
    await userEvent.click(within(card).getByRole("button", { name: "Add question" }));
    expect(key).toHaveAccessibleDescription(/already in the list/);
    await userEvent.clear(key);
    await userEvent.type(key, "music{Enter}");
    expect(within(card).getByRole("group", { name: "3. music" })).toBeInTheDocument();
    expect(calls.filter((c) => c.method === "PATCH")).toHaveLength(0);

    await userEvent.click(screen.getByRole("button", { name: "Save rules" }));
    expect(await screen.findByText("Rules saved.")).toBeInTheDocument();
    const patches = () => calls.filter((c) => c.method === "PATCH");
    expect(patches()[0]?.body).toMatchObject({
      name: "Hindi conversations",
      speaker_min_age: 20,
      qc_checklist: [
        {
          key: "echo_in_audio",
          question: "Is echo present?",
          scope: "conversation",
          fails_on: "yes",
          required: true,
        },
        {
          key: "two_speakers",
          question: "Only two people talk",
          scope: "conversation",
          fails_on: "no",
          required: false,
        },
        {
          key: "music",
          question: "Is music playing?",
          scope: "conversation",
          fails_on: "no",
          required: true,
        },
      ],
    });

    // Remove one; then put the client's list back.
    await userEvent.click(within(card).getByRole("button", { name: "Remove music" }));
    expect(within(card).queryByRole("group", { name: "3. music" })).toBeNull();
    await userEvent.click(within(card).getByRole("button", { name: "Reset to the client's list" }));
    expect(within(card).getByText("28 questions (at most 60).")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Save rules" }));
    await waitFor(() => expect(patches()).toHaveLength(2));
    expect((patches()[1]?.body as { qc_checklist: unknown }).qc_checklist).toEqual(
      CLIENT_QC_CHECKLIST,
    );
  });

  it("asks the device details ticked on the Rules tab (D-147)", async () => {
    const { calls } = fakeApi(
      signedInAs(["projects.view", "projects.manage"], {
        "GET /api/v1/projects/p1": () => [200, project],
        "PATCH /api/v1/projects/p1": (body) => [200, { ...project, ...(body as object) }],
      }),
    );
    renderAt("/projects/p1/rules/devices");
    const card = await screen.findByRole("region", { name: "Device details" });
    const asked = within(card).getByRole("group", { name: "Asked for each speaker" });
    expect(
      within(asked)
        .getAllByRole("checkbox")
        .map((b) => [b.closest("label")?.textContent, (b as HTMLInputElement).checked]),
    ).toEqual([
      ["Device make", true],
      ["Device model", true],
      ["Bluetooth earphones used (Yes / No)", true],
      ["Wired earphones used (Yes / No)", true],
      ["Loudspeaker on (Yes / No)", true],
    ]);
    await userEvent.click(within(asked).getByRole("checkbox", { name: /^Wired earphones/ }));
    await userEvent.click(within(asked).getByRole("checkbox", { name: "Device model" }));
    await userEvent.click(screen.getByRole("button", { name: "Save rules" }));
    expect(await screen.findByText("Rules saved.")).toBeInTheDocument();
    const patches = () => calls.filter((c) => c.method === "PATCH");
    expect(patches()[0]?.body).toMatchObject({
      name: "Hindi conversations",
      device_fields: ["device_make", "bluetooth_earphones", "loudspeaker_on"],
      recording_reminders: CLIENT_REMINDERS, // the other cards go back as they are
    });
    // None at all is allowed, and said.
    for (const box of within(asked).getAllByRole("checkbox"))
      if ((box as HTMLInputElement).checked) await userEvent.click(box);
    expect(within(card).getByText(/no device details are asked/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Save rules" }));
    await waitFor(() => expect(patches()).toHaveLength(2));
    expect(patches()[1]?.body).toMatchObject({ device_fields: [] });
  });

  it(
    "edits the moderator's reminders and puts back the client's text (D-147)",
    { timeout: 15000 },
    async () => {
      const { calls } = fakeApi(
        signedInAs(["projects.view", "projects.manage"], {
          "GET /api/v1/projects/p1": () => [200, project],
          "PATCH /api/v1/projects/p1": (body) => [200, { ...project, ...(body as object) }],
        }),
      );
      renderAt("/projects/p1/rules/reminders");
      const card = await screen.findByRole("region", { name: "Reminders for moderators" });
      const topics = within(card).getByLabelText("Talk about");
      const avoid = within(card).getByLabelText("Avoid");
      const phone = within(card).getByLabelText("Phone call tips");
      const speakerId = within(card).getByRole("checkbox", {
        name: "Ask each speaker to start with their first name and speaker ID",
      });
      // One line per entry, as the project has them.
      expect(topics).toHaveValue(CLIENT_REMINDERS.topics.join("\n"));
      expect(within(card).getByLabelText("Face-to-face tips")).toHaveValue(
        CLIENT_REMINDERS.face_to_face.join("\n"),
      );
      expect(speakerId).toBeChecked();

      await userEvent.clear(topics);
      await userEvent.type(topics, "cricket{Enter}{Enter}  monsoon   farming");
      await userEvent.clear(phone);
      await userEvent.type(phone, "Use a headset");
      await userEvent.click(speakerId);
      // A line that is too long holds the save.
      await userEvent.click(avoid);
      await userEvent.keyboard("{Control>}{End}{/Control}");
      await userEvent.paste(`\n${"x".repeat(201)}`);
      expect(avoid).toHaveAccessibleDescription(/Line 7 is longer than 200 characters\./);
      expect(screen.getByRole("button", { name: "Save rules" })).toBeDisabled();
      await userEvent.type(avoid, "{Backspace}");
      expect(screen.getByRole("button", { name: "Save rules" })).toBeEnabled();
      expect(calls.filter((c) => c.method === "PATCH")).toHaveLength(0);

      await userEvent.click(screen.getByRole("button", { name: "Save rules" }));
      expect(await screen.findByText("Rules saved.")).toBeInTheDocument();
      const patches = () => calls.filter((c) => c.method === "PATCH");
      expect(patches()[0]?.body).toMatchObject({
        device_fields: project.device_fields,
        recording_reminders: {
          speaker_id: false,
          // Spaces tidied, empty lines dropped.
          topics: ["cricket", "monsoon farming"],
          avoid: [...CLIENT_REMINDERS.avoid, "x".repeat(200)],
          face_to_face: CLIENT_REMINDERS.face_to_face,
          telephony: ["Use a headset"],
        },
      });

      await userEvent.click(
        within(card).getByRole("button", { name: "Reset to the client's text" }),
      );
      expect(topics).toHaveValue(CLIENT_REMINDERS.topics.join("\n"));
      expect(speakerId).toBeChecked();
      await userEvent.click(screen.getByRole("button", { name: "Save rules" }));
      await waitFor(() => expect(patches()).toHaveLength(2));
      expect((patches()[1]?.body as { recording_reminders: unknown }).recording_reminders).toEqual(
        CLIENT_REMINDERS,
      );
    },
  );

  it("keeps the Rules for project administrators, like the other pages (D-104, D-145)", async () => {
    fakeApi(signedInAs(["projects.view"], { "GET /api/v1/projects/p1": () => [200, project] }));
    const router = renderAt("/projects/p1/rules");
    expect(await screen.findByText("No access")).toBeInTheDocument();
    expect(screen.queryByRole("navigation", { name: "Project sections" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Save rules" })).toBeNull();
    // A section's own address too (D-150).
    await act(() => router.navigate("/projects/p1/rules/consent"));
    expect(router.state.location.pathname).toBe("/projects/p1/rules/consent");
    expect(screen.getByText("No access")).toBeInTheDocument();
    expect(screen.queryByRole("group", { name: "How participants give consent" })).toBeNull();
  });

  it("keeps an archived project's rules read only (D-145)", async () => {
    fakeApi(
      signedInAs(["projects.view", "projects.manage"], {
        "GET /api/v1/projects/p1": () => [200, { ...project, status: "ARCHIVED" }],
      }),
    );
    renderAt("/projects/p1/rules");
    expect(
      await screen.findByText("Read only. Reopen the project to change its rules."),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("checkbox", { name: "Each pair of speakers only once" }),
    ).toBeDisabled();
    expect(screen.queryByRole("button", { name: "Save rules" })).toBeNull();
    // The QC checklist too (D-146).
    await userEvent.click(
      within(screen.getByRole("navigation", { name: "Project sections" })).getByRole("link", {
        name: "QC checklist",
      }),
    );
    const card = await screen.findByRole("region", { name: "QC checklist" });
    expect(screen.getByText("Read only. Reopen the project to change its rules.")).toBeVisible();
    expect(screen.queryByRole("button", { name: "Save rules" })).toBeNull();
    expect(within(card).getAllByLabelText("Question")[0]).toBeDisabled();
    expect(within(card).getByRole("button", { name: "Remove two_speakers" })).toBeDisabled();
    expect(within(card).getByRole("button", { name: "Add question" })).toBeDisabled();
  });

  it("pauses a project and makes it active again, archiving only with a reason", async () => {
    let current = { ...project, status: "ACTIVE", accepts_new_work: true };
    const { calls } = fakeApi(
      signedInAs(["projects.view", "projects.manage", "projects.members"], {
        "GET /api/v1/projects/p1": () => [200, current],
        "POST /api/v1/projects/p1/status": (body) => {
          const status = (body as { status: string }).status;
          if (!["PAUSED", "ACTIVE"].includes(status) || status === current.status)
            return [409, { error: { code: "INVALID_TRANSITION", message: "Cannot change" } }];
          current = { ...current, status, accepts_new_work: status === "ACTIVE" };
          return [200, current];
        },
      }),
    );
    renderAt("/projects/p1");
    const confirmIn = async (name: string) =>
      userEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name }));
    // Archiving an active project needs a reason in words.
    await userEvent.click(await screen.findByRole("button", { name: "Archive" }));
    expect(
      within(screen.getByRole("dialog")).getByRole("button", { name: "Archive" }),
    ).toBeDisabled();
    await userEvent.click(
      within(screen.getByRole("dialog")).getByRole("button", { name: "Go back" }),
    );
    // Active -> Paused.
    await userEvent.click(screen.getByRole("button", { name: "Pause" }));
    await confirmIn("Pause");
    expect(
      await screen.findByText("This project does not accept new work until it is active."),
    ).toBeInTheDocument();
    // A paused project offers Make active; one click and a confirmation send it.
    await userEvent.click(screen.getByRole("button", { name: "Make active" }));
    await confirmIn("Make active");
    expect(await screen.findByText("This project accepts new work.")).toBeInTheDocument();
    expect(calls.filter((c) => c.path === "/api/v1/projects/p1/status").map((c) => c.body)).toEqual(
      [
        { status: "PAUSED", reason: null },
        { status: "ACTIVE", reason: null },
      ],
    );
  });

  it("shows a read-only project to a member without manage rights", async () => {
    fakeApi(signedInAs(["projects.view"], { "GET /api/v1/projects/p1": () => [200, project] }));
    renderAt("/projects/p1");
    await screen.findByRole("heading", { name: "HINDI · Hindi conversations" });
    expect(await screen.findByLabelText(/^Name/)).toBeDisabled(); // the tab has loaded
    expect(screen.queryByRole("button", { name: "Make active" })).not.toBeInTheDocument();
  });

  it("renders each tab", async () => {
    fakeApi(
      signedInAs(["projects.view", "projects.manage", "projects.members"], {
        "GET /api/v1/projects/p1": () => [200, project],
        "GET /api/v1/projects/p1/members": () => [200, []],
      }),
    );
    renderAt("/projects/p1/team");
    expect(await screen.findByText("No members yet")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("link", { name: "Audio rules" }));
    expect(await screen.findByRole("group", { name: "Phone call" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("link", { name: "Languages" }));
    expect(await screen.findByText(/Hindi \(hi\), Awadhi/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Remove" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("link", { name: "Retention" }));
    expect(await screen.findByLabelText("Browser original captures")).toBeInTheDocument();
    // Each box shows a faded example under it, tied to the box for screen readers (D-086).
    expect(screen.getByLabelText("Consent recordings")).toHaveAccessibleDescription(
      "Example: 1825 (five years)",
    );
  });

  it("goes back to the project list with a note after creating a project", async () => {
    const created = { ...project, id: "p9", code: "PRJ0009", name: "Tamil talk" };
    const { calls } = fakeApi(
      signedInAs(["projects.view", "projects.create", "projects.manage"], {
        "POST /api/v1/projects": () => [201, created],
        "GET /api/v1/projects": () => [200, { items: [created], total: 1, page: 1, page_size: 25 }],
      }),
    );
    renderAt("/projects/new");
    await userEvent.type(await screen.findByLabelText(/^Name/), "Tamil talk");
    // The rules are set on the Rules tab once the project exists (D-145): the server's defaults.
    expect(screen.getByText(/Change them on the project.s/)).toHaveTextContent("Rules tab");
    expect(screen.queryByLabelText("Conversations per speaker (at most)")).toBeNull();
    expect(screen.queryByRole("radio", { name: /^Online/ })).toBeNull();
    expect(screen.queryByRole("checkbox", { name: /QC pass is the final approval/ })).toBeNull();
    await userEvent.click(screen.getByRole("button", { name: "Create project" }));
    expect(
      await screen.findByText(/^PRJ0009 Tamil talk created\. It starts as Draft/),
    ).toBeInTheDocument();
    const sent = calls.find((c) => c.method === "POST")?.body as Record<string, unknown>;
    expect(sent).toMatchObject({ name: "Tamil talk" });
    for (const rule of [
      "speaker_min_age",
      "required_speaker_details",
      "max_conversations_per_speaker",
      "unique_pairs",
      "consent_mode",
      "qc_final_approval",
    ])
      expect(sent).not.toHaveProperty(rule);
    expect(screen.getByRole("heading", { name: "Projects" })).toBeInTheDocument();
    expect(await screen.findByRole("link", { name: "PRJ0009" })).toHaveAttribute(
      "href",
      "/projects/p9",
    );
  });

  it("prepares a bundle with the chosen filters and follows it until it is ready (D-105)", async () => {
    const jobs: Record<string, unknown>[] = [];
    let looks = 0;
    const { calls } = fakeApi(
      signedInAs(["projects.view", "projects.manage", "exports.create"], {
        "GET /api/v1/projects/p1": () => [200, project],
        "GET /api/v1/projects/p1/export/summary": () => [200, SUMMARY],
        "GET /api/v1/projects/p1/exports": () => {
          // The first look after asking finds it being prepared, the next one ready.
          if (jobs[0]) jobs[0].state = ++looks === 1 ? "RUNNING" : "READY";
          return [200, { items: jobs, total: jobs.length, page: 1, page_size: 20 }];
        },
        "POST /api/v1/projects/p1/exports": (body) => {
          const choice = body as Record<string, unknown>;
          jobs.unshift({ ...JOB, ...choice, filters: choice, state: "QUEUED" });
          return [202, jobs[0]];
        },
        "POST /api/v1/projects/p1/exports/x1/download-link": () => [
          200,
          { url: "#bundle", valid_seconds: 300, file_name: JOB.file_name, sha256: JOB.sha256 },
        ],
        "DELETE /api/v1/projects/p1/exports/x1": () => {
          jobs.length = 0;
          return [200, { ...JOB, state: "EXPIRED" }];
        },
      }),
    );
    renderAt("/projects/p1/export");
    expect(await screen.findByText("3 recordings")).toBeInTheDocument();
    expect(screen.getByText(/2 face-to-face, 1 phone call · about 240 MB of audio/)).toBeVisible();
    expect(await screen.findByText(/No export has been prepared yet/)).toBeInTheDocument();

    await userEvent.click(screen.getByRole("radio", { name: /Audio only/ }));
    await userEvent.selectOptions(screen.getByLabelText("Which recordings"), "finished");
    await userEvent.selectOptions(screen.getByLabelText("Recording type"), "TELEPHONY");
    await userEvent.selectOptions(screen.getByLabelText("Language"), "hi");
    await userEvent.selectOptions(screen.getByLabelText("Tables as"), "tsv");
    await userEvent.click(screen.getByRole("checkbox", { name: /original recordings/ }));
    // The count follows the choice.
    await waitFor(() =>
      expect(
        calls.some((c) =>
          c.path.includes("content=audio&scope=finished&mode=TELEPHONY&language=hi&originals=true"),
        ),
      ).toBe(true),
    );
    await userEvent.click(await screen.findByRole("button", { name: "Prepare export" }));
    await waitFor(() =>
      expect(
        calls.find((c) => c.path === "/api/v1/projects/p1/exports" && c.method === "POST")?.body,
      ).toEqual({
        content: "audio",
        scope: "finished",
        table_format: "tsv",
        mode: "TELEPHONY",
        language: "hi",
        recorded_from: null,
        recorded_to: null,
        originals: true,
        contact: false,
      }),
    );
    const list = await screen.findByRole("table", { name: "Prepared exports" });
    expect(await within(list).findByText("Being prepared")).toBeInTheDocument();
    expect(list).toHaveTextContent(
      "Audio only · every finished recording · Phone call · Hindi (hi) · with originals · TSV",
    );
    expect(within(list).queryByRole("button", { name: /Download/ })).not.toBeInTheDocument();
    // It is looked at again by itself until it is ready.
    expect(await within(list).findByText("Ready", {}, { timeout: 8000 })).toBeInTheDocument();
    expect(list).toHaveTextContent("about 240 MB");

    await userEvent.click(within(list).getByRole("button", { name: `Download ${JOB.file_name}` }));
    expect(
      await screen.findByText(`Downloading ${JOB.file_name}. The link works for 5 minutes.`),
    ).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: `Remove ${JOB.file_name}` }));
    await userEvent.click(
      within(screen.getByRole("dialog")).getByRole("button", { name: "Remove" }),
    );
    expect(await screen.findByText(`${JOB.file_name} removed.`)).toBeInTheDocument();
    expect(await screen.findByText(/No export has been prepared yet/)).toBeInTheDocument();
  }, 20000);

  it("gives reports as CSV or TSV, and says why an export failed or cannot be asked for", async () => {
    fakeApi(
      signedInAs(["projects.view", "projects.manage", "exports.create"], {
        "GET /api/v1/projects/p1": () => [200, project],
        "GET /api/v1/projects/p1/export/summary": (_b, url) => [
          200,
          url.searchParams.get("mode") === "FACE_TO_FACE"
            ? { ...SUMMARY, recordings: 0, face_to_face: 0, telephony: 0, audio_bytes: 0 }
            : SUMMARY,
        ],
        "GET /api/v1/projects/p1/exports": () => [
          200,
          {
            items: [
              {
                ...JOB,
                state: "FAILED",
                error: "A stored file of T000004 does not match its checksum: export stopped",
              },
            ],
            total: 1,
            page: 1,
            page_size: 20,
          },
        ],
      }),
    );
    renderAt("/projects/p1/export");
    expect(await screen.findByRole("link", { name: "Progress report as CSV" })).toHaveAttribute(
      "href",
      "/api/v1/projects/p1/export?content=progress&format=csv",
    );
    expect(screen.getByRole("link", { name: "Participant minutes as TSV" })).toHaveAttribute(
      "href",
      "/api/v1/projects/p1/export?content=participants&format=tsv",
    );
    // A failed export says why, and has nothing to download.
    const list = await screen.findByRole("table", { name: "Prepared exports" });
    expect(list).toHaveTextContent("Failed");
    expect(list).toHaveTextContent("A stored file of T000004 does not match its checksum");
    expect(within(list).queryByRole("button", { name: /Download|Remove/ })).toBeNull();
    // Personal data is offered only to people who may export it.
    expect(screen.getByRole("checkbox", { name: /original recordings/ })).toBeInTheDocument();
    expect(screen.queryByRole("checkbox", { name: /phone numbers/ })).not.toBeInTheDocument();
    // Nothing fits: said in words, and nothing to prepare.
    await userEvent.selectOptions(screen.getByLabelText("Recording type"), "FACE_TO_FACE");
    expect(await screen.findByText(/Nothing to export/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Prepare export" })).toBeDisabled();
    // Days the wrong way round are caught before anything is asked.
    await userEvent.selectOptions(screen.getByLabelText("Recording type"), "");
    await userEvent.type(screen.getByLabelText("Recorded from"), "2026-11-10");
    await userEvent.type(screen.getByLabelText("Recorded to"), "2026-11-01");
    expect(await screen.findByText("Must not be before the first day")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Prepare export" })).toBeDisabled();
  });

  it("has a Tasks tab listing every task of the project (D-117)", async () => {
    const task = {
      id: "t1",
      task_code: "T000001",
      project_id: "p1",
      recording_mode: "TELEPHONY",
      status: "ASSIGNED",
      priority: "HIGH",
      due_at: null,
    };
    const { calls } = fakeApi(
      signedInAs(["projects.view", "projects.manage", "tasks.view", "tasks.assign"], {
        "GET /api/v1/projects/p1": () => [200, project],
        "GET /api/v1/tasks": () => [200, { items: [task], total: 1, page: 1, page_size: 25 }],
      }),
    );
    renderAt("/projects/p1");
    const tabs = await screen.findByRole("navigation", { name: "Project sections" });
    await userEvent.click(within(tabs).getByRole("link", { name: "Tasks" }));
    expect(await screen.findByRole("link", { name: "T000001" })).toBeInTheDocument();
    expect(screen.getByText("1 task in this project")).toBeInTheDocument();
    // Fixed to this project: no project choice, no project column.
    expect(screen.queryByLabelText("Project")).not.toBeInTheDocument();
    expect(screen.queryByRole("columnheader", { name: "Project" })).not.toBeInTheDocument();
    expect(calls.find((c) => c.path.startsWith("/api/v1/tasks?"))?.path).toContain("project_id=p1");
    expect(screen.getByRole("link", { name: "New task" })).toHaveAttribute(
      "href",
      "/tasks/new?project=p1",
    );
  });
});
