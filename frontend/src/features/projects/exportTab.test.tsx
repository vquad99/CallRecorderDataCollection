// A project's Export tab (D-094, D-105, D-149): recordings prepared as a bundle with the chosen
// filters and followed until ready, the layout the project's bundles take with what is missing,
// and the reports downloaded as one table. The count is asked for once the choice settles, and
// only for what changes it.
// Requirements: EXP-001, EXP-002, EXP-006, EXP-008, EXP-009, EXP-010, PROJ-011
import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { SPEAKER_FIELDS } from "../../lib/speakers";
import { fakeApi, renderAt, signedInAs } from "../../test/fakeApi";
import { EXPORT_JOB, PROJECT } from "../../test/world";

afterEach(() => vi.unstubAllGlobals());

const MANAGER = ["projects.view", "projects.manage", "exports.create"];

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

/** A project of one recording type, phone calls (D-153). */
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
/** A project made before D-153 that still allows both recording types. */
const bothTypes = { ...project, allows_face_to_face: true };

/** The summary requests made, as "content=...&scope=..." . */
const summaries = (calls: { path: string }[]) =>
  calls
    .filter((c) => c.path.startsWith("/api/v1/projects/p1/export/summary"))
    .map((c) => c.path.split("?")[1] ?? "");

/** The Export tab of `shown`, with a fixed summary and no prepared export yet. */
function exportsOf(shown: Record<string, unknown>, permissions = MANAGER) {
  return fakeApi(
    signedInAs(permissions, {
      "GET /api/v1/projects/p1": () => [200, shown],
      "GET /api/v1/projects/p1/export/summary": () => [200, SUMMARY],
      "GET /api/v1/projects/p1/exports": () => [
        200,
        { items: [], total: 0, page: 1, page_size: 20 },
      ],
    }),
  );
}

