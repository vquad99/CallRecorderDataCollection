// Requirements: PROJ-009, PROJ-013, ROLE-011, USER-003, EXP-008, EXP-009, EXP-010
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { fakeApi, renderAt, signedInAs } from "../../test/fakeApi";

afterEach(() => vi.unstubAllGlobals());

const SUMMARY = {
  recordings: 3,
  face_to_face: 2,
  telephony: 1,
  audio_bytes: 240_000_000,
  file_name: "audio_HINDI_20261111_0900.zip",
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
    await userEvent.click(await screen.findByRole("button", { name: "Change status" }));
    expect(await screen.findByText("Status changed.")).toBeInTheDocument();
    expect(screen.getByText("This project accepts new work.")).toBeInTheDocument();
    expect(calls.find((c) => c.path === "/api/v1/projects/p1/status")?.body).toEqual({
      status: "ACTIVE",
      reason: null,
    });
  });

  it("makes a paused project active again without choosing anything else first", async () => {
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
    // Active -> Paused (the first choice offered for an active project).
    await userEvent.click(await screen.findByRole("button", { name: "Change status" }));
    expect(
      await screen.findByText("This project does not accept new work until it is active."),
    ).toBeInTheDocument();
    // The box now offers Active first; one more click sends it.
    expect(screen.getByLabelText("Change status to")).toHaveValue("ACTIVE");
    await userEvent.click(screen.getByRole("button", { name: "Change status" }));
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
    expect(screen.queryByRole("button", { name: "Change status" })).not.toBeInTheDocument();
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
    expect(await screen.findByRole("group", { name: "Telephony" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("link", { name: "Languages" }));
    expect(await screen.findByText(/Hindi \(hi\), Awadhi/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("link", { name: "Retention" }));
    expect(await screen.findByLabelText("Browser original captures")).toBeInTheDocument();
    // Each box shows a faded example under it, tied to the box for screen readers (D-086).
    expect(screen.getByLabelText("Consent recordings")).toHaveAccessibleDescription(
      "Example: 1825 (five years)",
    );
  });

  it("goes back to the project list with a note after creating a project", async () => {
    const created = { ...project, id: "p9", code: "PRJ0009", name: "Tamil talk" };
    fakeApi(
      signedInAs(["projects.view", "projects.create", "projects.manage"], {
        "POST /api/v1/projects": () => [201, created],
        "GET /api/v1/projects": () => [200, { items: [created], total: 1, page: 1, page_size: 25 }],
      }),
    );
    renderAt("/projects/new");
    await userEvent.type(await screen.findByLabelText(/^Name/), "Tamil talk");
    await userEvent.click(screen.getByRole("button", { name: "Create project" }));
    expect(
      await screen.findByText(/^PRJ0009 Tamil talk created\. It starts as Draft/),
    ).toBeInTheDocument();
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
    expect(screen.getByText(/2 face-to-face, 1 telephony · about 240 MB of audio/)).toBeVisible();
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
      "Audio only · every finished recording · Telephony · Hindi (hi) · with originals · TSV",
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
});
