// Requirements: FTF-001, FTF-002, FTF-006, FTF-009, FTF-014
// The recorder captures at the project's rate (16000 Hz) and never converts (owner 2026-11-17).
import { act, render, screen, within } from "@testing-library/react";
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
  participant_a: {
    id: "a",
    participant_code: "P1",
    display_label: "Asha Naik",
    consent_status: "GIVEN",
    consent_at: null,
  },
  // The moderator may not see this one's name.
  participant_b: {
    id: "b",
    participant_code: "P2",
    display_label: null,
    consent_status: "GIVEN",
    consent_at: null,
  },
  moderator_id: "u1",
  moderator_name: "Mo",
  allowed_transitions: [],
  reasons: {},
  can_assign: false,
  can_reassign: false,
  is_moderator: true,
  consent_missing: [],
  // The project's reminders for face-to-face (D-147).
  reminders: {
    speaker_id: true,
    topics: ["weather", "food and cooking"],
    avoid: ["politics", "personal information"],
    tips: [
      "Place the recording device between the two speakers, no more than 2.5 feet from each mouth, and do not move it.",
    ],
  },
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

/** A file of a recording, as the server lists it. */
function asset(id: string, kind: string, rate: number, depth: number, silence = 3.2) {
  return {
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
    silence_pct: silence,
  };
}

