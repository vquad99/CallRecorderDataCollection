// Journey: a person forgets their password, resets it from the email, and every old session ends
// (owner's test list, Option D). Requirements: AUTH-002, AUTH-004, AUTH-010, USER-002
import { expect, test } from "@playwright/test";

import {
  ADMIN_EMAIL,
  api,
  emailedLink,
  NEW_PASSWORD,
  requireSetup,
  runCode,
  SEEDED_PASSWORD,
  signIn,
} from "./support";

test("a forgotten password is reset by email and old sessions end", async ({ browser }, info) => {
  requireSetup();
  const code = runCode(info);
  const email = `reset.${code.toLowerCase()}@example.org`;
  const admin = await (await browser.newContext()).newPage();
  await signIn(admin, ADMIN_EMAIL, SEEDED_PASSWORD);
  const invited = Date.now() - 1000;
  await api(admin, "POST", "/api/v1/users", {
    email,
    display_name: `Reset ${code}`,
    roles: ["TRANSCRIBER"],
  });

  const laptop = await (await browser.newContext()).newPage();
  await test.step("the person accepts the invitation and signs in on a laptop", async () => {
    await laptop.goto(await emailedLink(email, invited));
    await laptop.getByLabel(/^New password/).fill(NEW_PASSWORD);
    await laptop.getByLabel(/^Repeat new password/).fill(NEW_PASSWORD);
    await laptop.getByRole("button", { name: "Set password" }).click();
    await laptop.getByRole("link", { name: "Go to sign in" }).click();
    await signIn(laptop, email, NEW_PASSWORD);
  });

  const phone = await (await browser.newContext()).newPage();
  const replaced = `${NEW_PASSWORD}-new`;
  await test.step("on another device the person asks for a reset link and sets a new password", async () => {
    const asked = Date.now() - 1000;
    await phone.goto("/login");
    await phone.getByRole("link", { name: /Forgot/ }).click();
    await phone.getByLabel(/^Email/).fill(email);
    await phone.getByRole("button", { name: "Send reset link" }).click();
    await expect(phone.getByRole("status")).toBeVisible();
    await phone.goto(await emailedLink(email, asked));
    await phone.getByLabel(/^New password/).fill(replaced);
    await phone.getByLabel(/^Repeat new password/).fill(replaced);
    await phone.getByRole("button", { name: "Set password" }).click();
    await expect(phone.getByText("Your password is set. You can sign in now.")).toBeVisible();
  });

  await test.step("the old password no longer works and the laptop session has ended", async () => {
    await phone.goto("/login");
    await phone.getByLabel(/^Email/).fill(email);
    await phone.getByLabel(/^Password/).fill(NEW_PASSWORD);
    await phone.getByRole("button", { name: "Sign in" }).click();
    await expect(phone.getByRole("alert")).toBeVisible();
    await signIn(phone, email, replaced);
    await laptop.reload();
    await expect(laptop.getByRole("heading", { name: "Sign in" })).toBeVisible();
  });
});
