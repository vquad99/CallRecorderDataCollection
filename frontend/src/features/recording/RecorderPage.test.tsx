// Requirements: FTF-001, FTF-002, FTF-006, FTF-009
// The recorder captures at the project's rate (16000 Hz) and never converts (owner 2026-11-17).
import { act, render, screen } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { AuthProvider } from "../../auth/AuthContext";
import { fakeApi, ME, renderAt, signedInAs, type Handler } from "../../test/fakeApi";
import { AfterRecording } from "./RecorderPage";

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
  can_reassign: false,
  is_moderator: true,
  consent_missing: [],
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

  it("shows plain advice and a clear message when the microphone is refused", async () => {
    vi.stubGlobal("navigator", {
      ...navigator,
      mediaDevices: {
        getUserMedia: vi.fn().mockRejectedValue(new DOMException("denied", "NotAllowedError")),
      },
    });
    api([]);
    renderAt("/tasks/t1/record");
    expect(
      await screen.findByText(/Place the microphone between the two speakers/),
    ).toHaveTextContent("At most 25% of the recording may be silence.");
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

  it("does not let recording start until both participants have consent (D-119)", async () => {
    vi.stubGlobal("navigator", { ...navigator, mediaDevices: { getUserMedia: vi.fn() } });
    fakeApi(
      signedInAs(["tasks.view", "recordings.create", "recordings.view"], {
        "GET /api/v1/tasks/t1": () => [200, { ...task, consent_missing: ["B"] }],
        "GET /api/v1/projects/p1": () => [200, project],
        "GET /api/v1/tasks/t1/recordings": () => [200, []],
      }),
    );
    renderAt("/tasks/t1/record");
    expect(
      await screen.findByText(/Participant B has not agreed on the consent form yet/),
    ).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Allow microphone" })).not.toBeInTheDocument();
  });
});

/** A browser's audio parts: the context keeps the rate asked for unless told otherwise. */
function fakeAudio({ refuse = false, keptRate }: { refuse?: boolean; keptRate?: number } = {}) {
  const nodes: { port: { onmessage: ((event: { data: unknown }) => void) | null } }[] = [];
  const asked: (number | undefined)[] = [];
  class FakeContext {
    sampleRate: number;
    destination = {};
    audioWorklet = { addModule: () => Promise.resolve() };
    constructor(options?: { sampleRate?: number }) {
      asked.push(options?.sampleRate);
      if (refuse) throw new DOMException("rate not supported", "NotSupportedError");
      this.sampleRate = keptRate ?? options?.sampleRate ?? 48000;
    }
    createMediaStreamSource() {
      return { connect: () => undefined };
    }
    createGain() {
      return { gain: { value: 1 }, connect: (to: unknown) => to };
    }
    close() {
      return Promise.resolve();
    }
  }
  function FakeNode(this: (typeof nodes)[number] & { connect: (to: unknown) => unknown }) {
    this.port = { onmessage: null };
    this.connect = (to) => to;
    nodes.push(this);
  }
  const track = {
    label: "Desk microphone",
    onended: null,
    stop: () => undefined,
    getSettings: () => ({
      channelCount: 1,
      echoCancellation: false,
      noiseSuppression: false,
      autoGainControl: false,
    }),
  };
  vi.stubGlobal("AudioContext", FakeContext);
  vi.stubGlobal("AudioWorkletNode", FakeNode);
  vi.stubGlobal("navigator", {
    ...navigator,
    mediaDevices: {
      getUserMedia: () =>
        Promise.resolve({ getTracks: () => [track], getAudioTracks: () => [track] }),
      enumerateDevices: () => Promise.resolve([]),
    },
  });
  /** The first block of audio from the microphone: the page then knows its channels. */
  const speak = () =>
    act(() =>
      nodes[0]?.port.onmessage?.({ data: { samples: new Float32Array(160), channels: 1 } }),
    );
  return { asked, speak };
}

