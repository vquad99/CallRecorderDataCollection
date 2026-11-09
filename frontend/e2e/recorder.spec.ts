// Requirements: FTF-003, FTF-004, FTF-007, FTF-008, FTF-010, FTF-012, AUDIO-004
// Real browser audio path (fake microphone, AudioWorklet, chunk upload); backend answered by page.route.
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

test("records with the fake microphone and uploads raw chunks with checksums", async ({ page }) => {
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
  await page.route("**/api/v1/recordings/r1", (r) =>
    r.fulfill({
      json: {
        id: "r1",
        task_id: "t1",
        state: "READY",
        chunks_received: chunks.length,
        saved_seconds: 7,
        interrupted: false,
        failure_reason: null,
        assets: [],
      },
    }),
  );

  await page.goto("/tasks/t1/record");
  await page.getByRole("button", { name: "Allow microphone" }).click();
  await expect(page.getByLabel("Input level")).toBeVisible();
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
  // The browser decides the device's channel count; the app records it and how it was reduced to mono.
  const count = Number(started?.["channel_count"]);
  expect(started?.["channel_handling"]).toBe(count > 1 ? `first channel of ${count}` : "mono");
  expect(chunks.length).toBeGreaterThanOrEqual(2);
  expect(chunks.map((c) => c.seq)).toEqual([...chunks.keys()]);
  expect(
    chunks.every(
      (c) =>
        c.type === "application/octet-stream" && /^[0-9a-f]{64}$/.test(c.sha) && c.bytes % 4 === 0,
    ),
  ).toBe(true);
  expect(completedWith).toEqual({ chunk_count: chunks.length });
});
