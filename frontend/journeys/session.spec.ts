// Journey: the moderator's session ends in the middle of a recording (an administrator ends it).
// Capture goes on, the page asks for a new sign-in, and once the moderator signs in again in
// another tab the waiting parts are sent; nothing is lost (owner's list, O1).
// Requirements: FTF-009, FTF-010, AUTH-010
import { expect, test } from "@playwright/test";

import {
  ADMIN_EMAIL,
  api,
  requireSetup,
  runCode,
  SEEDED,
  SEEDED_PASSWORD,
  setUpTask,
  signIn,
} from "./support";

test("a session ended mid-recording loses nothing once the moderator signs in again", async ({
  browser,
}, info) => {
  requireSetup();
  const admin = await (await browser.newContext()).newPage();
  await signIn(admin, ADMIN_EMAIL, SEEDED_PASSWORD);
  const setup = await setUpTask(admin, runCode(info), [SEEDED.moderator], SEEDED.moderator);

  const context = await browser.newContext();
  const page = await context.newPage();
  await signIn(page, SEEDED.moderator, SEEDED_PASSWORD);
  await page.goto(`/tasks/${setup.taskId}`);
  await page.getByLabel("Move to").selectOption("IN_PROGRESS");
  await page.getByRole("button", { name: "Apply" }).click();
  await page.getByRole("link", { name: "Open the recorder" }).click();
  await page.getByRole("button", { name: "Allow microphone" }).click();
  await page.getByRole("button", { name: "Start recording" }).click();
  await expect(page.getByText(/Saved parts: [1-9]\d*;/)).toBeVisible({ timeout: 20_000 });

  await test.step("an administrator ends every session of the moderator", async () => {
    const users = await api<{ items: { id: string; email: string }[] }>(
      admin,
      "GET",
      `/api/v1/users?search=${encodeURIComponent(SEEDED.moderator)}`,
    );
    const id = users.items.find((u) => u.email === SEEDED.moderator)?.id ?? "";
    await api(admin, "POST", `/api/v1/users/${id}/sessions/revoke`);
    await expect(page.getByText(/Your session has ended\. Sign in again in a new tab/)).toBeVisible(
      {
        timeout: 30_000,
      },
    );
    await expect(page.getByText(/Recording \d:\d\d/)).toBeVisible();
  });

  await test.step("the moderator signs in again in another tab; the waiting parts are sent", async () => {
    const other = await context.newPage();
    await signIn(other, SEEDED.moderator, SEEDED_PASSWORD);
    await other.close();
    await expect(page.getByText(/Your session has ended/)).toHaveCount(0, { timeout: 30_000 });
    await expect(page.getByText(/Saved parts: [3-9]; waiting to upload: 0\./)).toBeVisible({
      timeout: 60_000,
    });
    await page.getByRole("button", { name: "Stop and save" }).click();
    await expect(page.getByRole("heading", { name: "Recording saved" })).toBeVisible({
      timeout: 60_000,
    });
  });

  await test.step("the stored recording has every part, with no gap", async () => {
    const [recording] = await api<
      { state: string; chunks_received: number; saved_seconds: number }[]
    >(admin, "GET", `/api/v1/tasks/${setup.taskId}/recordings`);
    expect(recording?.state).toBe("READY");
    expect(recording?.chunks_received).toBeGreaterThanOrEqual(4);
    expect(recording?.saved_seconds).toBeGreaterThan(5 * ((recording?.chunks_received ?? 1) - 1));
  });
});
