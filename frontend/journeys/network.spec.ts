// Journey: the moderator's connection drops in the middle of a recording; the page keeps capturing,
// says so, sends the waiting parts when the connection returns, and nothing is lost
// (owner's test list, Option H). Requirements: FTF-009, FTF-010, STOR-004
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

test("a network drop mid-recording loses nothing", async ({ browser }, info) => {
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
  await expect(page.getByText(/Saved parts: 1;/)).toBeVisible({ timeout: 20_000 });

  await test.step("the connection drops: capture goes on and the page says parts are waiting", async () => {
    await context.setOffline(true);
    await expect(
      page.getByText("Connection problem. Saved parts are kept and sending is retried."),
    ).toBeVisible({
      timeout: 20_000,
    });
    await page.waitForTimeout(8_000);
    await expect(page.getByText(/Recording \d:\d\d/)).toBeVisible();
  });

  await test.step("the connection returns: the waiting parts are sent in order", async () => {
    await context.setOffline(false);
    await expect(page.getByText(/Saved parts: [4-9]; waiting to upload: 0\./)).toBeVisible({
      timeout: 60_000,
    });
    await expect(page.getByText("Connection problem.", { exact: false })).toHaveCount(0);
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
    expect(recording?.chunks_received).toBeGreaterThanOrEqual(5);
    // Every part but the last is 5 s; completion refuses any gap, so the length is continuous.
    expect(recording?.saved_seconds).toBeGreaterThan(5 * ((recording?.chunks_received ?? 1) - 1));
  });
});
