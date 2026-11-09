// Requirements: FTF-001, FTF-002, FTF-006, FTF-009
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { fakeApi, renderAt, signedInAs, type Handler } from "../../test/fakeApi";

const task = {
  id: "t1",
  task_code: "T000009",
  project_id: "p1",
  recording_mode: "FACE_TO_FACE",
  status: "IN_PROGRESS",
  priority: "NORMAL",
  due_at: null,
  created_at: "",
  held_from: null,
  reason_code: null,
  participant_a: { id: "a", participant_code: "P1", consent_status: "GIVEN", consent_at: null },
  participant_b: { id: "b", participant_code: "P2", consent_status: "GIVEN", consent_at: null },
  moderator_id: "u1",
  moderator_name: "Mo",
  allowed_transitions: [],
  reasons: {},
  can_assign: false,
  is_moderator: true,
};
const project = {
  id: "p1",
  audio_rules: [
    {
      mode: "FACE_TO_FACE",
      sample_rate: 16000,
      bit_depth: 16,
      channels: 1,
      max_silence_pct: "25.00",
      max_clipping_pct: null,
      min_duration_seconds: 0,
      max_duration_seconds: null,
    },
  ],
};

function api(recordings: unknown[], extra: Record<string, Handler> = {}) {
  return fakeApi(
    signedInAs(["tasks.view", "recordings.create", "recordings.view"], {
      "GET /api/v1/tasks/t1": () => [200, task],
      "GET /api/v1/projects/p1": () => [200, project],
      "GET /api/v1/tasks/t1/recordings": () => [200, recordings],
      ...extra,
    }),
  );
}

beforeEach(() => {
  vi.stubGlobal("AudioWorkletNode", function AudioWorkletNode() {});
});
afterEach(() => vi.unstubAllGlobals());

describe("RecorderPage", () => {
  it("explains when the browser cannot record", async () => {
    vi.stubGlobal("navigator", { ...navigator, mediaDevices: undefined });
    api([]);
    renderAt("/tasks/t1/record");
    expect(await screen.findByText("This browser cannot record here")).toBeInTheDocument();
  });

  it("shows project audio rules and a clear message when the microphone is refused", async () => {
    vi.stubGlobal("navigator", {
      ...navigator,
      mediaDevices: {
        getUserMedia: vi.fn().mockRejectedValue(new DOMException("denied", "NotAllowedError")),
      },
    });
    api([]);
    renderAt("/tasks/t1/record");
    expect(
      await screen.findByText(/Project audio rules: delivered as 16000 Hz, 16-bit, mono/),
    ).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Allow microphone" }));
    expect(await screen.findByText(/Microphone permission was refused/)).toBeInTheDocument();
  });

  it("offers to keep the saved audio of an interrupted recording", async () => {
    vi.stubGlobal("navigator", { ...navigator, mediaDevices: { getUserMedia: vi.fn() } });
    const open = {
      id: "r1",
      task_id: "t1",
      state: "RECORDING",
      chunks_received: 3,
      saved_seconds: 15,
      interrupted: false,
      assets: [],
    };
    const { calls } = api([open], {
      "POST /api/v1/recordings/r1/interrupted": () => [200, { ...open, state: "INTERRUPTED" }],
      "POST /api/v1/recordings/r1/complete": () => [200, { ...open, state: "UPLOADED" }],
    });
    renderAt("/tasks/t1/record");
    expect(
      await screen.findByText(/0:15 of audio reached the server and is kept/),
    ).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Keep the saved 0:15" }));
    await vi.waitFor(() =>
      expect(calls.some((c) => c.path === "/api/v1/recordings/r1/complete")).toBe(true),
    );
    expect(calls.filter((c) => c.method === "POST").map((c) => [c.path, c.body])).toEqual([
      ["/api/v1/recordings/r1/interrupted", { reason: "Page closed or reloaded during recording" }],
      ["/api/v1/recordings/r1/complete", { chunk_count: 3 }],
    ]);
  });
});