describe("the Export tab", () => {
  it("prepares a bundle with the chosen filters and follows it until it is ready (D-105)", async () => {
    const jobs: Record<string, unknown>[] = [];
    let looks = 0;
    const { calls } = fakeApi(
      signedInAs(MANAGER, {
        "GET /api/v1/projects/p1": () => [200, bothTypes],
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
    const prepare = await screen.findByRole("button", { name: "Prepare export" });
    await waitFor(() => expect(prepare).toBeEnabled());
    await userEvent.click(prepare);
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

    // The file's whole name on hover, as its line may be cut short (D-158).
    expect(within(list).getByTitle(JOB.file_name)).toHaveTextContent(JOB.file_name);
    await userEvent.click(within(list).getByRole("button", { name: `Download ${JOB.file_name}` }));
    expect(
      await screen.findByText(`Downloading ${JOB.file_name}. The link works for 5 minutes.`),
    ).toBeInTheDocument();
    // Removed with the bin, as a row everywhere (D-158).
    const remove = screen.getByRole("button", { name: `Remove ${JOB.file_name}` });
    expect(remove).toHaveClass("icon-button");
    await userEvent.click(remove);
    await userEvent.click(
      within(screen.getByRole("dialog")).getByRole("button", { name: "Remove" }),
    );
    expect(await screen.findByText(`${JOB.file_name} removed.`)).toBeInTheDocument();
    expect(await screen.findByText(/No export has been prepared yet/)).toBeInTheDocument();
  }, 20000);

  it("gives reports as CSV or TSV, and says why an export failed or cannot be asked for", async () => {
    vi.stubGlobal(
      "URL",
      Object.assign(URL, { createObjectURL: () => "blob:x", revokeObjectURL: () => {} }),
    );
    const { calls } = fakeApi(
      signedInAs(MANAGER, {
        "GET /api/v1/projects/p1": () => [200, bothTypes],
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
        "GET /api/v1/projects/p1/export": (_b, url) =>
          url.searchParams.get("content") === "participants"
            ? [403, { error: { code: "FORBIDDEN", message: "Not allowed", request_id: "r9" } }]
            : [200, "task_code,status\n"],
      }),
    );
    renderAt("/projects/p1/export");
    // Each report is saved as one table, fetched like any other request.
    const reports = await screen.findByRole("region", { name: "Reports" });
    await userEvent.click(within(reports).getByRole("button", { name: "Progress report as CSV" }));
    await waitFor(() =>
      expect(
        calls.some((c) => c.path === "/api/v1/projects/p1/export?content=progress&format=csv"),
      ).toBe(true),
    );
    expect(within(reports).getByText(/Times in India time \(IST\)\./)).toBeInTheDocument();
    // A refusal is said on the page, not a failed browser download.
    await userEvent.click(
      within(reports).getByRole("button", { name: "Participant minutes as TSV" }),
    );
    expect(await within(reports).findByRole("alert")).toHaveTextContent("Not allowed");
    expect(
      calls.some((c) => c.path === "/api/v1/projects/p1/export?content=participants&format=tsv"),
    ).toBe(true);
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

  it("offers no choice of recording type in a project of one type (D-153)", async () => {
    exportsOf(project);
    renderAt("/projects/p1/export");
    expect(await screen.findByText("3 recordings")).toBeInTheDocument();
    expect(screen.getByLabelText("Which recordings")).toBeInTheDocument();
    expect(screen.queryByLabelText("Recording type")).toBeNull();
    // Nor a split of the count by type: there is one type.
    expect(screen.getByText("about 240 MB of audio")).toBeVisible();
    expect(screen.queryByText(/face-to-face,/)).toBeNull();
    // The tables' format is named by its usual short name.
    expect(
      Array.from((screen.getByLabelText("Tables as") as HTMLSelectElement).options).map(
        (o) => o.text,
      ),
    ).toEqual(["CSV", "TSV"]);
  });

  it("asks for the count again only when what is counted changes", async () => {
    const { calls } = exportsOf(bothTypes, [...MANAGER, "participants.export"]);
    renderAt("/projects/p1/export");
    expect(await screen.findByText("3 recordings")).toBeInTheDocument();
    expect(summaries(calls)).toEqual(["content=both&scope=approved"]);
    // The tables' format and the contact details change the files, not the recordings.
    await userEvent.selectOptions(screen.getByLabelText("Tables as"), "tsv");
    await userEvent.click(screen.getByRole("checkbox", { name: /phone numbers/ }));
    await new Promise((done) => setTimeout(done, 600));
    expect(summaries(calls)).toEqual(["content=both&scope=approved"]);
    expect(screen.getByText("3 recordings")).toBeInTheDocument();
    // Choices made one after the other are counted once, when the choice settles.
    fireEvent.change(screen.getByLabelText("Which recordings"), { target: { value: "finished" } });
    fireEvent.change(screen.getByLabelText("Recording type"), { target: { value: "TELEPHONY" } });
    await waitFor(() => expect(summaries(calls)).toHaveLength(2));
    expect(summaries(calls)[1]).toBe("content=both&scope=finished&mode=TELEPHONY");
    expect(await screen.findByText("3 recordings")).toBeInTheDocument();
  });

  it("waits for a typed year before asking for the days (Edge fills it with zeros first)", async () => {
    const { calls } = exportsOf(project);
    renderAt("/projects/p1/export");
    expect(await screen.findByText("3 recordings")).toBeInTheDocument();
    const from = screen.getByLabelText("Recorded from");
    const to = screen.getByLabelText("Recorded to");
    fireEvent.change(to, { target: { value: "2026-11-30" } });
    await waitFor(() => expect(summaries(calls)).toHaveLength(2));
    // The year of the first day half typed: no question to the server, and no error.
    fireEvent.change(from, { target: { value: "0002-11-01" } });
    fireEvent.change(from, { target: { value: "0202-11-01" } });
    await new Promise((done) => setTimeout(done, 600));
    expect(summaries(calls)).toHaveLength(2);
    expect(screen.queryByText("Must not be before the first day")).toBeNull();
    expect(screen.getByRole("button", { name: "Prepare export" })).toBeDisabled();
    // The whole year: asked once.
    fireEvent.change(from, { target: { value: "2026-11-01" } });
    await waitFor(() => expect(summaries(calls)).toHaveLength(3));
    expect(summaries(calls)[2]).toBe(
      "content=both&scope=approved&recorded_from=2026-11-01&recorded_to=2026-11-30",
    );
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Prepare export" })).toBeEnabled(),
    );
  });
});

describe("the Export tab's layout", () => {
  function exportTab(over: Record<string, unknown>, summary: Record<string, unknown>) {
    return fakeApi(
      signedInAs(MANAGER, {
        "GET /api/v1/projects/p1": () => [200, { ...PROJECT, ...over }],
        "GET /api/v1/projects/p1/export/summary": () => [
          200,
          {
            recordings: 2,
            face_to_face: 1,
            telephony: 1,
            audio_bytes: 2_000_000,
            file_name: "both_HINDI_20261122_0900.zip",
            ...summary,
          },
        ],
        "GET /api/v1/projects/p1/exports": () => [
          200,
          {
            items: [
              {
                ...EXPORT_JOB,
                filters: { ...EXPORT_JOB.filters, layout: over.export_layout ?? "CLIENT" },
                missing: summary.missing ?? 0,
              },
            ],
            total: 1,
            page: 1,
            page_size: 20,
          },
        ],
      }),
    );
  }

  it("says the speaker-pair format is used, links to its Rules section and counts what is missing", async () => {
    exportTab({ speaker_id_style: "CODE" }, { layout: "CLIENT", missing: 3 });
    renderAt("/projects/p1/export");
    const note = await screen.findByText(/speaker-pair delivery format/);
    const paragraph = note.closest("p") as HTMLElement;
    expect(paragraph).toHaveTextContent("P000001_P000002_570001_576101_CON001.wav");
    expect(paragraph).toHaveTextContent(/MISSING\.csv listing what is not on file/);
    expect(paragraph).not.toHaveTextContent(/client/i);
    expect(within(paragraph).getByRole("link", { name: "Change it under Rules" })).toHaveAttribute(
      "href",
      "/projects/p1/rules/export",
    );
    expect(
      await screen.findByText("3 items missing", { selector: ".export__summary span" }),
    ).toBeVisible();
    // The prepared export says it too, and in which layout it was made.
    const list = await screen.findByRole("table", { name: "Prepared exports" });
    expect(within(list).getByText("3 items missing")).toBeInTheDocument();
    expect(list).toHaveTextContent("Speaker-pair format · Audio + metadata · approved tasks · CSV");
  });

  it("says when nothing is missing", async () => {
    exportTab({}, { layout: "CLIENT", missing: 0 });
    renderAt("/projects/p1/export");
    expect(await screen.findByText("Nothing missing")).toBeInTheDocument();
  });

  it("names the platform's own layout", async () => {
    exportTab({ export_layout: "PLATFORM" }, { layout: "PLATFORM", missing: 0 });
    renderAt("/projects/p1/export");
    const note = await screen.findByText(/platform's own layout/);
    expect(note.closest("p")).toHaveTextContent(/details file and consent record/);
    expect(await screen.findByText("2 recordings")).toBeInTheDocument();
    expect(screen.queryByText(/missing/i)).toBeNull();
    const list = await screen.findByRole("table", { name: "Prepared exports" });
    expect(list).not.toHaveTextContent("Speaker-pair format");
  });
});