describe("recording at the project's rate, never converted (owner 2026-11-17)", () => {
  it("opens the microphone at 16000 Hz and tells the server so", async () => {
    const audio = fakeAudio();
    const { calls } = api([], {
      "POST /api/v1/tasks/t1/recordings": () => [201, { id: "r1", state: "RECORDING" }],
    });
    renderAt("/tasks/t1/record");
    await userEvent.click(await screen.findByRole("button", { name: "Allow microphone" }));
    await vi.waitFor(() => expect(audio.asked).toEqual([16000]));
    await audio.speak();
    await userEvent.click(await screen.findByRole("button", { name: "Start recording" }));
    await vi.waitFor(() =>
      expect(calls.find((c) => c.method === "POST")?.body).toMatchObject({
        native_sample_rate: 16000,
        channel_count: 1,
      }),
    );
  });

  it("does not record when the browser refuses the rate", async () => {
    fakeAudio({ refuse: true });
    const { calls } = api([]);
    renderAt("/tasks/t1/record");
    await userEvent.click(await screen.findByRole("button", { name: "Allow microphone" }));
    expect(await screen.findByText("This browser cannot record at 16000 Hz")).toBeInTheDocument();
    expect(screen.getByText("Use the latest Chrome or Edge.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Allow microphone" })).not.toBeInTheDocument();
    expect(calls.some((c) => c.method === "POST")).toBe(false);
  });

  it("does not record when the browser quietly keeps its own rate", async () => {
    fakeAudio({ keptRate: 48000 });
    api([]);
    renderAt("/tasks/t1/record");
    await userEvent.click(await screen.findByRole("button", { name: "Allow microphone" }));
    expect(await screen.findByText("This browser cannot record at 16000 Hz")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Start recording" })).not.toBeInTheDocument();
  });

  it("names the recording file in plain words; only the Super Admin sees the technical details", async () => {
    const asset = (id: string, kind: string, rate: number, depth: number) => ({
      id,
      kind,
      version: 1,
      codec: "pcm",
      sample_rate: rate,
      bit_depth: depth,
      channels: 1,
      duration_ms: 7000,
      size_bytes: 1,
      sha256: "",
      peak_dbfs: null,
      rms_dbfs: null,
      clip_pct: 0,
      silence_pct: 3.2,
    });
    const recording = {
      id: "r1",
      task_id: "t1",
      state: "READY" as const,
      native_sample_rate: 16000,
      channel_count: 1,
      device_channel_count: 1,
      channel_handling: "mono",
      echo_cancellation: false,
      noise_suppression: false,
      auto_gain_control: false,
      chunks_received: 2,
      interrupted: false,
      failure_reason: null,
      saved_seconds: 7,
      assets: [
        asset("a1", "BROWSER_ORIGINAL", 16000, 32),
        asset("a2", "FTF_DERIVED_PCM", 16000, 16),
      ],
    };
    const { Result } = await import("./RecorderPage");
    for (const [roles, technical] of [
      [["MODERATOR"], false],
      [["SUPER_ADMIN"], true],
    ] as const) {
      fakeApi(
        signedInAs(["tasks.view"], {
          "GET /api/v1/auth/me": () => [200, { ...ME, roles, permissions: ["tasks.view"] }],
        }),
      );
      const router = createMemoryRouter([{ path: "/", element: <Result recording={recording} /> }]);
      const { unmount } = render(
        <AuthProvider>
          <RouterProvider router={router} />
        </AuthProvider>,
      );
      expect(await screen.findByText("Recorded at 16000 Hz.")).toBeInTheDocument();
      expect(screen.getByText("Recording, 16000 Hz, mono")).toBeInTheDocument();
      if (technical) expect(await screen.findByText("Technical details")).toBeInTheDocument();
      expect(screen.queryByText("Original capture") !== null).toBe(technical);
      unmount();
    }
  });
});

describe("after a recording (D-120)", () => {
  function show(onAgain = vi.fn()) {
    const router = createMemoryRouter(
      [
        { path: "/tasks/t1/record", element: <AfterRecording taskId="t1" onAgain={onAgain} /> },
        { path: "/tasks/t1", element: <p>Task page</p> },
      ],
      { initialEntries: ["/tasks/t1/record"] },
    );
    render(<RouterProvider router={router} />);
    return onAgain;
  }

  it("sends the recording to QC from the recorder and opens the task", async () => {
    const { calls } = fakeApi({
      "POST /api/v1/tasks/t1/transition": () => [200, { ...task, status: "AUDIO_QC" }],
    });
    show();
    await userEvent.click(screen.getByRole("button", { name: "Send to QC" }));
    expect(await screen.findByText("Task page")).toBeInTheDocument();
    expect(calls[0]?.body).toMatchObject({ to: "AUDIO_QC" });
  });

  it("records again from the recorder", async () => {
    const { calls } = fakeApi({
      "POST /api/v1/tasks/t1/transition": () => [200, task],
    });
    const onAgain = show();
    await userEvent.click(screen.getByRole("button", { name: "Record again" }));
    await vi.waitFor(() => expect(onAgain).toHaveBeenCalled());
    expect(calls[0]?.body).toMatchObject({ to: "IN_PROGRESS" });
  });
});
