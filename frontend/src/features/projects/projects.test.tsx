// Requirements: PROJ-001, PROJ-002, PROJ-008, PROJ-009, PROJ-010, PROJ-011, PROJ-012, PROJ-013, ROLE-011, USER-003, PART-006, AQC-008
import { act, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { SPEAKER_FIELDS } from "../../lib/speakers";
import { fakeApi, renderAt, signedInAs, type Handler } from "../../test/fakeApi";
import { PARTICIPANT, PROGRESS, PROJECT, worldHandlers } from "../../test/world";
import { CLIENT_QC_CHECKLIST } from "./qcChecklist";
import { CLIENT_REMINDERS } from "./reminders";

afterEach(() => vi.unstubAllGlobals());

/** The project's GET and PATCH as the server answers them: what a save keeps is what the next read
 * gives, with a newer `updated_at`. */
function projectApi(start: Record<string, unknown>): Record<string, Handler> {
  let current = { ...start };
  let saves = 0;
  return {
    "GET /api/v1/projects/p1": () => [200, current],
    "PATCH /api/v1/projects/p1": (body) => {
      const fields = { ...(body as Record<string, unknown>) };
      delete fields.expected_updated_at;
      saves += 1;
      current = { ...current, ...fields, updated_at: `2026-11-21T10:00:0${saves}Z` };
      return [200, current];
    },
  };
}

const MANAGER = ["projects.view", "projects.manage"];
const sections = () => screen.getByRole("navigation", { name: "Project sections" });
const patches = (calls: { method: string; body: unknown }[]) =>
  calls.filter((c) => c.method === "PATCH").map((c) => c.body as Record<string, unknown>);

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
  updated_at: "2026-11-20T10:00:00Z",
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
        // The version read just before saving: the server refuses a save over a newer one.
        expected_updated_at: "2026-11-20T10:00:00Z",
      }),
    );
  });

  it("loads the rules one section at a time and saves each with the rest as it is (D-145, D-150)", async () => {
    const { calls } = fakeApi(
      signedInAs(["projects.view", "projects.manage"], projectApi(project)),
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
      signedInAs(["projects.view", "projects.manage"], projectApi(project)),
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

    // Remove one; then put the default list back.
    await userEvent.click(within(card).getByRole("button", { name: "Remove music" }));
    expect(within(card).queryByRole("group", { name: "3. music" })).toBeNull();
    await userEvent.click(within(card).getByRole("button", { name: "Reset to the default list" }));
    expect(within(card).getByText("28 questions (at most 60).")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Save rules" }));
    await waitFor(() => expect(patches()).toHaveLength(2));
    expect((patches()[1]?.body as { qc_checklist: unknown }).qc_checklist).toEqual(
      CLIENT_QC_CHECKLIST,
    );
  });

  it("asks the device details ticked on the Rules tab (D-147)", async () => {
    const { calls } = fakeApi(
      signedInAs(["projects.view", "projects.manage"], projectApi(project)),
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
    "edits the moderator's reminders and puts back the default text (D-147)",
    { timeout: 15000 },
    async () => {
      const { calls } = fakeApi(
        signedInAs(["projects.view", "projects.manage"], projectApi(project)),
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
        within(card).getByRole("button", { name: "Reset to the default text" }),
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

  it("shows a member without manage rights the project in a few words, not a settings form", async () => {
    fakeApi(
      signedInAs(["projects.view"], {
        "GET /api/v1/projects/p1": () => [
          200,
          { ...project, description: "Everyday talk in Hindi.\nTwo speakers each time." },
        ],
      }),
    );
    renderAt("/projects/p1");
    await screen.findByRole("heading", { name: "HINDI · Hindi conversations" });
    const about = await screen.findByRole("region", { name: "About this project" });
    const facts = within(about)
      .getAllByRole("term")
      .map((term) => [term.textContent, term.nextElementSibling?.textContent]);
    expect(facts).toEqual([
      ["Name", "Hindi conversations"],
      ["Description", "Everyday talk in Hindi.\nTwo speakers each time."],
      ["Recording type", "Phone call"],
      ["Daily target", "10 h a day"],
      ["New work", "This project does not accept new work until it is active."],
    ]);
    // Nothing to fill in, and nothing internal: who sees phone numbers, the consent policy.
    expect(screen.queryByRole("textbox")).toBeNull();
    expect(screen.queryByText(/phone numbers/i)).toBeNull();
    expect(screen.queryByText(/Consent policy/i)).toBeNull();
    expect(screen.queryByRole("button", { name: "Make active" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Save project" })).toBeNull();
  });

  it("says so when a member's project has no description and no daily target", async () => {
    fakeApi(
      signedInAs(["projects.view"], {
        "GET /api/v1/projects/p1": () => [
          200,
          { ...project, target_telephony_hours_per_day: "0.00", accepts_new_work: true },
        ],
      }),
    );
    renderAt("/projects/p1");
    const about = await screen.findByRole("region", { name: "About this project" });
    expect(about).toHaveTextContent("DescriptionNo description");
    expect(about).toHaveTextContent("Daily targetNo daily target");
    expect(about).toHaveTextContent("New workThis project accepts new work.");
  });

  it("renders each tab", async () => {
    fakeApi(
      signedInAs(["projects.view", "projects.manage", "projects.members"], {
        "GET /api/v1/projects/p1": () => [200, project],
        "GET /api/v1/projects/p1/members": () => [200, []],
      }),
    );
    renderAt("/projects/p1/team");
    // Each list is a titled section (D-158).
    const members = await screen.findByRole("region", { name: "Members" });
    expect(await within(members).findByText("No members yet")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("link", { name: "Audio rules" }));
    expect(await screen.findByRole("group", { name: "Phone call" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("link", { name: "Languages" }));
    expect(await screen.findByRole("row", { name: /Hindi \(hi\) Awadhi/ })).toBeInTheDocument();
    const languages = screen.getByRole("region", { name: "Project languages" });
    // Removed with the bin like every row, under "Actions" (D-158).
    expect(within(languages).getByRole("columnheader", { name: "Actions" })).toBeInTheDocument();
    expect(
      within(languages).getByRole("button", { name: "Remove Hindi (hi), Awadhi" }),
    ).toHaveClass("icon-button");
    await userEvent.click(screen.getByRole("link", { name: "Retention" }));
    expect(await screen.findByLabelText("Browser original captures")).toBeInTheDocument();
    // Each box shows a faded example under it, tied to the box for screen readers (D-086).
    expect(screen.getByLabelText("Phone call 16 kHz WAV")).toHaveAccessibleDescription(
      "Example: 365 (one year)",
    );
  });

  it("keeps only the kinds a rule can delete, and says the deletion is automatic (PROJ-01)", async () => {
    const { calls } = fakeApi(
      signedInAs(MANAGER, {
        // A rule saved before for a kind no rule can delete is not shown, and not sent back.
        "GET /api/v1/projects/p1": () => [
          200,
          {
            ...project,
            retention_rules: [
              { asset_kind: "BROWSER_ORIGINAL", retain_days: 90 },
              { asset_kind: "EXPORT_PACKAGE", retain_days: 30 },
            ],
          },
        ],
        "PUT /api/v1/projects/p1/retention": (body) => [
          200,
          { ...project, retention_rules: (body as { rules: unknown[] }).rules },
        ],
      }),
    );
    renderAt("/projects/p1/retention");
    const form = await screen.findByRole("form", { name: "Days to keep files" });
    expect(within(form).getAllByRole("spinbutton")).toHaveLength(4);
    for (const kind of [
      "Browser original captures",
      "Face-to-face 16 kHz WAV",
      "Phone system mixed recordings",
      "Phone call 16 kHz WAV",
    ])
      expect(within(form).getByRole("spinbutton", { name: kind })).toBeInTheDocument();
    expect(form).toHaveTextContent(/An automatic job deletes a file permanently/);
    expect(form).toHaveTextContent(/Only the files of closed tasks/);
    expect(within(form).queryByLabelText(/Export packages/)).toBeNull();
    expect(screen.getByLabelText("Browser original captures")).toHaveValue(90);
    // 0 days is not a rule: said, and nothing is sent.
    await userEvent.type(screen.getByLabelText("Phone call 16 kHz WAV"), "0");
    expect(screen.getByLabelText("Phone call 16 kHz WAV")).toHaveAccessibleDescription(
      /Type a whole number of days, 1 or more, or leave it empty\./,
    );
    expect(screen.getByRole("button", { name: "Save retention" })).toBeDisabled();
    await userEvent.clear(screen.getByLabelText("Phone call 16 kHz WAV"));
    await userEvent.type(screen.getByLabelText("Phone call 16 kHz WAV"), "365");
    await userEvent.click(screen.getByRole("button", { name: "Save retention" }));
    expect(await screen.findByText("Retention saved.")).toBeInTheDocument();
    expect(calls.find((c) => c.method === "PUT")?.body).toEqual({
      rules: [
        { asset_kind: "BROWSER_ORIGINAL", retain_days: 90 },
        { asset_kind: "TELEPHONY_DERIVED_PCM", retain_days: 365 },
      ],
    });
  });

  it("asks before removing a team member to reassign their open tasks first (PROJ-06)", async () => {
    fakeApi(
      signedInAs([...MANAGER, "projects.members"], {
        "GET /api/v1/projects/p1": () => [200, project],
        "GET /api/v1/projects/p1/members": () => [
          200,
          [
            {
              user_id: "m1",
              email: "mona@example.org",
              display_name: "Mona Moderator",
              roles: ["MODERATOR"],
              status: "ACTIVE",
              added_at: "2026-11-09T00:00:00Z",
            },
          ],
        ],
        "DELETE /api/v1/projects/p1/members/m1": () => [
          409,
          {
            error: {
              code: "MEMBER_HAS_OPEN_TASKS",
              message: "Mona Moderator still has 1 open task in this project (T000001).",
            },
          },
        ],
      }),
    );
    renderAt("/projects/p1/team");
    // The members in a titled section, removed with the bin under "Actions" (D-158).
    const members = await screen.findByRole("table", { name: "Members" });
    expect(within(members).getByRole("columnheader", { name: "Actions" })).toBeInTheDocument();
    await userEvent.click(within(members).getByRole("button", { name: "Remove Mona Moderator" }));
    const dialog = screen.getByRole("dialog", { name: "Remove Mona Moderator from HINDI?" });
    expect(dialog).toHaveTextContent(/must have those tasks reassigned first/);
    await userEvent.click(within(dialog).getByRole("button", { name: "Remove" }));
    // The server's refusal is said in the window, which stays open.
    expect(await within(dialog).findByText(/still has 1 open task/)).toBeInTheDocument();
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
    // One recording type, chosen by the admin (D-153): nothing is sent until it is.
    const type = screen.getByRole("group", { name: /Recording type/ });
    expect(
      within(type)
        .getAllByRole("radio")
        .map((r) => (r as HTMLInputElement).checked),
    ).toEqual([false, false]);
    await userEvent.click(screen.getByRole("button", { name: "Create project" }));
    expect(
      within(type).getByText("Choose one recording type: face-to-face or phone call."),
    ).toBeInTheDocument();
    expect(calls.filter((c) => c.method === "POST")).toHaveLength(0);
    await userEvent.click(within(type).getByRole("radio", { name: "Face-to-face" }));
    const hours = screen.getByLabelText("Face-to-face target (hours per day)");
    await userEvent.clear(hours);
    await userEvent.type(hours, "4");
    await userEvent.click(screen.getByRole("button", { name: "Create project" }));
    expect(
      await screen.findByText(/^PRJ0009 Tamil talk created\. It starts as Draft/),
    ).toBeInTheDocument();
    const sent = calls.find((c) => c.method === "POST")?.body as Record<string, unknown>;
    expect(sent).toMatchObject({
      name: "Tamil talk",
      allows_face_to_face: true,
      allows_telephony: false,
      target_face_to_face_hours_per_day: "4",
      target_telephony_hours_per_day: "0",
    });
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
    // Both on the project's title row (D-158): the count under the title, New task on the right.
    const titleRow = screen
      .getByRole("heading", { level: 1, name: "Tasks" })
      .closest(".page-header") as HTMLElement;
    expect(within(titleRow).getByText("1 task in this project")).toBeInTheDocument();
    expect(within(titleRow).getByRole("link", { name: "New task" })).toBeInTheDocument();
  });
});

describe("one recording type per project (D-153)", () => {
  // A project made before D-153 that allows both types.
  const legacy = {
    ...project,
    allows_face_to_face: true,
    target_face_to_face_hours_per_day: "5.00",
  };

  it("asks a project that allows both to choose one on its next save", async () => {
    const { calls } = fakeApi(
      signedInAs(["projects.view", "projects.manage"], {
        "GET /api/v1/projects/p1": () => [200, legacy],
        "PATCH /api/v1/projects/p1": (body) => [200, { ...legacy, ...(body as object) }],
      }),
    );
    renderAt("/projects/p1");
    expect(
      await screen.findByText(
        "This project allows both types. Choose one: from now on a project records one type.",
      ),
    ).toBeInTheDocument();
    const type = screen.getByRole("group", { name: /Recording type/ });
    expect(within(type).getByRole("radio", { name: "Face-to-face" })).not.toBeChecked();
    expect(within(type).getByRole("radio", { name: "Phone call" })).not.toBeChecked();
    await userEvent.click(screen.getByRole("button", { name: "Save project" }));
    expect(type).toHaveAccessibleDescription(
      /A project records one type\. For the other, make another project\. Choose one recording type/,
    );
    expect(calls.filter((c) => c.method === "PATCH")).toHaveLength(0);
    // Phone call: its daily target stays, the face-to-face one goes.
    await userEvent.click(within(type).getByRole("radio", { name: "Phone call" }));
    expect(screen.getByLabelText("Phone call target (hours per day)")).toHaveValue(10);
    expect(screen.queryByLabelText("Face-to-face target (hours per day)")).toBeNull();
    await userEvent.click(screen.getByRole("button", { name: "Save project" }));
    await waitFor(() =>
      expect(calls.find((c) => c.method === "PATCH")?.body).toMatchObject({
        allows_telephony: true,
        allows_face_to_face: false,
        target_telephony_hours_per_day: "10.00",
        target_face_to_face_hours_per_day: "0",
      }),
    );
  });

  it("shows a one-type project's type chosen, and no split by type among the targets", async () => {
    fakeApi(
      signedInAs(["projects.view", "projects.manage"], {
        "GET /api/v1/projects/p1": () => [200, project],
      }),
    );
    renderAt("/projects/p1");
    const type = await screen.findByRole("group", { name: /Recording type/ });
    expect(within(type).getByRole("radio", { name: "Phone call" })).toBeChecked();
    expect(screen.queryByText(/This project allows both types/)).toBeNull();
    await userEvent.click(screen.getByRole("link", { name: "Rules" }));
    await userEvent.click(await screen.findByRole("link", { name: "Targets" }));
    const targets = await screen.findByRole("region", { name: "Targets" });
    expect(within(targets).getByRole("spinbutton", { name: "Male (%)" })).toBeInTheDocument();
    expect(within(targets).queryByRole("spinbutton", { name: "Face-to-face (%)" })).toBeNull();
  });

  it("names each project's type in the list", async () => {
    const face = {
      ...project,
      id: "p2",
      code: "FACE",
      allows_telephony: false,
      allows_face_to_face: true,
    };
    fakeApi(
      signedInAs(["projects.view"], {
        "GET /api/v1/projects": () => [
          200,
          {
            items: [project, face, { ...legacy, id: "p3", code: "OLD" }],
            total: 3,
            page: 1,
            page_size: 25,
          },
        ],
      }),
    );
    renderAt("/projects");
    const table = await screen.findByRole("table");
    expect(within(table).getByRole("columnheader", { name: "Recording type" })).toBeInTheDocument();
    const typeOf = (code: string) =>
      within(table).getByRole("link", { name: code }).closest("tr")?.cells[3]?.textContent;
    expect([typeOf("HINDI"), typeOf("FACE"), typeOf("OLD")]).toEqual([
      "Phone call",
      "Face-to-face",
      "Phone call, Face-to-face",
    ]);
  });
});

describe("saving one part of the project (FEA-02, PROJ-03)", () => {
  /** The project as this page read it first; every later read gives it as another tab saved it. */
  function changedElsewhere(change: Record<string, unknown>) {
    let reads = 0;
    const later = { ...project, ...change, updated_at: "2026-11-21T09:00:00Z" };
    return fakeApi(
      signedInAs(MANAGER, {
        "GET /api/v1/projects/p1": () => [200, ++reads === 1 ? project : later],
        "PATCH /api/v1/projects/p1": (body) => [200, { ...later, ...(body as object) }],
      }),
    );
  }

  it("keeps what another tab saved when the Targets are saved", async () => {
    const { calls } = changedElsewhere({ speaker_min_age: 25, consent_mode: "UPLOAD" });
    renderAt("/projects/p1/rules/targets");
    await userEvent.type(await screen.findByRole("spinbutton", { name: "Hours completed" }), "800");
    await userEvent.click(screen.getByRole("button", { name: "Save rules" }));
    expect(await screen.findByText("Rules saved.")).toBeInTheDocument();
    expect(patches(calls)).toHaveLength(1);
    expect(patches(calls)[0]).toMatchObject({
      target_hours: "800", // this section's own field, as typed
      speaker_min_age: 25, // another section's, as saved in the other tab
      consent_mode: "UPLOAD",
      name: "Hindi conversations",
      expected_updated_at: "2026-11-21T09:00:00Z", // the version read just before saving
    });
  });

  it("keeps what another tab saved when the Overview is saved", async () => {
    const { calls } = changedElsewhere({ speaker_min_age: 25, consent_mode: "UPLOAD" });
    renderAt("/projects/p1");
    await userEvent.type(await screen.findByLabelText("Description"), "Daily talk.");
    await userEvent.click(screen.getByRole("button", { name: "Save project" }));
    expect(await screen.findByText("Saved.")).toBeInTheDocument();
    expect(patches(calls)).toHaveLength(1);
    expect(patches(calls)[0]).toMatchObject({
      description: "Daily talk.",
      speaker_min_age: 25,
      consent_mode: "UPLOAD",
      expected_updated_at: "2026-11-21T09:00:00Z",
    });
  });

  it("says so, and sends nothing, when the same rules were changed meanwhile", async () => {
    const { calls } = changedElsewhere({ target_speakers: 800 });
    renderAt("/projects/p1/rules/targets");
    const speakers = await screen.findByRole("spinbutton", { name: "Speakers" });
    await userEvent.clear(speakers);
    await userEvent.type(speakers, "600");
    await userEvent.click(screen.getByRole("button", { name: "Save rules" }));
    expect(
      await screen.findByText(
        "Someone else saved this project after you opened it. Reload the page to see their changes, then save again.",
      ),
    ).toBeInTheDocument();
    expect(patches(calls)).toHaveLength(0);
    expect(speakers).toHaveValue(600); // what was typed stays
  });

  it("says so on the Overview too, when its settings were changed meanwhile", async () => {
    const { calls } = changedElsewhere({ consent_text: "A newer consent form." });
    renderAt("/projects/p1");
    await userEvent.type(await screen.findByLabelText("Description"), "Daily talk.");
    await userEvent.click(screen.getByRole("button", { name: "Save project" }));
    expect(
      await screen.findByText(/^Someone else saved this project after you opened it/),
    ).toBeVisible();
    expect(patches(calls)).toHaveLength(0);
    expect(screen.getByLabelText("Description")).toHaveValue("Daily talk.");
  });
});

describe("changes not saved yet (FEA-04)", () => {
  const leave = () => screen.findByRole("dialog", { name: "Leave without saving?" });

  it("asks before a Rules section is left: Stay keeps the change, Leave drops it", async () => {
    const { calls } = fakeApi(signedInAs(MANAGER, projectApi(project)));
    const router = renderAt("/projects/p1/rules/speakers");
    const youngest = await screen.findByRole("spinbutton", { name: "Youngest speaker age" });
    await userEvent.clear(youngest);
    await userEvent.type(youngest, "33");
    await userEvent.click(within(sections()).getByRole("link", { name: "Consent" }));
    const ask = await leave();
    expect(ask).toHaveTextContent("Your changes on this page are not saved.");
    await userEvent.click(within(ask).getByRole("button", { name: "Stay" }));
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(router.state.location.pathname).toBe("/projects/p1/rules/speakers");
    expect(youngest).toHaveValue(33);

    await userEvent.click(within(sections()).getByRole("link", { name: "Consent" }));
    await userEvent.click(within(await leave()).getByRole("button", { name: "Leave" }));
    expect(
      await screen.findByRole("group", { name: "How participants give consent" }),
    ).toBeInTheDocument();
    expect(router.state.location.pathname).toBe("/projects/p1/rules/consent");
    await userEvent.click(within(sections()).getByRole("link", { name: "Speakers" }));
    expect(await screen.findByRole("spinbutton", { name: "Youngest speaker age" })).toHaveValue(20);
    expect(patches(calls)).toHaveLength(0);
  });

  it("does not ask once the changes are saved", async () => {
    const { calls } = fakeApi(signedInAs(MANAGER, projectApi(project)));
    const router = renderAt("/projects/p1/rules/speakers");
    const youngest = await screen.findByRole("spinbutton", { name: "Youngest speaker age" });
    await userEvent.clear(youngest);
    await userEvent.type(youngest, "33");
    await userEvent.click(screen.getByRole("button", { name: "Save rules" }));
    expect(await screen.findByText("Rules saved.")).toBeInTheDocument();
    await userEvent.click(within(sections()).getByRole("link", { name: "Consent" }));
    expect(
      await screen.findByRole("group", { name: "How participants give consent" }),
    ).toBeInTheDocument();
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(router.state.location.pathname).toBe("/projects/p1/rules/consent");
    expect(patches(calls)[0]).toMatchObject({ speaker_min_age: 33 });
  });

  it("keeps what is typed on the Overview through a status change, and asks before it is left", async () => {
    let current = { ...project, status: "ACTIVE", accepts_new_work: true };
    fakeApi(
      signedInAs(MANAGER, {
        "GET /api/v1/projects/p1": () => [200, current],
        "POST /api/v1/projects/p1/status": (body) => {
          current = { ...current, status: (body as { status: string }).status };
          return [200, current];
        },
      }),
    );
    const router = renderAt("/projects/p1");
    await userEvent.type(await screen.findByLabelText("Description"), "Still typing");
    await userEvent.click(screen.getByRole("button", { name: "Pause" }));
    await userEvent.click(
      within(screen.getByRole("dialog")).getByRole("button", { name: "Pause" }),
    );
    expect(await screen.findByText("Status changed to Paused.")).toBeInTheDocument();
    expect(screen.getByLabelText("Description")).toHaveValue("Still typing");

    await userEvent.click(within(sections()).getByRole("link", { name: "Audio rules" }));
    await userEvent.click(within(await leave()).getByRole("button", { name: "Leave" }));
    expect(await screen.findByRole("group", { name: "Phone call" })).toBeInTheDocument();
    expect(router.state.location.pathname).toBe("/projects/p1/audio");
  });

  it("asks before the audio rules and the retention are left with changes", async () => {
    fakeApi(signedInAs(MANAGER, { "GET /api/v1/projects/p1": () => [200, project] }));
    const router = renderAt("/projects/p1/audio");
    const rate = await screen.findByLabelText("Sample rate (Hz)");
    await userEvent.clear(rate);
    await userEvent.type(rate, "8000");
    await userEvent.click(within(sections()).getByRole("link", { name: "Retention" }));
    await userEvent.click(within(await leave()).getByRole("button", { name: "Stay" }));
    expect(router.state.location.pathname).toBe("/projects/p1/audio");
    // Back to what is saved: nothing to ask.
    await userEvent.clear(rate);
    await userEvent.type(rate, "16000");
    await userEvent.click(within(sections()).getByRole("link", { name: "Retention" }));
    const days = await screen.findByLabelText("Face-to-face 16 kHz WAV");
    expect(router.state.location.pathname).toBe("/projects/p1/retention");
    await userEvent.type(days, "30");
    await userEvent.click(within(sections()).getByRole("link", { name: "Languages" }));
    expect(await leave()).toBeInTheDocument();
  });
});

describe("one look on every page (D-158)", () => {
  /** The title bar a button sits on, as its text. */
  const barOf = (button: HTMLElement) => button.closest(".card__head")?.textContent;

  it("has each settings form's Save on its section's title bar", async () => {
    fakeApi(signedInAs(MANAGER, { "GET /api/v1/projects/p1": () => [200, project] }));
    renderAt("/projects/p1");
    expect(barOf(await screen.findByRole("button", { name: "Save project" }))).toBe(
      "Project detailsSave project",
    );
    await userEvent.click(within(sections()).getByRole("link", { name: "Audio rules" }));
    // A project of one recording type: the section is titled with it.
    expect(barOf(await screen.findByRole("button", { name: "Save audio rules" }))).toBe(
      "Phone callSave audio rules",
    );
    await userEvent.click(within(sections()).getByRole("link", { name: "Retention" }));
    // A short title, so the bar stays one row on a phone (D-159).
    expect(barOf(await screen.findByRole("button", { name: "Save retention" }))).toBe(
      "Days to keep filesSave retention",
    );
  });

  it("gives a project made with both recording types one Save for both", async () => {
    const both = {
      ...project,
      allows_face_to_face: true,
      audio_rules: [{ ...project.audio_rules[0], mode: "FACE_TO_FACE" }, ...project.audio_rules],
    };
    fakeApi(signedInAs(MANAGER, { "GET /api/v1/projects/p1": () => [200, both] }));
    renderAt("/projects/p1/audio");
    const save = await screen.findByRole("button", { name: "Save audio rules" });
    expect(barOf(save)).toBe("Face-to-face and phone callSave audio rules");
    expect(screen.getAllByRole("button", { name: "Save audio rules" })).toHaveLength(1);
    // Each type a part of the section, its boxes named by it.
    for (const type of ["Face-to-face", "Phone call"])
      expect(
        within(screen.getByRole("group", { name: type })).getByLabelText("Sample rate (Hz)"),
      ).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 3, name: "Phone call" })).toHaveClass("subhead");
  });
});

describe("an archived project (PROJ-05)", () => {
  it("keeps its settings, audio rules, languages and retention read only until it is reopened", async () => {
    const { calls } = fakeApi(
      signedInAs([...MANAGER, "projects.members"], {
        "GET /api/v1/projects/p1": () => [200, { ...project, status: "ARCHIVED" }],
      }),
    );
    renderAt("/projects/p1");
    const note = "Read only. Reopen the project to change it.";
    // The Overview says why, not that only an administrator could change it.
    expect(await screen.findByText(note)).toBeInTheDocument();
    expect(screen.queryByText(/Only a project administrator/)).toBeNull();
    expect(screen.getByLabelText(/^Name/)).toBeDisabled();
    expect(screen.queryByRole("button", { name: "Save project" })).toBeNull();

    await userEvent.click(within(sections()).getByRole("link", { name: "Audio rules" }));
    expect(await screen.findByLabelText("Sample rate (Hz)")).toBeDisabled();
    expect(screen.getByText(note)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Save audio rules" })).toBeNull();

    await userEvent.click(within(sections()).getByRole("link", { name: "Languages" }));
    expect(await screen.findByRole("row", { name: /Hindi \(hi\) Awadhi/ })).toBeInTheDocument();
    expect(screen.getByText(note)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^Remove/ })).toBeNull();
    expect(screen.queryByRole("columnheader", { name: "Actions" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Add language" })).toBeNull();

    await userEvent.click(within(sections()).getByRole("link", { name: "Retention" }));
    expect(await screen.findByLabelText("Browser original captures")).toBeDisabled();
    expect(screen.getByText(note)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Save retention" })).toBeNull();
    expect(calls.filter((c) => c.method !== "GET")).toHaveLength(0);
  });
});

describe("rules and settings in words", () => {
  it("warns that uploaded forms stop counting when consent goes back to online (PROJ-02)", async () => {
    fakeApi(signedInAs(MANAGER, projectApi({ ...project, consent_mode: "UPLOAD" })));
    renderAt("/projects/p1/rules/consent");
    const consent = await screen.findByRole("group", { name: "How participants give consent" });
    const warning = /^Signed forms uploaded so far stop counting while the project is Online/;
    expect(screen.queryByText(warning)).toBeNull();
    await userEvent.click(within(consent).getByRole("radio", { name: /^Online/ }));
    expect(screen.getByText(warning)).toHaveTextContent(
      "those people cannot be put on tasks or recorded until they agree on their personal page. Switch back to Upload and the forms count again.",
    );
    expect(consent).toHaveAccessibleDescription(/stop counting while the project is Online/);
    // Back to Upload: nothing to warn about.
    await userEvent.click(within(consent).getByRole("radio", { name: /^Upload/ }));
    expect(screen.queryByText(warning)).toBeNull();
    // Saved as Online: the project is online now, so there is nothing left to warn about.
    await userEvent.click(within(consent).getByRole("radio", { name: /^Online/ }));
    await userEvent.click(screen.getByRole("button", { name: "Save rules" }));
    expect(await screen.findByText("Rules saved.")).toBeInTheDocument();
    expect(screen.queryByText(warning)).toBeNull();
  });

  it("adds a language that is not in the list by its code (POL-02)", async () => {
    const { calls } = fakeApi(
      signedInAs(MANAGER, {
        "GET /api/v1/projects/p1": () => [200, project],
        "PUT /api/v1/projects/p1/languages": (body) => [
          200,
          { ...project, languages: (body as { languages: unknown[] }).languages },
        ],
      }),
    );
    renderAt("/projects/p1/languages");
    const language = await screen.findByRole("combobox", { name: "Language" });
    expect(within(language).getAllByRole("option").at(-1)).toHaveTextContent(
      "Other (type the code)",
    );
    const add = screen.getByRole("button", { name: "Add language" });
    expect(screen.queryByRole("textbox", { name: "Language code" })).toBeNull();
    await userEvent.selectOptions(language, "Other (type the code)");
    expect(add).toBeDisabled();
    const code = screen.getByRole("textbox", { name: "Language code" });
    await userEvent.type(code, "Swahili");
    expect(code).toHaveAccessibleDescription(/like sw or en-US/);
    expect(add).toBeDisabled();
    await userEvent.clear(code);
    await userEvent.type(code, "sw");
    expect(add).toBeEnabled();
    await userEvent.type(screen.getByRole("textbox", { name: "Dialect" }), "Coastal");
    await userEvent.click(add);
    expect(await screen.findByText("Language added.")).toBeInTheDocument();
    expect(calls.find((c) => c.method === "PUT")?.body).toEqual({
      languages: [
        { language_code: "hi", dialect: "Awadhi" },
        { language_code: "sw", dialect: "Coastal" },
      ],
    });
    // The form starts again for the next one.
    expect(language).toHaveValue("");
    expect(screen.queryByRole("textbox", { name: "Language code" })).toBeNull();
  });
});

describe("the project's Participants page", () => {
  /** The progress answer with this many speakers still needed. */
  const stillNeeded = (n: number) => {
    const speakers = PROGRESS.still_needed.speakers;
    return {
      ...PROGRESS,
      still_needed: {
        ...PROGRESS.still_needed,
        speakers: {
          ...speakers,
          total: { ...speakers.total, total: { ...speakers.total.total, still_needed: n } },
        },
      },
    };
  };

  it("reads the Still needed line again after someone is added (FEA-09)", async () => {
    let still = 495;
    const { calls } = fakeApi(
      signedInAs([...MANAGER, "participants.view", "participants.manage"], {
        ...worldHandlers(),
        "GET /api/v1/projects/p1/progress": () => [200, stillNeeded(still)],
        "GET /api/v1/projects/p1/participants/link-candidates": () => [
          200,
          [
            {
              id: "c9",
              participant_code: "P000009",
              display_label: "Chitra",
              language_code: "hi",
              dialect: "",
            },
          ],
        ],
        "POST /api/v1/projects/p1/participants/link": () => {
          still = 494;
          return [
            200,
            {
              ...PARTICIPANT,
              id: "c9",
              participant_code: "P000009",
              consent_email: "Consent form emailed.",
            },
          ];
        },
      }),
    );
    renderAt("/projects/p1/participants");
    expect(await screen.findByText("Still needed: 495 speakers")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Add existing participant" }));
    await userEvent.click(await screen.findByRole("button", { name: "Add P000009" }));
    expect(await screen.findByText("Still needed: 494 speakers")).toBeInTheDocument();
    expect(calls.filter((c) => c.path === "/api/v1/projects/p1/progress")).toHaveLength(2);
  });

  it("still shows the participants when the progress answer has no Still needed figures (FEA-01)", async () => {
    // An older server during a deploy answers without `still_needed`.
    fakeApi(
      signedInAs([...MANAGER, "participants.view", "participants.manage"], {
        ...worldHandlers(),
        "GET /api/v1/projects/p1/progress": () => [200, { project_id: "p1" }],
      }),
    );
    renderAt("/projects/p1/participants");
    expect(await screen.findByText("P000001")).toBeInTheDocument();
    expect(screen.queryByText(/Still needed|No more speakers/)).toBeNull();
    expect(screen.getByRole("button", { name: "Add participant" })).toBeInTheDocument();
  });

  it("marks a missing phone with a dash, and a search without a match says so (UXA-12, UXA-13)", async () => {
    fakeApi(
      signedInAs([...MANAGER, "participants.view", "participants.manage"], {
        ...worldHandlers(),
        "GET /api/v1/projects/p1/participants": (_body, url) => [
          200,
          url.searchParams.get("search")
            ? { items: [], total: 0, page: 1, page_size: 25 }
            : {
                items: [{ ...PARTICIPANT, phone: null, has_phone: false }],
                total: 1,
                page: 1,
                page_size: 25,
              },
        ],
      }),
    );
    renderAt("/projects/p1/participants");
    const row = (await screen.findByText("P000001")).closest("tr") as HTMLTableRowElement;
    expect(row.cells[2]).toHaveTextContent(/^-$/);
    expect(within(row).queryByText("None")).toBeNull();
    await userEvent.type(screen.getByRole("searchbox", { name: "Search by code or name" }), "zz");
    expect(await screen.findByRole("heading", { name: "No participants match" })).toBeVisible();
    expect(screen.getByText("Try another code or name.")).toBeInTheDocument();
    expect(screen.queryByText("No participants yet")).toBeNull();
  });
});

describe("the project list", () => {
  /** Projects PRJ0001 to PRJ0060, 25 a page, as the server pages them. */
  const pages = (_body: unknown, url: URL): [number, unknown] => {
    const page = Number(url.searchParams.get("page") ?? "1");
    const first = (page - 1) * 25;
    const items = Array.from({ length: Math.min(25, 60 - first) }, (_, i) => ({
      ...project,
      id: `q${first + i + 1}`,
      code: `PRJ${String(first + i + 1).padStart(4, "0")}`,
      name: `Project ${first + i + 1}`,
    }));
    return [200, { items, total: 60, page, page_size: 25 }];
  };

  it("keeps its search, status and page in the address, so Back returns to them (FEA-07)", async () => {
    const { calls } = fakeApi(
      signedInAs(["projects.view"], {
        "GET /api/v1/projects": pages,
        "GET /api/v1/projects/q26": () => [200, { ...project, id: "q26", code: "PRJ0026" }],
      }),
    );
    const router = renderAt("/projects");
    await userEvent.selectOptions(await screen.findByLabelText("Status"), "DRAFT");
    await userEvent.type(screen.getByRole("searchbox", { name: "Search" }), "Project");
    await waitFor(() =>
      expect(new URLSearchParams(router.state.location.search).get("search")).toBe("Project"),
    );
    await userEvent.click(await screen.findByRole("button", { name: "Next" }));
    expect(await screen.findByText("Page 2 of 3 (60 total)")).toBeInTheDocument();
    const params = new URLSearchParams(router.state.location.search);
    expect([params.get("search"), params.get("status"), params.get("page")]).toEqual([
      "Project",
      "DRAFT",
      "2",
    ]);

    await userEvent.click(await screen.findByRole("link", { name: "PRJ0026" }));
    expect(
      await screen.findByRole("heading", { name: "PRJ0026 · Hindi conversations" }),
    ).toBeVisible();
    await act(() => router.navigate(-1));
    expect(await screen.findByText("Page 2 of 3 (60 total)")).toBeInTheDocument();
    expect(screen.getByRole("searchbox", { name: "Search" })).toHaveValue("Project");
    expect(screen.getByLabelText("Status")).toHaveValue("DRAFT");
    expect(calls.at(-1)?.path).toBe(
      "/api/v1/projects?search=Project&status=DRAFT&page=2&page_size=25",
    );
  });

  it("says when nothing matches the filters and clears them in one click (UXA-12)", async () => {
    fakeApi(
      signedInAs(["projects.view"], {
        "GET /api/v1/projects": (_body, url) =>
          url.searchParams.get("status") === "ARCHIVED"
            ? [200, { items: [], total: 0, page: 1, page_size: 25 }]
            : pages(_body, url),
      }),
    );
    const router = renderAt("/projects?status=ARCHIVED");
    expect(await screen.findByRole("heading", { name: "No projects match" })).toBeVisible();
    expect(screen.getByText("Try another search or status.")).toBeInTheDocument();
    expect(screen.queryByText(/not a member/)).toBeNull();
    // Clear filters is the filter bar's last part, as on every list (D-158).
    const filters = screen.getByRole("group", { name: "Filters" });
    expect(screen.getAllByRole("button", { name: "Clear filters" })).toHaveLength(1);
    await userEvent.click(within(filters).getByRole("button", { name: "Clear filters" }));
    expect(await screen.findByRole("link", { name: "PRJ0001" })).toBeInTheDocument();
    expect(router.state.location.search).toBe("");
    expect(screen.getByLabelText("Status")).toHaveValue("");
    expect(within(filters).queryByRole("button", { name: "Clear filters" })).toBeNull();
  });

  it("titles the page without an icon tile and lists plain codes (UXA-14)", async () => {
    fakeApi(signedInAs(["projects.view"], { "GET /api/v1/projects": pages }));
    renderAt("/projects");
    const code = await screen.findByRole("link", { name: "PRJ0001" });
    expect(
      screen.getByRole("heading", { level: 1, name: "Projects" }).querySelector(".tile"),
    ).toBeNull();
    expect(code.closest("td")).toHaveTextContent(/^PRJ0001$/);
  });

  it("has New project in the title row's actions, a full row on a phone as on every page (D-159)", async () => {
    fakeApi(signedInAs(["projects.view", "projects.create"], { "GET /api/v1/projects": pages }));
    renderAt("/projects");
    const add = await screen.findByRole("link", { name: "New project" });
    expect(add.parentElement).toHaveClass("actions");
    expect(add.parentElement?.parentElement).toHaveClass("page-header");
  });
});
