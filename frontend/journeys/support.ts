// Helpers for the user-journey tests (owner's test list, Option D). These run a real browser
// against the real backend, database and file storage; nothing is mocked.
//
// Environment: E2E_ADMIN_PASSWORD (the seeded Super Admin's password, DEMO_PASSWORD), E2E_OUTBOX
// (the backend's EMAIL_FILE_DIR, where invitation and reset emails are written as files).
import { createHash, randomBytes } from "node:crypto";
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";

import { expect, type Locator, type Page, type TestInfo } from "@playwright/test";

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

/** The newest link of one kind in the emails to this address written since `after`. */
async function newestEmailedUrl(to: string, after: number, kind: RegExp, what: string) {
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
          const match = kind.exec(text);
          if (match) {
            link = match[0];
            return true;
          }
        }
        return false;
      },
      { message: `an email with ${what} to ${to}`, timeout: 15_000 },
    )
    .toBe(true);
  return new URL(link);
}

/** The newest password link emailed to this address (invitation or reset). */
export async function emailedLink(to: string, after: number): Promise<string> {
  const link = await newestEmailedUrl(
    to,
    after,
    /https?:\/\/\S*?\/reset-password\?token=[A-Za-z0-9_-]+/,
    "a password link",
  );
  // The link names the configured site; open it on the site under test.
  return link.pathname + link.search;
}

/** The newest personal link to a project's consent form emailed to this participant (D-129);
 * staff never see it (D-142). As a path on the site under test, with its secret after "#". */
export async function emailedConsentLink(to: string): Promise<string> {
  const link = await newestEmailedUrl(
    to,
    0,
    /https?:\/\/\S*?\/portal#[A-Za-z0-9_-]{20,}/,
    "a consent form link",
  );
  return link.pathname + link.hash;
}

/** API calls made with the signed-in browser's own session (as the page itself would). */
export async function api<T>(
  page: Page,
  method: "GET" | "POST" | "PUT" | "PATCH" | "DELETE",
  path: string,
  body?: unknown,
  headers: Record<string, string> = {},
): Promise<T> {
  const cookies = await page.context().cookies();
  const csrf = cookies.find((c) => c.name === "csrf_token")?.value ?? "";
  const response = await page.request.fetch(path, {
    method,
    headers: { "X-CSRF-Token": csrf, Accept: "application/json", ...headers },
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
  return page.getByLabel(label, { exact: true }).evaluate(async (node) => {
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

/** Complete speaker details (D-143): a task is made only for people who have them all. */
export const SPEAKER_DETAILS = {
  age: 34,
  gender: "FEMALE",
  current_state: "Goa",
  current_district: "North Goa",
  current_pincode: "403001",
  native_state: "Goa",
  district: "Salcete",
  native_pincode: "403601",
  native_language: "Konkani",
  education: "BACHELORS",
  education_medium: "ENGLISH",
  recording_state: "Goa",
  recording_district: "North Goa",
  recording_pincode: "403001",
};

/** Fills every speaker detail in the Add participant window, as a person would (D-143). */
export async function fillSpeakerDetails(form: Locator): Promise<void> {
  const box = (label: string) => form.getByLabel(new RegExp(`^${label}`));
  const d = SPEAKER_DETAILS;
  await box("Age").fill(String(d.age));
  await box("Gender").selectOption(d.gender);
  for (const [where, title] of [
    ["current", "Current"],
    ["native", "Native"],
    ["recording", "Recording"],
  ] as const) {
    await box(`${title} state`).selectOption(d[`${where}_state`]);
    await box(`${title} district`).fill(where === "native" ? d.district : d[`${where}_district`]);
    await box(`${title} PIN code`).fill(d[`${where}_pincode`]);
  }
  await box("Native language").fill(d.native_language);
  await box("Education").selectOption(d.education);
  await box("Medium of education").selectOption(d.education_medium);
}

/** Fills both speakers' device details in the Device details card and saves them, as the
 * moderator does before Send to QC (D-147; a project made through the API asks all five). */
export async function fillDeviceDetails(page: Page): Promise<void> {
  const card = page.getByRole("region", { name: "Device details" });
  // D-152: one matrix, a row per detail and a column per speaker; each box and Yes / No switch
  // is named "<detail> – Participant <side>".
  for (const side of ["A", "B"]) {
    await card.getByLabel(`Device make – Participant ${side}`, { exact: true }).fill("Samsung");
    await card.getByLabel(`Device model – Participant ${side}`, { exact: true }).fill("Galaxy A14");
    for (const question of ["Bluetooth earphones used", "Wired earphones used", "Loudspeaker on"]) {
      await card
        .getByRole("radiogroup", { name: `${question} – Participant ${side}`, exact: true })
        .getByRole("radio", { name: "No" })
        .check();
    }
  }
  await card.getByRole("button", { name: "Save device details" }).click();
  await expect(card.getByText("Device details saved.")).toBeVisible();
}

/** The participant agrees to the project's consent form the real way (D-129: tasks are made only
 * for people who agreed): with the personal link emailed to them when they joined the project,
 * the answer goes in through the personal page's API with the link's secret, as the page itself
 * sends it. */
export async function agree(admin: Page, projectId: string, participantId: string): Promise<void> {
  const person = await api<{ email: string | null }>(
    admin,
    "GET",
    `/api/v1/projects/${projectId}/participants/${participantId}`,
  );
  expect(person.email, "the participant has an email address").toBeTruthy();
  // The secret sits after "#" (D-067).
  const token = (await emailedConsentLink(person.email ?? "")).split("#")[1] ?? "";
  const page = await api<{ consent_status: string }>(
    admin,
    "POST",
    "/api/v1/portal/consent",
    { decision: "GIVEN" },
    { "X-Portal-Token": token },
  );
  expect(page.consent_status).toBe("GIVEN");
}

/** Fast set-up through the API as the signed-in Super Admin: an active face-to-face project with
 * a consent form, two participants who agreed to it, and one task, assigned to `moderator` when
 * given. */
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
    consent_text: `I agree to be recorded for ${code}.`,
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
    const person = await api<{ id: string }>(
      admin,
      "POST",
      `/api/v1/projects/${project.id}/participants`,
      {
        display_label: `${label} ${code}`,
        language_code: "hi",
        email: `${label.toLowerCase()}.${code.toLowerCase()}@example.org`,
        ...SPEAKER_DETAILS,
      },
    );
    await agree(admin, project.id, person.id);
    people.push(person);
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
  qcExecutive: "demo.qc-executive@example.org",
  clientViewer: "demo.client-viewer@example.org",
};
