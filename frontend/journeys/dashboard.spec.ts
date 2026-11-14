// Journey: every role opens the app on its own dashboard, and two-step sign-in asks for the
// password before it starts (D-064, D-065, D-108). Requirements: DASH-001, DASH-002, DASH-004,
// ROLE-007, AUTH-008
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

    // The filters (D-108): each one narrows what the server is asked; the server answers with
    // the lists to choose from and the figures for the choice.
    const filters = page.getByRole("group", { name: "Filters" });
    const byMode = page.waitForResponse((r) => r.url().includes("mode=FACE_TO_FACE"));
    await filters.getByLabel("Recording type").selectOption("FACE_TO_FACE");
    const narrowed = (await (await byMode).json()) as {
      by_mode: { mode: string; recordings: number }[];
      options: { languages: string[]; staff: { name: string }[] };
      calls: { placed: number };
    };
    expect(narrowed.by_mode.find((m) => m.mode === "TELEPHONY")?.recordings).toBe(0);
    expect(narrowed.calls.placed).toBe(0);
    expect(Array.isArray(narrowed.options.staff)).toBe(true);
    await page.getByLabel("Period").selectOption("custom");
    const byDays = page.waitForResponse(
      (r) => r.url().includes("date_from=2026-01-01") && r.url().includes("date_to=2026-01-02"),
    );
    await filters.getByLabel("From").fill("2026-01-01");
    await filters.getByLabel("To").fill("2026-01-02");
    const twoDays = (await (await byDays).json()) as { daily: unknown[]; recordings: number };
    expect([twoDays.daily.length, twoDays.recordings]).toEqual([2, 0]);
    await filters.getByLabel("To").fill("2025-12-01");
    await expect(page.getByText("Must not be before the first day")).toBeVisible();
    await filters.getByRole("button", { name: "Clear filters" }).click();
    await expect(filters.getByLabel("Recording type")).toHaveValue("");
    await expect(filters.getByLabel("From")).toHaveCount(0);
    await expect(page.getByRole("heading", { name: "Needs attention" })).toBeVisible();
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
