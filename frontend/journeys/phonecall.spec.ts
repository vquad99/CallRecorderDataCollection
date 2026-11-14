// Journey: a phone-call conversation from start to QC, through the interface, by the people who
// would do it (D-101, D-103). The backend talks to a stand-in for TxContact
// (backend/tests/fake_txcontact.py): no phone rings, everything else is real (browser, backend,
// database, file storage). Skipped when the backend has no phone provider configured.
// Requirements: TEL-002, TEL-010, TEL-018, TEL-036, TEL-037, TEL-038, PART-016
import { expect, test, type Page } from "@playwright/test";

import {
  ADMIN_EMAIL,
  api,
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

async function giveConsent(page: Page, people: Participant[]) {
  for (const p of people) {
    await page
      .getByRole("group", { name: `Consent of ${p.participant_code}` })
      .getByRole("button", { name: "Consent given" })
      .click();
  }
  await expect(page.getByText("Given").first()).toBeVisible();
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

  await test.step("the Super Admin gives the moderator a TxContact agent seat", async () => {
    await admin.goto(`/admin/users/${moderatorId}`);
    await admin.getByLabel("TxContact agent seat").fill(`seat-${code}`);
    await admin.getByRole("button", { name: "Save agent seat" }).click();
    await expect(admin.getByText("Agent seat saved.")).toBeVisible();
  });

  const moderator = await (await browser.newContext()).newPage();
  await signIn(moderator, SEEDED.moderator, SEEDED_PASSWORD);

  await test.step("a call the provider refuses is shown as refused, not as a call", async () => {
    await moderator.goto(`/tasks/${blocked.id}`);
    await moderator.getByRole("button", { name: "Start session" }).click();
    await moderator.getByRole("button", { name: "Start call" }).click();
    await expect(moderator.getByRole("alert")).toContainText("The last call could not be placed");
    await expect(moderator.getByText("Call could not be placed").first()).toBeVisible();
    await expect(moderator.getByRole("button", { name: "Start call" })).toBeVisible();
  });

  await test.step("the moderator starts the call and confirms both people", async () => {
    await moderator.goto(`/tasks/${main.id}`);
    await moderator.getByRole("button", { name: "Start session" }).click();
    await moderator.getByRole("button", { name: "Start call" }).click();
    await expect(moderator.getByRole("heading", { name: "On the call" })).toBeVisible();
    // What the provider answered is on the page, in the call's history.
    await expect(moderator.getByText(/TXCONTACT answered HTTP 200/)).toBeVisible();
    // The call cannot be closed before both people are confirmed on it.
    await expect(moderator.getByRole("button", { name: "Close call" })).toBeDisabled();
    await moderator.getByRole("checkbox", { name: /Participant A is on the call/ }).check();
    await moderator.getByRole("checkbox", { name: /Participant B is on the call/ }).check();
    await moderator.getByRole("checkbox", { name: /I am muted and listening/ }).check();
    await expect(moderator.getByRole("button", { name: "Close call" })).toBeEnabled();
  });

  await test.step("closing needs both consents; then the recording arrives by itself", async () => {
    await moderator.getByRole("button", { name: "Close call" }).click();
    await expect(moderator.getByText(/Record consent for participant A and B/)).toBeVisible();
    await giveConsent(moderator, [asha, bina]);
    await moderator.getByLabel("Note for the record (optional)").fill("clear line");
    await moderator.getByRole("button", { name: "Close call" }).click();
    await expect(moderator.getByRole("heading", { name: "Check the call recording" })).toBeVisible({
      timeout: 90_000,
    });
    await expect(moderator.getByText(/Recording stored: 8000 Hz, 1 channel/)).toBeVisible();
  });

  await test.step("the moderator listens, sees the check passed, and sends it to QC", async () => {
    await moderator.getByRole("button", { name: "Listen" }).first().click();
    const played = await playToEnd(moderator, "Recording being checked");
    expect(played.error).toBeNull();
    expect(played.ended).toBe(true);
    expect(Math.round(played.duration)).toBe(12);
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
    const row = admin.getByRole("row").filter({ hasText: main.task_code });
    await expect(row).toContainText("Recording stored");
    await expect(row).toContainText("12 s");
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
    expect(figures.checklist).toMatchObject({ A_JOINED: 1, B_JOINED: 1, MODERATOR_MUTED: 1 });

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
    expect(details.call.note).toBe("clear line");
    expect(details.call.checklist.A_JOINED).toBeTruthy();
    expect(details.call.checklist.QUALITY_OK).toBeNull();
  });

  await test.step("the admin opens everything about the person who was called (D-104)", async () => {
    await admin.goto("/participants");
    await admin.getByLabel("Project", { exact: true }).selectOption(project.id);
    const row = admin.getByRole("row").filter({ hasText: asha.participant_code });
    await row.getByRole("button", { name: "View" }).click();
    const panel = admin.getByRole("region", { name: "Participant details" });
    await expect(panel.getByRole("heading", { name: "Sessions" })).toBeVisible();
    for (const title of ["Profile", "Work in this project", "Personal link", "Consent form"]) {
      await expect(panel.getByRole("heading", { name: title, exact: true })).toBeVisible();
    }
    await expect(panel).toContainText(`Asha ${code}`);
    await expect(panel).toContainText("Phone calls to them1");
    await expect(panel).toContainText("Calls with a recording1");
    const session = panel.getByRole("row").filter({ hasText: main.task_code });
    await expect(session).toContainText("Telephony");
    await expect(session).toContainText("Participant A");
    await expect(session).toContainText(bina.participant_code);
    await expect(session).toContainText("Agreed");
    await expect(session).toContainText("12 s");
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
