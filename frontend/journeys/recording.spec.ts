// Journey: from an empty project to a recorded face-to-face conversation, through the interface
// only, by the people who would do it (owner's test list, Option D).
// Requirements: USER-001, USER-002, AUTH-004, PROJ-001, PROJ-002, PROJ-009, PART-001, TASK-001,
// TASK-002, TASK-003, PART-006, FTF-001..FTF-014, AUDIO-014, STOR-005, SEC-001
import { expect, test, type Page } from "@playwright/test";

import {
  ADMIN_EMAIL,
  api,
  emailedLink,
  NEW_PASSWORD,
  playToEnd,
  requireSetup,
  runCode,
  SEEDED_PASSWORD,
  sha256,
  signIn,
} from "./support";

/** Select the option whose text names this participant (the label also carries the code). */
async function pickParticipant(page: Page, label: string, name: string) {
  const option = page.getByLabel(label).locator("option", { hasText: name });
  await expect(option).toHaveCount(1);
  await page.getByLabel(label).selectOption((await option.getAttribute("value")) ?? "");
}

interface Asset {
  id: string;
  kind: string;
  sample_rate: number;
  bit_depth: number;
  channels: number;
  size_bytes: number;
  sha256: string;
}

test("set up a project, invite a moderator, and record a face-to-face conversation", async ({
  browser,
}, info) => {
  requireSetup();
  const code = runCode(info);
  const name = `Journey ${code}`;
  const moderatorEmail = `moderator.${code.toLowerCase()}@example.org`;
  const admin = await (await browser.newContext()).newPage();
  const moderator = await (await browser.newContext()).newPage();
  let projectUrl = "";
  let taskUrl = "";

  await test.step("the Super Admin creates and opens the project", async () => {
    await signIn(admin, ADMIN_EMAIL, SEEDED_PASSWORD);
    await admin
      .getByRole("navigation", { name: "Main" })
      .getByRole("link", { name: "Projects" })
      .click();
    await admin.getByRole("link", { name: "New project" }).click();
    await admin.getByLabel(/^Project code/).fill(code);
    await admin.getByLabel(/^Name/).fill(name);
    await admin.getByRole("checkbox", { name: "Face-to-face" }).check();
    await admin.getByRole("button", { name: "Create project" }).click();
    await expect(admin.getByRole("heading", { level: 1 })).toHaveText(`${code} · ${name}`);
    projectUrl = new URL(admin.url()).pathname;
    await admin.getByLabel("Change status to").selectOption("ACTIVE");
    await admin.getByRole("button", { name: "Change status" }).click();
    await expect(admin.getByText("This project accepts new work.")).toBeVisible();
    await admin.getByRole("link", { name: "Languages" }).click();
    await admin.getByLabel(/^Language code/).fill("hi");
    await admin.getByRole("button", { name: "Add language" }).click();
    await expect(admin.getByRole("listitem").filter({ hasText: /^hi/ })).toBeVisible();
  });

  await test.step("the Super Admin invites a moderator by email", async () => {
    const sent = Date.now() - 1000;
    await admin
      .getByRole("navigation", { name: "Main" })
      .getByRole("link", { name: "Users" })
      .click();
    await admin.getByRole("link", { name: "Add user" }).click();
    await admin.getByLabel(/^Email/).fill(moderatorEmail);
    await admin.getByLabel(/^Name/).fill(`Moderator ${code}`);
    await admin.getByRole("checkbox", { name: "Moderator" }).check();
    await admin.getByRole("button", { name: "Add and send invitation" }).click();
    await expect(admin.getByText(`${moderatorEmail} was invited by email`)).toBeVisible();

    await test.step("the moderator sets a password from the email and signs in", async () => {
      await moderator.goto(await emailedLink(moderatorEmail, sent));
      await moderator.getByLabel(/^New password/).fill(NEW_PASSWORD);
      await moderator.getByLabel(/^Repeat new password/).fill(NEW_PASSWORD);
      await moderator.getByRole("button", { name: "Set password" }).click();
      await expect(moderator.getByText("Your password is set. You can sign in now.")).toBeVisible();
      await signIn(moderator, moderatorEmail, NEW_PASSWORD);
    });
  });

  await test.step("the Super Admin adds the moderator and two participants to the project", async () => {
    await admin.goto(`${projectUrl}/team`);
    await admin.getByLabel("Find by name or email").fill(moderatorEmail);
    await admin.getByRole("button", { name: "Search" }).click();
    await admin
      .getByRole("listitem")
      .filter({ hasText: moderatorEmail })
      .getByRole("button", { name: "Add" })
      .click();
    await expect(admin.getByText(`${moderatorEmail} added.`)).toBeVisible();
    await admin
      .getByRole("navigation", { name: "Project sections" })
      .getByRole("link", { name: "Participants" })
      .click();
    for (const person of ["Asha", "Bina"]) {
      await admin.getByRole("button", { name: "Add participant" }).first().click();
      await admin.getByLabel(/^Name or label/).fill(`${person} ${code}`);
      await admin.getByLabel(/^Language code/).fill("hi");
      await admin.getByRole("button", { name: "Add participant" }).last().click();
      await expect(admin.getByRole("cell", { name: `${person} ${code}` })).toBeVisible();
    }
  });

  await test.step("the Super Admin creates the task and assigns the moderator", async () => {
    await admin
      .getByRole("navigation", { name: "Main" })
      .getByRole("link", { name: "Tasks" })
      .click();
    await admin.getByRole("link", { name: "New task" }).click();
    await admin.getByLabel("Project (active projects)").selectOption({ label: `${code} ${name}` });
    await admin.getByLabel("Recording mode").selectOption("FACE_TO_FACE");
    await pickParticipant(admin, "Participant A", `Asha ${code}`);
    await pickParticipant(admin, "Participant B", `Bina ${code}`);
    await admin.getByRole("button", { name: "Create task" }).click();
    await expect(admin.getByRole("heading", { level: 1, name: /^Task T\d{6}$/ })).toBeVisible();
    taskUrl = new URL(admin.url()).pathname;
    await admin
      .getByLabel("Moderator")
      .selectOption({ label: `Moderator ${code} (${moderatorEmail})` });
    await admin.getByRole("button", { name: "Assign" }).click();
    await expect(admin.getByText(`Moderator ${code}`).first()).toBeVisible();
  });

  await test.step("the moderator finds the task, starts it and records consent", async () => {
    await moderator
      .getByRole("navigation", { name: "Main" })
      .getByRole("link", { name: "Tasks" })
      .click();
    const taskCode =
      (await admin.getByRole("heading", { level: 1 }).textContent())?.replace("Task ", "") ?? "";
    await moderator.getByRole("link", { name: taskCode }).click();
    await moderator.getByLabel("Move to").selectOption("IN_PROGRESS");
    await moderator.getByRole("button", { name: "Apply" }).click();
    await expect(moderator.getByText("In progress").first()).toBeVisible();
    for (const which of ["A", "B"]) {
      await moderator
        .locator(".actions")
        .filter({ hasText: `Participant ${which}` })
        .getByRole("button", { name: "Consent given" })
        .click();
      await expect(
        moderator.locator(".actions").filter({ hasText: `Participant ${which}` }),
      ).toBeVisible();
    }
  });

  await test.step("the moderator records the conversation and plays it back", async () => {
    await moderator.getByRole("link", { name: "Open the recorder" }).click();
    await moderator.getByRole("button", { name: "Allow microphone" }).click();
    await moderator.getByRole("button", { name: "Start recording" }).click();
    await expect(moderator.getByText(/Recording 0:0[1-9]/)).toBeVisible();
    await moderator.waitForTimeout(7_000);
    await moderator.getByRole("button", { name: "Stop and save" }).click();
    await expect(moderator.getByRole("heading", { name: "Recording saved" })).toBeVisible({
      timeout: 60_000,
    });
    await expect(
      moderator.getByRole("row").filter({ hasText: "16 kHz delivery file" }),
    ).toContainText("16000 Hz, 16-bit, mono (pcm_s16le)");
    await expect(moderator.getByRole("row").filter({ hasText: "Original capture" })).toContainText(
      "32-bit",
    );
    await moderator.getByRole("button", { name: "Listen" }).click();
    const played = await playToEnd(moderator, "Recorded conversation");
    expect(played.error).toBeNull();
    expect(played.ended).toBe(true);
    expect(played.duration).toBeGreaterThan(5);
    await expect(moderator.getByText("The task is now marked as recorded.")).toBeVisible();
  });

  await test.step("the task shows as recorded, with its history", async () => {
    await admin.goto(taskUrl);
    await expect(admin.getByText("Recorded").first()).toBeVisible();
    await expect(admin.getByText(/IN_PROGRESS -> RECORDED/)).toBeVisible();
  });

  await test.step("the Super Admin downloads both files through short-lived links", async () => {
    const taskId = taskUrl.split("/").pop() ?? "";
    const [recording] = await api<{ id: string }[]>(
      admin,
      "GET",
      `/api/v1/tasks/${taskId}/recordings`,
    );
    const detail = await api<{ assets: Asset[] }>(
      admin,
      "GET",
      `/api/v1/recordings/${recording?.id}`,
    );
    expect(detail.assets.map((a) => a.kind).sort()).toEqual([
      "BROWSER_ORIGINAL",
      "FTF_DERIVED_PCM",
    ]);
    for (const asset of detail.assets) {
      const link = await api<{ url: string; expires_in: number }>(
        admin,
        "POST",
        `/api/v1/assets/${asset.id}/url`,
        { purpose: "download" },
      );
      expect(link.expires_in).toBe(300);
      const file = await admin.request.get(link.url);
      expect(file.status()).toBe(200);
      const body = await file.body();
      expect(body.length).toBe(asset.size_bytes);
      expect(sha256(body)).toBe(asset.sha256);
    }
  });

  await test.step("the audit log shows what happened", async () => {
    await admin
      .getByRole("navigation", { name: "Main" })
      .getByRole("link", { name: "Audit log" })
      .click();
    for (const action of [
      "task.created",
      "consent.recorded",
      "recording.started",
      "recording.completed",
    ]) {
      await admin.getByLabel("Action").fill(action);
      await expect(admin.getByText(action).first()).toBeVisible();
    }
  });
});
