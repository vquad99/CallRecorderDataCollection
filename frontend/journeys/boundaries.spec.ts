// Journey: people try pages and records that are not theirs, by menu and by typing addresses
// (owner's test list, Option D). Requirements: ROLE-004..007, ROLE-011, AUTH-003, AUTH-011
import { expect, test, type Page } from "@playwright/test";

import {
  ADMIN_EMAIL,
  requireSetup,
  runCode,
  SEEDED,
  SEEDED_PASSWORD,
  setUpTask,
  signIn,
} from "./support";

async function menu(page: Page): Promise<string[]> {
  return page.getByRole("navigation", { name: "Main" }).getByRole("link").allTextContents();
}

test("each role reaches only its own pages and records", async ({ browser }, info) => {
  requireSetup();
  const admin = await (await browser.newContext()).newPage();
  await signIn(admin, ADMIN_EMAIL, SEEDED_PASSWORD);
  // A task in a project the moderator belongs to, but assigned to nobody.
  const setup = await setUpTask(admin, runCode(info), [SEEDED.moderator, SEEDED.transcriber]);

  await test.step("a moderator sees only moderator pages", async () => {
    const page = await (await browser.newContext()).newPage();
    await signIn(page, SEEDED.moderator, SEEDED_PASSWORD);
    expect(await menu(page)).toEqual(["Projects", "Tasks", "System status"]);
    for (const path of [
      "/admin/users",
      "/admin/audit",
      "/admin/settings",
      "/projects/new",
      "/tasks/new",
    ]) {
      await page.goto(path);
      await expect(page.getByRole("heading", { name: "No access" }), path).toBeVisible();
    }
    await page.goto(`/tasks/${setup.taskId}`);
    await expect(page.getByRole("heading", { name: "Not found" })).toBeVisible();
    await page.goto(`/tasks/${setup.taskId}/record`);
    await expect(page.getByRole("heading", { name: "Not found" })).toBeVisible();

    await test.step("after signing out, going back shows sign-in, not data", async () => {
      await page.goto(`/projects/${setup.projectId}`);
      await expect(page.getByRole("heading", { level: 1 })).toContainText("Journey");
      await page.getByRole("button", { name: "Sign out" }).click();
      await expect(page.getByRole("heading", { name: "Sign in" })).toBeVisible();
      await page.goBack();
      await expect(page.getByRole("heading", { name: "Sign in" })).toBeVisible();
      expect((await page.request.get("/api/v1/auth/me")).status()).toBe(401);
    });
  });

  await test.step("a transcriber sees no tasks before any is assigned", async () => {
    const page = await (await browser.newContext()).newPage();
    await signIn(page, SEEDED.transcriber, SEEDED_PASSWORD);
    await page.goto(`/tasks/${setup.taskId}`);
    await expect(page.getByRole("heading", { name: "Not found" })).toBeVisible();
    await page.goto(`/projects/${setup.projectId}/participants`);
    await expect(page.getByRole("cell", { name: "Hidden" }).first()).toBeVisible();
    await expect(page.getByRole("button", { name: "Add participant" })).toHaveCount(0);
  });

  await test.step("a client viewer has no task pages at all", async () => {
    const page = await (await browser.newContext()).newPage();
    await signIn(page, SEEDED.clientViewer, SEEDED_PASSWORD);
    expect(await menu(page)).toEqual(["Projects", "System status"]);
    await page.goto("/tasks");
    await expect(page.getByRole("heading", { name: "No access" })).toBeVisible();
    await page.goto(`/projects/${setup.projectId}`);
    await expect(page.getByRole("heading", { name: "Not found" })).toBeVisible();
  });
});
