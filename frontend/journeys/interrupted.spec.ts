// Journey: the moderator's tab closes mid-recording; what reached the server is kept, the moderator
// is told exactly how much, and can finish with it (owner's test list, Option D).
// Requirements: FTF-009, FTF-010, FTF-011, STOR-004, TASK-003
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

test("an interrupted recording keeps the saved audio and can be finished", async ({
  browser,
}, info) => {
  requireSetup();
  const admin = await (await browser.newContext()).newPage();
  await signIn(admin, ADMIN_EMAIL, SEEDED_PASSWORD);
  const setup = await setUpTask(admin, runCode(info), [SEEDED.moderator], SEEDED.moderator);

  const context = await browser.newContext();
  const first = await context.newPage();
  let parts = 0;
  let keptSeconds = 0;
  await test.step("the moderator starts recording and the tab closes after the first part is saved", async () => {
    await signIn(first, SEEDED.moderator, SEEDED_PASSWORD);
    await first.goto(`/tasks/${setup.taskId}`);
    await first.getByLabel("Move to").selectOption("IN_PROGRESS");
    await first.getByRole("button", { name: "Apply" }).click();
    await first.getByRole("link", { name: "Open the recorder" }).click();
    await first.getByRole("button", { name: "Allow microphone" }).click();
    await first.getByRole("button", { name: "Start recording" }).click();
    // At least one 5-second part is on the server (the count may already be past 1 when seen).
    const saved = first.getByText(/Saved parts: [1-9]\d*;/);
    await expect(saved).toBeVisible({ timeout: 20_000 });
    parts = Number(/Saved parts: (\d+);/.exec((await saved.textContent()) ?? "")?.[1]);
    await first.close({ runBeforeUnload: false });
  });

  await test.step("on return the moderator is told what was kept and keeps it", async () => {
    const again = await context.newPage();
    await again.goto(`/tasks/${setup.taskId}/record`);
    const notice = again
      .getByRole("alert")
      .filter({ hasText: "An earlier recording did not finish" });
    await expect(notice).toContainText("of audio reached the server and is kept.");
    // What the server kept: the parts seen before the tab closed, or one more that was on its way.
    const [, minutes, seconds] = /(\d+):(\d\d) of audio reached the server/.exec(
      (await notice.textContent()) ?? "",
    ) ?? ["", "0", "0"];
    keptSeconds = 60 * Number(minutes) + Number(seconds);
    expect([5 * parts, 5 * (parts + 1)]).toContain(keptSeconds);
    const kept = `${minutes}:${seconds}`;
    await notice.getByRole("button", { name: `Keep the saved ${kept}` }).click();
    await expect(notice).toHaveCount(0, { timeout: 30_000 });
  });

  await test.step("the kept recording is processed and the task is recorded", async () => {
    await expect
      .poll(
        async () =>
          (
            await api<{ state: string }[]>(admin, "GET", `/api/v1/tasks/${setup.taskId}/recordings`)
          )[0]?.state,
        { timeout: 60_000 },
      )
      .toBe("READY");
    const [recording] = await api<{ interrupted: boolean; saved_seconds: number }[]>(
      admin,
      "GET",
      `/api/v1/tasks/${setup.taskId}/recordings`,
    );
    expect(recording?.interrupted).toBe(true);
    expect(recording?.saved_seconds).toBe(keptSeconds);
    await admin.goto(`/tasks/${setup.taskId}`);
    await expect(admin.getByText(/IN_PROGRESS -> RECORDED/)).toBeVisible();
  });
});
