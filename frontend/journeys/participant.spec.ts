// Journey: staff publish a consent form and create a participant's personal link; the participant
// (no account) opens it, sees only their own sessions, agrees, then withdraws; staff see the answers
// (D-067). Requirements: PART-006, PART-013, PART-014
import { expect, test } from "@playwright/test";

import {
  ADMIN_EMAIL,
  requireSetup,
  runCode,
  SEEDED,
  SEEDED_PASSWORD,
  setUpTask,
  signIn,
} from "./support";

test("a participant answers the consent form on their personal page", async ({
  page,
  browser,
}, info) => {
  requireSetup();
  const code = runCode(info);
  await signIn(page, ADMIN_EMAIL, SEEDED_PASSWORD);
  const setup = await setUpTask(page, code, [SEEDED.moderator], SEEDED.moderator);
  let link = "";

  await test.step("an administrator writes the consent form in the project", async () => {
    await page.goto(`/projects/${setup.projectId}`);
    await page.getByLabel("Consent form text").fill(`I agree to be recorded for ${code}.`);
    await page.getByRole("button", { name: "Save project" }).click();
    await expect(page.getByRole("status").filter({ hasText: /saved/i })).toBeVisible();
  });

  await test.step("and creates the first participant's personal link", async () => {
    await page.goto(`/projects/${setup.projectId}/participants`);
    await page.getByRole("button", { name: "Personal link" }).first().click();
    const card = page.getByRole("region", { name: "Personal link" });
    await expect(card).toBeVisible();
    link = (await card.locator(".mono").innerText()).trim();
    expect(link).toMatch(/\/portal#[A-Za-z0-9_-]{20,}$/);
  });

  const visitor = await (await browser.newContext()).newPage(); // no session, like a participant
  const sent: string[] = [];
  visitor.on("request", (r) => sent.push(r.url()));

  await test.step("the participant opens the link: own session, no staff application", async () => {
    await visitor.goto(new URL(link).pathname + new URL(link).hash);
    await expect(
      visitor.getByRole("heading", { level: 1, name: "Your participation" }),
    ).toBeVisible();
    await expect(visitor.getByText(`I agree to be recorded for ${code}.`)).toBeVisible();
    await expect(visitor.getByRole("cell", { name: setup.taskCode })).toBeVisible();
    await expect(visitor.getByRole("navigation", { name: "Main" })).toHaveCount(0);
    // Their own details are shown, read-only; the other speaker's never are (D-100).
    await expect(visitor.getByText(`Asha ${code}`)).toBeVisible();
    await expect(visitor.getByText(`Bina ${code}`)).toHaveCount(0);
    const secret = new URL(link).hash.slice(1);
    expect(sent.some((u) => u.includes(secret))).toBe(false); // never in any address
  });

  await test.step("agrees after ticking that they read it, then withdraws", async () => {
    await expect(visitor.getByRole("button", { name: "I agree" })).toBeDisabled();
    await visitor.getByLabel("I have read and understood this form").check();
    await visitor.getByRole("button", { name: "I agree" }).click();
    await expect(visitor.getByText("You agreed")).toBeVisible();
    await visitor.reload();
    await expect(visitor.getByText("You agreed")).toBeVisible();
    await visitor.getByRole("button", { name: "Withdraw my consent" }).click();
    await expect(visitor.getByText("You withdrew your consent")).toBeVisible();
  });

  await test.step("staff see both answers; a new link ends the old one", async () => {
    await page.reload();
    await page.getByRole("button", { name: "Consent" }).first().click();
    const history = page.getByRole("region", { name: "Consent history" });
    await expect(history.getByText(/WITHDRAWN.*answered by the participant/)).toBeVisible();
    await expect(history.getByText(/GIVEN.*answered by the participant/)).toBeVisible();
    await page.getByRole("button", { name: "Personal link" }).first().click();
    await expect(page.getByRole("region", { name: "Personal link" })).toBeVisible();
    await visitor.reload();
    await expect(visitor.getByRole("alert")).toContainText("not valid any more");
  });
});