/** A recording prepared by the server: the original capture and the delivered recording. */
function prepared(state: "READY" | "FAILED" = "READY", silence = 3.2) {
  return {
    id: "r1",
    task_id: "t1",
    state,
    native_sample_rate: 16000,
    channel_count: 1,
    device_channel_count: 1,
    channel_handling: "mono",
    echo_cancellation: false,
    noise_suppression: false,
    auto_gain_control: false,
    chunks_received: 2,
    interrupted: false,
    failure_reason: state === "FAILED" ? "RuntimeError" : null,
    saved_seconds: 7,
    current: true,
    assets:
      state === "READY"
        ? [
            asset("a1", "BROWSER_ORIGINAL", 16000, 32, silence),
            asset("a2", "FTF_DERIVED_PCM", 16000, 16, silence),
          ]
        : [],
  };
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
    const note = await screen.findByRole("note", { name: "Reminders" });
    expect(note).toHaveTextContent(/Place the recording device between the two speakers/);
    expect(note).toHaveTextContent("At most 25% of the recording may be silence.");
    await userEvent.click(screen.getByRole("button", { name: "Allow microphone" }));
    expect(await screen.findByText(/Microphone permission was refused/)).toBeInTheDocument();
  });

  it("reminds the moderator before recording, with each speaker's code (D-147)", async () => {
    vi.stubGlobal("navigator", { ...navigator, mediaDevices: { getUserMedia: vi.fn() } });
    api([]);
    renderAt("/tasks/t1/record");
    const note = await screen.findByRole("note", { name: "Reminders" });
    const lines = within(note)
      .getAllByRole("listitem")
      .map((li) => li.textContent);
    // The first name only, where the moderator may see it; the code always.
    expect(lines).toContain("“I am Asha and speaker ID P1”");
    expect(lines).toContain("“I am <their name> and speaker ID P2”");
    expect(lines).toContain("Talk about: weather, food and cooking");
    expect(lines).toContain("Avoid: politics, personal information");
    expect(lines.at(-1)).toBe("At most 25% of the recording may be silence.");
    // Before Start recording: the note comes before the microphone.
    expect(
      note.compareDocumentPosition(screen.getByRole("button", { name: "Allow microphone" })) &
        Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
  });

  it("leaves out the speaker-ID line when the project does not ask it (D-147)", async () => {
    vi.stubGlobal("navigator", { ...navigator, mediaDevices: { getUserMedia: vi.fn() } });
    api([], {
      "GET /api/v1/tasks/t1": () => [
        200,
        { ...task, reminders: { speaker_id: false, topics: [], avoid: [], tips: ["Sit still."] } },
      ],
    });
    renderAt("/tasks/t1/record");
    const note = await screen.findByRole("note", { name: "Reminders" });
    expect(note).toHaveTextContent("Sit still.");
    expect(note).not.toHaveTextContent(/speaker ID/);
    expect(note).not.toHaveTextContent(/Talk about/);
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
      "GET /api/v1/recordings/r1": () => [200, prepared()],
    });
    renderAt("/tasks/t1/record");
    expect(
      await screen.findByText(/0:15 of audio reached the server and is kept/),
    ).toBeInTheDocument();
    await vi.waitFor(() => expect(document.title).toBe("Record T000009 · Conversation Collection"));
    await userEvent.click(screen.getByRole("button", { name: "Keep the saved 0:15" }));
    await vi.waitFor(() =>
      expect(calls.some((c) => c.path === "/api/v1/recordings/r1/complete")).toBe(true),
    );
    expect(calls.filter((c) => c.method === "POST").map((c) => [c.path, c.body])).toEqual([
      ["/api/v1/recordings/r1/interrupted", { reason: "Page closed or reloaded during recording" }],
      ["/api/v1/recordings/r1/complete", { chunk_count: 3 }],
    ]);
    // FEW-02: the kept audio is prepared and shown, with Send to QC; not a fresh start.
    expect(await screen.findByRole("heading", { name: "Recording saved" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Send to QC" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Record again" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Allow microphone" })).not.toBeInTheDocument();
    expect(screen.queryByText("An earlier recording did not finish")).not.toBeInTheDocument();
  });

  it("keeps the way back and the title when the task cannot be loaded (POL-13)", async () => {
    vi.stubGlobal("navigator", { ...navigator, mediaDevices: { getUserMedia: vi.fn() } });
    api([], {
      "GET /api/v1/tasks/t1": () => [
        404,
        { error: { code: "NOT_FOUND", message: "Task not found", request_id: "r" } },
      ],
    });
    renderAt("/tasks/t1/record");
    expect(
      await screen.findByRole("heading", { level: 1, name: "Record task" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "All tasks" })).toHaveAttribute("href", "/tasks");
    expect(screen.getByText("Task not found")).toBeInTheDocument();
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
    onended: null as (() => void) | null,
    stopped: false,
    stop() {
      this.stopped = true;
    },
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
  return { asked, speak, track };
}

/** The microphone is allowed, audio arrives, and Start recording is pressed. */
async function startRecording(audio: ReturnType<typeof fakeAudio>) {
  renderAt("/tasks/t1/record");
  await userEvent.click(await screen.findByRole("button", { name: "Allow microphone" }));
  await audio.speak();
  await userEvent.click(await screen.findByRole("button", { name: "Start recording" }));
  expect(await screen.findByRole("button", { name: "Stop and save" })).toBeInTheDocument();
}

describe("no dead ends while recording (FEW-01, FEW-08)", () => {
  const open = {
    id: "r1",
    task_id: "t1",
    state: "INTERRUPTED",
    chunks_received: 2,
    saved_seconds: 10,
    interrupted: true,
    assets: [],
  };

  it("offers to keep or discard the saved audio when the microphone stops", async () => {
    const audio = fakeAudio();
    let listed: unknown[] = [];
    const { calls } = api([], {
      "GET /api/v1/tasks/t1/recordings": () => [200, listed],
      "POST /api/v1/tasks/t1/recordings": () => [201, { id: "r1", state: "RECORDING" }],
      "POST /api/v1/recordings/r1/interrupted": () => {
        listed = [open];
        return [200, open];
      },
    });
    await startRecording(audio);
    act(() => audio.track.onended?.());
    const card = await screen.findByRole("alert", { name: "The recording stopped" });
    expect(card).toHaveTextContent(
      "The microphone stopped. 0:10 of audio reached the server and is kept. Nothing after that " +
        "was recorded.",
    );
    expect(within(card).getByRole("button", { name: "Keep the saved 0:10" })).toBeInTheDocument();
    expect(within(card).getByRole("button", { name: "Discard it" })).toBeInTheDocument();
    expect(calls.find((c) => c.path === "/api/v1/recordings/r1/interrupted")?.body).toEqual({
      reason: "Microphone stopped",
    });
    expect(audio.track.stopped).toBe(true); // the microphone is let go
    expect(screen.queryByRole("button", { name: "Allow microphone" })).not.toBeInTheDocument();
  });

  it("offers the same when saving fails, instead of a fresh start the server refuses", async () => {
    const audio = fakeAudio();
    let listed: unknown[] = [];
    api([], {
      "GET /api/v1/tasks/t1/recordings": () => [200, listed],
      "POST /api/v1/tasks/t1/recordings": () => [201, { id: "r1", state: "RECORDING" }],
      "PUT /api/v1/recordings/r1/chunks/0": () => [200, { seq: 0, size_bytes: 640, sha256: "" }],
      "POST /api/v1/recordings/r1/complete": () => {
        listed = [{ ...open, state: "RECORDING", interrupted: false }];
        return [
          409,
          {
            error: {
              code: "MISSING_CHUNKS",
              message: "Some parts of the recording have not arrived yet",
              request_id: "r",
            },
          },
        ];
      },
    });
    await startRecording(audio);
    await audio.speak();
    await userEvent.click(screen.getByRole("button", { name: "Stop and save" }));
    const card = await screen.findByRole("alert", { name: "The recording stopped" });
    expect(card).toHaveTextContent("The recording could not be saved. 0:10 of audio reached");
    expect(within(card).getByRole("button", { name: "Keep the saved 0:10" })).toBeInTheDocument();
    expect(
      screen.getByText("Some parts of the recording have not arrived yet"),
    ).toBeInTheDocument();
    expect(audio.track.stopped).toBe(true);
    expect(screen.queryByRole("button", { name: "Allow microphone" })).not.toBeInTheDocument();
  });

  it("sends Start recording once, and waits while it is on its way", async () => {
    const audio = fakeAudio();
    let answer: (reply: [number, unknown]) => void = () => undefined;
    const { calls } = api([], {
      "POST /api/v1/tasks/t1/recordings": () =>
        new Promise<[number, unknown]>((resolve) => {
          answer = resolve;
        }),
    });
    renderAt("/tasks/t1/record");
    await userEvent.click(await screen.findByRole("button", { name: "Allow microphone" }));
    await audio.speak();
    const start = await screen.findByRole("button", { name: "Start recording" });
    await userEvent.dblClick(start);
    await vi.waitFor(() => expect(start).toBeDisabled());
    expect(screen.getByRole("button", { name: /^Test/ })).toBeDisabled();
    expect(calls.filter((c) => c.method === "POST")).toHaveLength(1);
    answer([201, { id: "r1", state: "RECORDING" }]);
    expect(await screen.findByRole("button", { name: "Stop and save" })).toBeInTheDocument();
    expect(calls.filter((c) => c.method === "POST")).toHaveLength(1);
  });

  it("lets the moderator record again when the recording could not be prepared", async () => {
    const audio = fakeAudio();
    api([], {
      "POST /api/v1/tasks/t1/recordings": () => [201, { id: "r1", state: "RECORDING" }],
      "POST /api/v1/recordings/r1/complete": () => [200, { ...open, state: "UPLOADED" }],
      "GET /api/v1/recordings/r1": () => [200, prepared("FAILED")],
    });
    await startRecording(audio);
    await userEvent.click(screen.getByRole("button", { name: "Stop and save" }));
    expect(await screen.findByRole("heading", { name: "Processing failed" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Send to QC" })).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Record again" }));
    expect(await screen.findByRole("button", { name: "Allow microphone" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Processing failed" })).not.toBeInTheDocument();
  });
});

describe("the silence of a saved recording (UXW-12)", () => {
  it("warns at once when there is more silence than the project allows", async () => {
    const { Result } = await import("./RecorderPage");
    for (const [silence, warned] of [
      [92.2, true],
      [3.2, false],
    ] as const) {
      fakeApi(signedInAs(["tasks.view"]));
      const router = createMemoryRouter([
        { path: "/", element: <Result recording={prepared("READY", silence)} maxSilence={25} /> },
      ]);
      const { unmount } = render(
        <AuthProvider>
          <RouterProvider router={router} />
        </AuthProvider>,
      );
      expect(await screen.findByText("Recorded at 16000 Hz.")).toBeInTheDocument();
      const warning = screen.queryByText(/of this recording is silence/);
      if (warned) {
        expect(warning).toHaveTextContent(
          "92.2% of this recording is silence; this project allows at most 25%. Listen to it, " +
            "and record again while both speakers are here if it is not good.",
        );
        expect(warning).toHaveAttribute("role", "status");
      } else {
        expect(warning).toBeNull();
      }
      unmount();
    }
  });
});

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
      current: true,
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
  function show(onAgain = vi.fn(), waits: string | null = null) {
    const router = createMemoryRouter(
      [
        {
          path: "/tasks/t1/record",
          element: <AfterRecording taskId="t1" onAgain={onAgain} waits={waits} />,
        },
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

  it("waits for the device details before Send to QC (D-147)", async () => {
    const { calls } = fakeApi({});
    show(vi.fn(), "Fill in the device details of P2 first (Device details card).");
    const send = screen.getByRole("button", { name: "Send to QC" });
    expect(send).toBeDisabled();
    expect(send).toHaveAccessibleDescription(
      "Fill in the device details of P2 first (Device details card).",
    );
    // Recording again does not wait.
    expect(screen.getByRole("button", { name: "Record again" })).toBeEnabled();
    expect(calls).toHaveLength(0);
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
