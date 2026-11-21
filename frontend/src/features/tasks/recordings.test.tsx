// The task page lists finished recordings; a download brings the consent record (D-068) and the
// details file (D-079) with the audio. A recording the moderator replaced is greyed and says so
// (D-135); an approved task's files download as one ZIP (D-136).
// Requirements: PART-015, STOR-006, AQC-008, EXP-001
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { fakeApi, renderAt, signedInAs } from "../../test/fakeApi";
import { ALL_PERMISSIONS, TASK, worldHandlers } from "../../test/world";

afterEach(() => vi.unstubAllGlobals());

const RECORDING = {
  id: "r1",
  task_id: "t1",
  state: "READY",
  current: true,
  saved_seconds: 600,
  assets: [
    { id: "a1", kind: "BROWSER_ORIGINAL", sample_rate: 16000, channels: 1 },
    { id: "a2", kind: "FTF_DERIVED_PCM", sample_rate: 16000, channels: 1 },
  ],
};

// Recorded first, then replaced when the moderator chose Record again.
const REPLACED = { ...RECORDING, id: "r0", current: false, saved_seconds: 300 };

function open(permissions: string[], status = "RECORDED", recordings: unknown[] = [RECORDING]) {
  vi.stubGlobal(
    "URL",
    Object.assign(URL, { createObjectURL: () => "blob:x", revokeObjectURL: () => {} }),
  );
  return fakeApi(
    signedInAs(permissions, {
      ...worldHandlers(),
      "GET /api/v1/tasks/t1": () => [200, { ...TASK, status }],
      "GET /api/v1/tasks/t1/recordings": () => [200, recordings],
      "GET /api/v1/tasks/t1/export": () => [200, "zip"],
      "POST /api/v1/assets/a2/url": () => [
        200,
        { url: "https://storage.example/a2.wav", expires_in: 300 },
      ],
      "GET /api/v1/recordings/r1/consent-form": () => [200, "<html></html>"],
      "GET /api/v1/recordings/r1/metadata": () => [200, { format: "ccp.recording-metadata/1" }],
      "GET /api/v1/tasks/t1/audio-qc": () => [
        200,
        {
          task_status: "RECORDED",
          qc_user_id: null,
          qc_name: null,
          can_decide: false,
          can_assign: false,
          can_recheck: false,
          reasons: { FAIL: [] },
          results: [],
        },
      ],
    }),
  );
}

describe("recordings on the task page", () => {
  it("downloads the delivery file, the consent record and the details file together", async () => {
    const { calls } = open(ALL_PERMISSIONS);
    renderAt("/tasks/t1");
    await userEvent.click(
      await screen.findByRole("button", { name: "Download with consent form" }, { timeout: 5000 }),
    );
    expect(
      await screen.findByText("Recording, consent record and details downloaded."),
    ).toBeInTheDocument();
    await waitFor(() => {
      expect(calls.find((c) => c.path === "/api/v1/assets/a2/url")?.body).toEqual({
        purpose: "download",
      });
      expect(calls.some((c) => c.path === "/api/v1/recordings/r1/consent-form")).toBe(true);
      expect(calls.some((c) => c.path === "/api/v1/recordings/r1/metadata")).toBe(true);
    });
  });

  it("shows one recording file in plain words, and no download without the right", async () => {
    open(ALL_PERMISSIONS.filter((p) => p !== "recordings.download"));
    renderAt("/tasks/t1");
    expect(await screen.findByText("16000 Hz, mono", {}, { timeout: 5000 })).toBeInTheDocument();
    expect(screen.getByText("Recording 1")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Download with consent form" })).toBeNull();
  });

  it("says the effective speech and the long pauses under the length (D-148)", async () => {
    const measured = {
      ...RECORDING,
      assets: [
        RECORDING.assets[0],
        {
          ...RECORDING.assets[1],
          duration_ms: 600_000,
          effective_ms: 372_000,
          longest_pause_ms: 7_200,
          long_pauses: 3,
          pause_limit_seconds: 3,
        },
      ],
    };
    open(ALL_PERMISSIONS, "RECORDED", [measured]);
    renderAt("/tasks/t1");
    const line = await screen.findByText(
      "Effective speech 6 min 12 s · 3 pauses over 3 s",
      {},
      { timeout: 5000 },
    );
    expect(line.closest("td")).toHaveTextContent("10 min");
  });

  it("says nothing of effective speech before the file is measured, and 'no pauses'", async () => {
    const one = {
      ...RECORDING,
      assets: [
        RECORDING.assets[0],
        {
          ...RECORDING.assets[1],
          duration_ms: 45_000,
          effective_ms: 40_000,
          longest_pause_ms: 900,
          long_pauses: 0,
          pause_limit_seconds: 3,
        },
      ],
    };
    open(ALL_PERMISSIONS, "RECORDED", [one, { ...RECORDING, id: "r2", current: false }]);
    renderAt("/tasks/t1");
    expect(
      await screen.findByText("Effective speech 40 s · no pauses over 3 s", {}, { timeout: 5000 }),
    ).toBeInTheDocument();
    expect(screen.getAllByText(/^Effective speech/)).toHaveLength(1);
  });
});

describe("replaced recordings and the task's files", () => {
  it("greys a recording the moderator replaced, and says why", async () => {
    open(ALL_PERMISSIONS, "AUDIO_QC", [RECORDING, REPLACED]);
    renderAt("/tasks/t1");
    const tag = await screen.findByText(
      "Rejected by moderator – recorded again",
      {},
      { timeout: 5000 },
    );
    expect(tag.closest("tr")).toHaveClass("row--replaced");
    expect(screen.getByText("Recording 2").closest("tr")).not.toHaveClass("row--replaced");
    expect(screen.getAllByText("Rejected by moderator – recorded again")).toHaveLength(1);
  });

  it("downloads an approved task's files as one ZIP for people who may export", async () => {
    const { calls } = open([...ALL_PERMISSIONS, "exports.create"], "APPROVED");
    renderAt("/tasks/t1");
    await userEvent.click(
      await screen.findByRole("button", { name: "Download task files" }, { timeout: 5000 }),
    );
    expect(await screen.findByText("Task files downloaded.")).toBeInTheDocument();
    expect(calls.some((c) => c.path === "/api/v1/tasks/t1/export")).toBe(true);
  });

  it("offers no task download before approval", async () => {
    open([...ALL_PERMISSIONS, "exports.create"], "ADMIN_REVIEW");
    renderAt("/tasks/t1");
    expect(await screen.findByText("Recording 1", {}, { timeout: 5000 })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Download task files" })).toBeNull();
  });

  it("offers no task download to someone who may not export", async () => {
    open(ALL_PERMISSIONS, "APPROVED");
    renderAt("/tasks/t1");
    expect(await screen.findByText("Recording 1", {}, { timeout: 5000 })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Download task files" })).toBeNull();
  });
});
