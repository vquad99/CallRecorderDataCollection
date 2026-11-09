// Helpers for the user-journey tests (owner's test list, Option D). These run a real browser
// against the real backend, database and file storage; nothing is mocked.
//
// Environment: E2E_ADMIN_PASSWORD (the seeded Super Admin's password, DEMO_PASSWORD), E2E_OUTBOX
// (the backend's EMAIL_FILE_DIR, where invitation and reset emails are written as files).
import { createHash, randomBytes } from "node:crypto";
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";

import { expect, type Page, type TestInfo } from "@playwright/test";

export const ADMIN_EMAIL = process.env.E2E_ADMIN_EMAIL ?? "demo.super-admin@example.org";
export const SEEDED_PASSWORD = process.env.E2E_ADMIN_PASSWORD ?? "";
export const OUTBOX = process.env.E2E_OUTBOX ?? "";
// A fresh password for every run: nothing that works anywhere is stored in the code.
export const NEW_PASSWORD = `journey-${randomBytes(12).toString("hex")}`;

/** A short code unique to this test run and browser, so reruns never collide. */
export function runCode(info: TestInfo): string {
  const browser = info.project.name.slice(0, 1).toUpperCase();
  return `${browser}${(Date.now() % 1e9).toString(36).toUpperCase()}${info.workerIndex}`;
}

export function requireSetup(): void {
  expect(SEEDED_PASSWORD, "E2E_ADMIN_PASSWORD must be set").not.toBe("");
  expect(OUTBOX, "E2E_OUTBOX must be set").not.toBe("");
}

export async function signIn(page: Page, email: string, password: string): Promise<void> {
  await page.goto("/login");
  await page.getByLabel(/^Email/).fill(email);
  await page.getByLabel(/^Password/).fill(password);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("navigation", { name: "Main" })).toBeVisible();
}

function quotedPrintable(text: string): string {
  return text
    .replace(/=\r?\n/g, "")
    .replace(/=([0-9A-F]{2})/g, (_, hex: string) => String.fromCharCode(parseInt(hex, 16)));
}

/** The newest password link emailed to this address (invitation or reset). */
export async function emailedLink(to: string, after: number): Promise<string> {
  let link = "";
  await expect
    .poll(
      () => {
        const files = readdirSync(OUTBOX)
          .filter((f) => f.endsWith(".eml"))
          .map((f) => join(OUTBOX, f))
          .filter((f) => statSync(f).mtimeMs >= after)
          .sort((a, b) => statSync(b).mtimeMs - statSync(a).mtimeMs);
        for (const file of files) {
          const text = quotedPrintable(readFileSync(file, "utf8"));
          if (!new RegExp(`^To: .*${to.replace(/[.+]/g, "\\$&")}`, "mi").test(text)) continue;
          const match = /https?:\/\/\S*?\/reset-password\?token=[A-Za-z0-9_-]+/.exec(text);
          if (match) {
            link = match[0];
            return true;
          }
        }
        return false;
      },
      { message: `an email with a password link to ${to}`, timeout: 15_000 },
    )
    .toBe(true);
  // The link names the configured site; open it on the site under test.
  return new URL(link).pathname + new URL(link).search;
}

/** API calls made with the signed-in browser's own session (as the page itself would). */
export async function api<T>(
  page: Page,
  method: "GET" | "POST" | "PUT" | "PATCH" | "DELETE",
  path: string,
  body?: unknown,
): Promise<T> {
  const cookies = await page.context().cookies();
  const csrf = cookies.find((c) => c.name === "csrf_token")?.value ?? "";
  const response = await page.request.fetch(path, {
    method,
    headers: { "X-CSRF-Token": csrf, Accept: "application/json" },
    ...(body === undefined ? {} : { data: body }),
  });
  expect(response.status(), `${method} ${path}: ${await response.text()}`).toBeLessThan(400);
  return (response.status() === 204 ? null : await response.json()) as T;
}

export function sha256(data: Buffer): string {
  return createHash("sha256").update(data).digest("hex");
}

/** Plays an <audio> element to its end (muted, fast) and reports what the browser saw. */
export async function playToEnd(page: Page, label: string) {
  return page.getByLabel(label).evaluate(async (node) => {
    const audio = node as HTMLAudioElement;
    if (audio.readyState < 1)
      await new Promise((resolve, reject) => {
        audio.addEventListener("loadedmetadata", resolve, { once: true });
        audio.addEventListener("error", reject, { once: true });
      });
    audio.muted = true;
    audio.playbackRate = 4;
    await audio.play();
    await new Promise((resolve) => audio.addEventListener("ended", resolve, { once: true }));
    return { duration: audio.duration, ended: audio.ended, error: audio.error?.code ?? null };
  });
}

export interface Setup {
  projectId: string;
  taskId: string;
  taskCode: string;
}

/** Fast set-up through the API as the signed-in Super Admin: an active face-to-face project with
 * two participants and one task, assigned to `moderator` when given. */
export async function setUpTask(
  admin: Page,
  code: string,
  members: string[],
  moderator?: string,
): Promise<Setup> {
  const project = await api<{ id: string }>(admin, "POST", "/api/v1/projects", {
    code,
    name: `Journey ${code}`,
    allows_telephony: false,
    allows_face_to_face: true,
  });
  await api(admin, "POST", `/api/v1/projects/${project.id}/status`, { status: "ACTIVE" });
  await api(admin, "PUT", `/api/v1/projects/${project.id}/languages`, {
    languages: [{ language_code: "hi", dialect: "" }],
  });
  const ids: Record<string, string> = {};
  for (const email of members) {
    const found = await api<{ items: { id: string; email: string }[] }>(
      admin,
      "GET",
      `/api/v1/users?search=${encodeURIComponent(email)}`,
    );
    const id = found.items.find((u) => u.email === email)?.id ?? "";
    ids[email] = id;
    await api(admin, "POST", `/api/v1/projects/${project.id}/members`, { user_id: id });
  }
  const people = [];
  for (const label of ["Asha", "Bina"]) {
    people.push(
      await api<{ id: string }>(admin, "POST", `/api/v1/projects/${project.id}/participants`, {
        display_label: `${label} ${code}`,
        language_code: "hi",
      }),
    );
  }
  const task = await api<{ id: string; task_code: string }>(admin, "POST", "/api/v1/tasks", {
    project_id: project.id,
    recording_mode: "FACE_TO_FACE",
    participant_a_id: people[0]?.id,
    participant_b_id: people[1]?.id,
  });
  if (moderator) {
    await api(admin, "POST", `/api/v1/tasks/${task.id}/assign`, { user_id: ids[moderator] });
  }
  return { projectId: project.id, taskId: task.id, taskCode: task.task_code };
}

export const SEEDED = {
  moderator: "demo.moderator@example.org",
  transcriber: "demo.transcriber@example.org",
  clientViewer: "demo.client-viewer@example.org",
};
