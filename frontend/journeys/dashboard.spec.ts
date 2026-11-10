// Journey: every role opens the app on its own dashboard, and two-step sign-in asks for the
// password before it starts (D-064, D-065). Requirements: DASH-001, DASH-004, ROLE-007, AUTH-008
import { expect, test } from "@playwright/test";

import { ADMIN_EMAIL, requireSetup, SEEDED, SEEDED_PASSWORD, signIn } from "./support";

test("each role lands on its own dashboard view", async ({ browser }) => {
  requireSetup();

  await test.step("a client viewer sees progress only", async () => {
    const page = await (await browser.newContext()).newPage();
    await signIn(page, SEEDED.clientViewer, SEEDED_PASSWORD);
    await expect(page).toHaveURL(/\/dashboard$/);
    await expect(
      page.getByRole("heading", { level: 1, name: "Collection progress" }),
    ).toBeVisible();
    await expect(page.getByRole("heading", { name: "Hours per day" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Needs attention" })).toHaveCount(0);
    await expect(page.getByRole("heading", { name: "Moderator output" })).toHaveCount(0);
    await expect(page.getByRole("heading", { name: "Tasks by status" })).toHaveCount(0);
    const body = await (await page.request.get("/api/v1/dashboard")).json();
    expect(body.view).toBe("client");
    expect([body.queues, body.team, body.storage_bytes, body.tasks_by_status]).toEqual([
      null,
      null,
      null,
      null,
    ]);
  });

  await test.step("a moderator sees their own work", async () => {
    const page = await (await browser.newContext()).newPage();
    await signIn(page, SEEDED.moderator, SEEDED_PASSWORD);
    await expect(page.getByRole("heading", { level: 1, name: "My work" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Tasks by status" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Needs attention" })).toHaveCount(0);
  });

  await test.step("an administrator sees operations, and filters change the request", async () => {
    const page = await (await browser.newContext()).newPage();
    await signIn(page, ADMIN_EMAIL, SEEDED_PASSWORD);
    await expect(page.getByRole("heading", { level: 1, name: "Dashboard" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Needs attention" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Storage used" })).toBeVisible();
    const asked = page.waitForRequest((r) => r.url().includes("/api/v1/dashboard?days=7"));
    await page.getByLabel("Period").selectOption("7");
    await asked;
    await page.getByText("Show as a table").click();
    await expect(page.getByRole("columnheader", { name: "Recorded" })).toBeVisible();
  });

  await test.step("two-step sign-in does not start without the right password", async () => {
    const page = await (await browser.newContext()).newPage();
    await signIn(page, SEEDED.qcExecutive, SEEDED_PASSWORD);
    await page.goto("/account");
    await page.getByLabel(/^Your password/).fill("not-the-right-password");
    await page.getByRole("button", { name: "Turn on two-step sign-in" }).click();
    await expect(
      page.getByRole("alert").filter({ hasText: "Password is not correct" }),
    ).toBeVisible();
    await expect(page.getByLabel("Authenticator code")).toHaveCount(0);
  });
});
