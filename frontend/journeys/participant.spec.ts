// Journey: staff publish a consent form and add a participant, who is emailed the form by itself
// (D-129); with the personal link in that email (D-067; staff never see it, D-142) the participant
// (no account) opens their page, first does not agree, then agrees - final, nothing to withdraw;
// staff see both answers, and a task can then be made with them. Requirements: PART-006,
// PART-013, PART-014
import { expect, test } from "@playwright/test";

import {
  ADMIN_EMAIL,
  api,
  emailedConsentLink,
  fillSpeakerDetails,
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
  const name = `Chitra ${code}`;
  const email = `chitra.${code.toLowerCase()}@example.org`;
  const row = () => page.getByRole("row").filter({ hasText: name });
  let link = "";

  await test.step("an administrator writes the consent form in the project", async () => {
    await page.goto(`/projects/${setup.projectId}`);
    await page.getByLabel("Consent form text").fill(`I agree to be recorded for ${code}.`);
    await page.getByRole("button", { name: "Save project" }).click();
    await expect(page.getByRole("status").filter({ hasText: /saved/i })).toBeVisible();
  });

  await test.step("adds a participant, who is emailed the form by itself", async () => {
    await page.goto(`/projects/${setup.projectId}/participants`);
    await page.getByRole("button", { name: "Add participant" }).click();
    const form = page.getByRole("dialog", { name: "Add participant" });
    await form.getByLabel(/^Name or label/).fill(name);
    await form.getByLabel(/^Email address/).fill(email);
    await form.getByLabel(/^Language/).selectOption("hi");
    await fillSpeakerDetails(form); // every one, for someone new (D-143)
    await form.getByRole("button", { name: "Add participant" }).click();
    await expect(page.getByText(/^P\d{6} added\. Consent form emailed\.$/)).toBeVisible();
    // Staff cannot make or see the participant's link: it is in the participant's email only.
    await expect(row().getByRole("button", { name: "Personal link" })).toHaveCount(0);
    link = await emailedConsentLink(email);
    expect(link).toMatch(/^\/portal#[A-Za-z0-9_-]{20,}$/);
  });

  const visitor = await (await browser.newContext()).newPage(); // no session, like a participant
  const sent: string[] = [];
  visitor.on("request", (r) => sent.push(r.url()));

  await test.step("the participant opens the link: own details, no staff application", async () => {
    await visitor.goto(link);
    await expect(
      visitor.getByRole("heading", { level: 1, name: "Your participation" }),
    ).toBeVisible();
    await expect(visitor.getByText(`I agree to be recorded for ${code}.`)).toBeVisible();
    await expect(visitor.getByText("No sessions yet")).toBeVisible();
    await expect(visitor.getByRole("navigation", { name: "Main" })).toHaveCount(0);
    // Their own details are shown, read-only; other people's never are (D-100).
    await expect(visitor.getByText(name)).toBeVisible();
    await expect(visitor.getByText(`Asha ${code}`)).toHaveCount(0);
    const secret = link.split("#")[1] ?? "";
    expect(sent.some((u) => u.includes(secret))).toBe(false); // never in any address
  });

  await test.step("does not agree at first, then agrees: final, nothing to withdraw", async () => {
    await expect(visitor.getByRole("button", { name: "I agree" })).toBeDisabled();
    await visitor.getByLabel("I have read and understood this form").check();
    await visitor.getByRole("button", { name: "I do not agree" }).click();
    await expect(visitor.getByText("You did not agree")).toBeVisible();
    await expect(visitor.getByText(/You can still agree\./)).toBeVisible();
    await visitor.getByRole("button", { name: "I agree" }).click();
    await expect(visitor.getByText(/^You agreed on .+\.$/)).toBeVisible();
    await visitor.reload();
    await expect(visitor.getByText(/^You agreed on .+\.$/)).toBeVisible();
    await expect(visitor.getByRole("button")).toHaveCount(0);
    await expect(visitor.getByText(/withdraw/i)).toHaveCount(0);
  });

  await test.step("staff see both answers, at once and with nothing to review", async () => {
    await page.reload();
    await row().getByRole("button", { name: "Consent history" }).click();
    const history = page.getByRole("dialog", { name: /Consent history/ });
    await expect(history.getByText("Agreed").first()).toBeVisible();
    await expect(history.getByText("Did not agree").first()).toBeVisible();
    await expect(history.getByText(/answered by the participant/)).toHaveCount(2);
    await history.getByRole("button", { name: "Close" }).click();
    await expect(row().getByRole("button", { name: "Email consent form again" })).toHaveCount(0);
  });

  await test.step("a task can now be made with them, and their page shows it", async () => {
    const people = await api<{ items: { id: string; display_label: string }[] }>(
      page,
      "GET",
      `/api/v1/projects/${setup.projectId}/participants?search=${encodeURIComponent(name)}`,
    );
    const chitra = people.items.find((p) => p.display_label === name)?.id ?? "";
    const first = await api<{ moderator_id: string; participant_b: { id: string } }>(
      page,
      "GET",
      `/api/v1/tasks/${setup.taskId}`,
    );
    // Assigned at once: a participant's page lists sessions from Assigned on.
    const task = await api<{ task_code: string }>(page, "POST", "/api/v1/tasks", {
      project_id: setup.projectId,
      recording_mode: "FACE_TO_FACE",
      participant_a_id: chitra,
      participant_b_id: first.participant_b.id,
      moderator_id: first.moderator_id,
    });
    await visitor.reload();
    await expect(visitor.getByRole("cell", { name: task.task_code })).toBeVisible();
  });
});
