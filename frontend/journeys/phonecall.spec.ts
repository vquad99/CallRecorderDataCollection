// Journey: a phone-call conversation from start to QC, through the interface, by the people who
// would do it (D-101, D-103). The backend talks to a stand-in for TxContact
// (backend/tests/fake_txcontact.py): no phone rings, everything else is real (browser, backend,
// database, file storage). Skipped when the backend has no phone provider configured.
// Requirements: TEL-002, TEL-004, TEL-010, TEL-018, TEL-036, TEL-037, TEL-038, PART-016
import { expect, test } from "@playwright/test";

import {
  ADMIN_EMAIL,
  api,
  consentBoth,
  playToEnd,
  requireSetup,
  runCode,
  SEEDED,
  SEEDED_PASSWORD,
  signIn,
} from "./support";

interface Participant {
  id: string;
  participant_code: string;
}

/** An Indian mobile number that no other run uses (the last digits pick the stand-in's case). */
function phone(ending: string): string {
  const random = String(Math.floor(Math.random() * 1e9)).padStart(9, "0");
  return `+919${random.slice(0, 9 - ending.length)}${ending}`;
}

test("a moderator calls, confirms both people, closes the call and sends the recording to QC", async ({
  browser,
}, info) => {
  requireSetup();
  const code = runCode(info);
  const admin = await (await browser.newContext()).newPage();
  await signIn(admin, ADMIN_EMAIL, SEEDED_PASSWORD);
  const status = await api<{ configured: boolean }>(admin, "GET", "/api/v1/telephony/status");
  test.skip(!status.configured, "the backend has no phone provider configured (TXCONTACT_*)");

  // Set-up through the API as the Super Admin: a telephony project, two people with phone
  // numbers, and tasks given to the seeded moderator.
  const project = await api<{ id: string }>(admin, "POST", "/api/v1/projects", {
    code,
    name: `Journey ${code}`,
    allows_telephony: true,
    allows_face_to_face: false,
  });
  await api(admin, "POST", `/api/v1/projects/${project.id}/status`, { status: "ACTIVE" });
  await api(admin, "PUT", `/api/v1/projects/${project.id}/languages`, {
    languages: [{ language_code: "hi", dialect: "" }],
  });
  const found = await api<{ items: { id: string; email: string }[] }>(
    admin,
    "GET",
    `/api/v1/users?search=${encodeURIComponent(SEEDED.moderator)}`,
  );
  const moderatorId = found.items.find((u) => u.email === SEEDED.moderator)?.id ?? "";
  await api(admin, "POST", `/api/v1/projects/${project.id}/members`, { user_id: moderatorId });
  const person = (label: string, number: string) =>
    api<Participant>(admin, "POST", `/api/v1/projects/${project.id}/participants`, {
      display_label: `${label} ${code}`,
      language_code: "hi",
      phone: number,
    });
  const asha = await person("Asha", phone("123"));
  const bina = await person("Bina", phone("456"));
  const refused = await person("Refused", phone("8888")); // the stand-in refuses this number
  const task = async (a: Participant) => {
    const t = await api<{ id: string; task_code: string }>(admin, "POST", "/api/v1/tasks", {
      project_id: project.id,
      recording_mode: "TELEPHONY",
      participant_a_id: a.id,
      participant_b_id: bina.id,
    });
    await api(admin, "POST", `/api/v1/tasks/${t.id}/assign`, { user_id: moderatorId });
    return t;
  };
  const main = await task(asha);
  const blocked = await task(refused);

  await test.step("the Super Admin gives the moderator a phone seat", async () => {
    await admin.goto(`/admin/users/${moderatorId}`);
    await admin.getByLabel("Phone seat").fill(`seat-${code}`);
    await admin.getByRole("button", { name: "Save phone seat" }).click();
    await expect(admin.getByText("Phone seat saved.")).toBeVisible();
  });

  const moderator = await (await browser.newContext()).newPage();
  await signIn(moderator, SEEDED.moderator, SEEDED_PASSWORD);

  await test.step("a call the provider refuses is shown as refused, not as a call", async () => {
    await moderator.goto(`/tasks/${blocked.id}`);
    await moderator.getByRole("button", { name: "Start session" }).click();
    // D-127: nobody is called before both have agreed on their consent form.
    await expect(moderator.getByRole("button", { name: "Start call" })).toBeDisabled();
    await expect(moderator.getByText(/has not agreed on the consent form yet/)).toBeVisible();
    await consentBoth(moderator);
    await moderator.getByRole("button", { name: "Start call" }).click();
    await expect(moderator.getByRole("alert")).toContainText("The last call could not be placed");
    await expect(moderator.getByText("Call could not be placed").first()).toBeVisible();
    await expect(moderator.getByRole("button", { name: "Start call" })).toBeVisible();
  });

  await test.step("the moderator calls and follows one button at a time", async () => {
    await moderator.goto(`/tasks/${main.id}`);
    await moderator.getByRole("button", { name: "Start session" }).click();
    await consentBoth(moderator);
    await moderator.getByRole("button", { name: "Start call" }).click();
    await expect(moderator.getByRole("heading", { name: "On the call" })).toBeVisible();
    // The call's history in plain words; the provider's own answer is for the Super Admin only.
    await expect(
      moderator.getByText("The phone system is ringing participant A").first(),
    ).toBeVisible();
    await expect(moderator.getByText(/TXCONTACT answered HTTP 200/)).toHaveCount(0);
    // A answers: one click says so and rings B into the same call (D-111).
    await moderator.getByRole("button", { name: /A answered/ }).click();
    await expect(
      moderator.getByText(/The phone system is ringing participant B/).first(),
    ).toBeVisible();
    // B answers: one click says so and marks where the conversation starts (D-113).
    await moderator.getByRole("button", { name: /B answered/ }).click();
    await expect(moderator.getByRole("button", { name: "Stop and close call" })).toBeVisible();
    // About four seconds of conversation: only that part is delivered.
    await moderator.waitForTimeout(4_000);
  });

  await test.step("the moderator stops and closes; then the recording arrives by itself", async () => {
    await moderator.getByRole("button", { name: "Stop and close call" }).click();
    await expect(moderator.getByRole("heading", { name: "Check the call recording" })).toBeVisible({
      timeout: 90_000,
    });
    // The delivered file: 16 kHz, cut to the marked part (about 4 s plus a second each side).
    const delivered = moderator.getByRole("row").filter({ hasText: "16000 Hz, mono" });
    await expect(delivered).toContainText(/[4-9] s/);
  });

  await test.step("the moderator listens, sees the check passed, and sends it to QC", async () => {
    await moderator.getByRole("button", { name: "Listen" }).first().click();
    const played = await playToEnd(moderator, "Recording");
    expect(played.error).toBeNull();
    expect(played.ended).toBe(true);
    // The stand-in's file is 12 s from the moment A was rung; the delivery file is cut to the
    // marked part, about 4 s, plus one second each side (D-113).
    expect(played.duration).toBeGreaterThanOrEqual(4);
    expect(played.duration).toBeLessThan(10);
    // One channel is what a phone call has: the automatic check does not fail it (D-103).
    await expect(moderator.getByRole("heading", { name: "Audio quality" })).toBeVisible();
    await expect(moderator.getByText("Failed", { exact: true })).toHaveCount(0);
    await moderator.getByRole("button", { name: "Send to QC" }).click();
    await expect(moderator.locator(".page-header .badge").first()).toHaveText("Audio QC");
    await expect(moderator.getByRole("button", { name: "Send to QC" })).toHaveCount(0);
  });

  await test.step("the admin sees the call counted, listed and described in the details file", async () => {
    await admin.goto("/calls");
    await admin.getByLabel("Project", { exact: true }).selectOption(project.id);
    await expect(admin.getByRole("heading", { name: "Calls per day" })).toBeVisible();
    // Every call is on its own tab (UI review 2026-11-17).
    await admin.getByRole("tab", { name: "All calls" }).click();
    const row = admin.getByRole("row").filter({ hasText: main.task_code });
    await expect(row).toContainText("Recording stored");
    await expect(row).toContainText(/[4-9] s/);
    await expect(admin.getByRole("row").filter({ hasText: blocked.task_code })).toContainText(
      "Call could not be placed",
    );
    const figures = await api<{
      calls: number;
      recorded: number;
      dial_failed: number;
      funnel: { sent_to_qc: number };
      checklist: Record<string, number>;
    }>(admin, "GET", `/api/v1/telephony/analytics?project_id=${project.id}&days=7`);
    expect([figures.calls, figures.recorded, figures.dial_failed]).toEqual([2, 1, 1]);
    expect(figures.funnel.sent_to_qc).toBe(1);
    expect(figures.checklist).toMatchObject({ A_JOINED: 1, B_JOINED: 1 });

    const recordings = await api<{ id: string; assets: { kind: string }[] }[]>(
      admin,
      "GET",
      `/api/v1/tasks/${main.id}/recordings`,
    );
    expect(recordings[0]?.assets.map((a) => a.kind).sort()).toEqual([
      "PROVIDER_ORIGINAL_MIXED",
      "TELEPHONY_DERIVED_PCM",
    ]);
    const details = await api<{
      call: { agent_seat: string; note: string; checklist: Record<string, string | null> };
    }>(admin, "GET", `/api/v1/recordings/${recordings[0]?.id}/metadata`);
    expect(details.call.agent_seat).toBe(`seat-${code}`);
    expect(details.call.checklist.A_JOINED).toBeTruthy();
    expect(details.call.checklist.QUALITY_OK).toBeNull();
  });

  await test.step("the admin opens everything about the person who was called (D-104)", async () => {
    await admin.goto("/participants");
    await admin.getByLabel("Project", { exact: true }).selectOption(project.id);
    const row = admin.getByRole("row").filter({ hasText: asha.participant_code });
    await row.getByRole("button", { name: "View" }).click();
    const panel = admin.getByRole("dialog", { name: "Participant details" });
    await expect(panel.getByRole("heading", { name: "Sessions" })).toBeVisible();
    for (const title of ["Profile", "Work in this project", "Personal link", "Consent form"]) {
      await expect(panel.getByRole("heading", { name: title, exact: true })).toBeVisible();
    }
    await expect(panel).toContainText(`Asha ${code}`);
    await expect(panel).toContainText("Phone calls to them1");
    await expect(panel).toContainText("Calls with a recording1");
    const session = panel.getByRole("row").filter({ hasText: main.task_code });
    await expect(session).toContainText("Phone call");
    await expect(session).toContainText("Participant A");
    await expect(session).toContainText(bina.participant_code);
    await expect(session).toContainText("Agreed");
    await expect(session).toContainText(/[4-9] s/);
    await session.getByRole("link", { name: main.task_code }).click();
    await expect(admin).toHaveURL(new RegExp(`/tasks/${main.id}$`));
  });

  await test.step("the moderator has a list of their own calls, and no figures (D-104)", async () => {
    await moderator.goto("/calls");
    await expect(moderator.getByRole("heading", { name: "My phone calls" })).toBeVisible();
    await expect(moderator.getByRole("link", { name: main.task_code })).toBeVisible();
    await expect(moderator.getByRole("heading", { name: "Calls per day" })).toHaveCount(0);
    await expect(moderator.getByRole("button", { name: "Download calls (CSV)" })).toHaveCount(0);
    const figures = await moderator.request.get("/api/v1/telephony/analytics");
    expect(figures.status()).toBe(403);
  });
});
