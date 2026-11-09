// Requirements: FTF-003, FTF-004, FTF-005, FTF-007, FTF-008, FTF-010, FTF-012, AUDIO-004
// Real browser audio path (fake microphone, AudioWorklet, chunk upload, playback of a 16 kHz 16-bit
// mono WAV); backend answered by page.route.
import { expect, test } from "@playwright/test";

const task = {
  id: "t1",
  task_code: "T000042",
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

/** A 16 kHz, 16-bit, mono PCM WAV: the delivery format the player must handle. */
function deliveryWav(seconds: number): Buffer {
  const rate = 16000;
  const frames = rate * seconds;
  const out = Buffer.alloc(44 + frames * 2);
  out.write("RIFF", 0);
  out.writeUInt32LE(36 + frames * 2, 4);
  out.write("WAVEfmt ", 8);
  out.writeUInt32LE(16, 16);
  out.writeUInt16LE(1, 20); // PCM
  out.writeUInt16LE(1, 22); // mono
  out.writeUInt32LE(rate, 24);
  out.writeUInt32LE(rate * 2, 28);
  out.writeUInt16LE(2, 32);
  out.writeUInt16LE(16, 34);
  out.write("data", 36);
  out.writeUInt32LE(frames * 2, 40);
  for (let i = 0; i < frames; i++)
    out.writeInt16LE(Math.round(8000 * Math.sin((2 * Math.PI * 440 * i) / rate)), 44 + i * 2);
  return out;
}

test("records with the fake microphone, uploads whole frames with checksums, and plays back", async ({
  page,
}) => {
  const chunks: { seq: number; bytes: number; type: string; sha: string }[] = [];
  let started: Record<string, unknown> | null = null;
  let completedWith: unknown = null;
  await page.route("**/api/v1/auth/csrf", (r) => r.fulfill({ status: 204 }));
  await page.route("**/api/v1/auth/me", (r) =>
    r.fulfill({
      json: {
        id: "u1",
        email: "m@example.org",
        display_name: "Mo",
        roles: ["MODERATOR"],
        permissions: ["tasks.view", "recordings.create", "recordings.view"],
        project_ids: ["p1"],
        mfa_enabled: false,
      },
    }),
  );
  await page.route("**/api/v1/tasks/t1", (r) => r.fulfill({ json: task }));
  await page.route("**/api/v1/projects/p1", (r) =>
    r.fulfill({ json: { id: "p1", audio_rules: [] } }),
  );
  await page.route("**/api/v1/tasks/t1/recordings", async (r) => {
    if (r.request().method() === "POST") {
      started = r.request().postDataJSON() as Record<string, unknown>;
      return r.fulfill({ status: 201, json: { id: "r1", state: "RECORDING" } });
    }
    return r.fulfill({ json: [] });
  });
  await page.route("**/api/v1/recordings/r1/chunks/*", (r) => {
    const req = r.request();
    chunks.push({
      seq: Number(req.url().split("/").pop()),
      bytes: req.postDataBuffer()?.length ?? 0,
      type: req.headers()["content-type"] ?? "",
      sha: req.headers()["x-content-sha256"] ?? "",
    });
    return r.fulfill({ json: { seq: 0, size_bytes: 0, sha256: "" } });
  });
  await page.route("**/api/v1/recordings/r1/complete", (r) => {
    completedWith = r.request().postDataJSON();
    return r.fulfill({ json: { id: "r1", state: "UPLOADED" } });
  });
  // What the server answers once processing is done: values derived from what the page sent.
  await page.route("**/api/v1/recordings/r1", (r) => {
    const channels = Number(started?.["channel_count"]);
    return r.fulfill({
      json: {
        id: "r1",
        task_id: "t1",
        state: "READY",
        native_sample_rate: started?.["native_sample_rate"],
        channel_count: channels,
        device_channel_count: started?.["device_channel_count"],
        channel_handling: channels > 1 ? `first channel of ${channels}` : "mono",
        chunks_received: chunks.length,
        saved_seconds: 7,
        interrupted: false,
        failure_reason: null,
        assets: [
          {
            id: "a2",
            kind: "FTF_DERIVED_PCM",
            version: 1,
            codec: "pcm_s16le",
            sample_rate: 16000,
            bit_depth: 16,
            channels: 1,
            duration_ms: 2000,
            size_bytes: 64044,
            sha256: "0".repeat(64),
            peak_dbfs: -12,
            rms_dbfs: -15,
            clip_pct: 0,
            silence_pct: 0,
          },
        ],
      },
    });
  });
  await page.route("**/api/v1/assets/a2/url", (r) =>
    r.fulfill({ json: { url: "/signed/derived.wav", expires_in: 300 } }),
  );
  await page.route("**/signed/derived.wav", (r) =>
    r.fulfill({ status: 200, contentType: "audio/wav", body: deliveryWav(2) }),
  );

  await page.goto("/tasks/t1/record");
  await page.getByRole("button", { name: "Allow microphone" }).click();
  // Start appears only once the capture has reported its real channel count (no guessing).
  await page.getByRole("button", { name: "Start recording" }).click();
  await expect(page.getByText(/Recording 0:0[1-9]/)).toBeVisible();
  await page.waitForTimeout(7000);
  await page.getByRole("button", { name: "Stop and save" }).click();
  await expect(page.getByRole("heading", { name: "Recording saved" })).toBeVisible({
    timeout: 20_000,
  });

  expect(started).toMatchObject({
    echo_cancellation: false,
    noise_suppression: false,
    auto_gain_control: false,
  });
  expect(started).not.toHaveProperty("channel_handling"); // the server derives it from the data
  const channels = Number(started?.["channel_count"]);
  const rate = Number(started?.["native_sample_rate"]);
  const device = started?.["device_channel_count"];
  expect(Number.isInteger(channels) && channels >= 1).toBe(true);
  expect(device === null || (typeof device === "number" && device >= 1)).toBe(true);
  test.info().annotations.push({
    type: "channels",
    description: `device reported ${String(device)}, captured ${channels}, rate ${rate}`,
  });

  expect(chunks.length).toBeGreaterThanOrEqual(2);
  expect(chunks.map((c) => c.seq)).toEqual([...chunks.keys()]);
  const frameBytes = 4 * channels;
  const fullChunk = Math.round(rate * 5) * frameBytes;
  for (const [i, c] of chunks.entries()) {
    expect(c.type).toBe("application/octet-stream");
    expect(c.sha).toMatch(/^[0-9a-f]{64}$/);
    expect(c.bytes % frameBytes).toBe(0); // whole frames: every channel of every instant
    if (i < chunks.length - 1) expect(c.bytes).toBe(fullChunk); // 5 s of every channel
  }
  expect(completedWith).toEqual({ chunk_count: chunks.length });
  await expect(
    page.getByText(new RegExp(`${channels} captured and kept in the original`)),
  ).toBeVisible();

  // Playback: the browser decodes the delivery format and plays it to the end of its length.
  await page.getByRole("button", { name: "Listen" }).click();
  const player = page.getByLabel("Recorded conversation");
  await expect(player).toBeVisible();
  const played = await player.evaluate(async (node) => {
    const audio = node as HTMLAudioElement;
    if (audio.readyState < 1)
      await new Promise((resolve, reject) => {
        audio.addEventListener("loadedmetadata", resolve, { once: true });
        audio.addEventListener("error", reject, { once: true });
      });
    audio.muted = true;
    await audio.play();
    await new Promise((resolve) => audio.addEventListener("ended", resolve, { once: true }));
    return { duration: audio.duration, ended: audio.ended, error: audio.error?.code ?? null };
  });
  expect(played.error).toBeNull();
  expect(played.ended).toBe(true);
  expect(played.duration).toBeCloseTo(2, 1);
});
