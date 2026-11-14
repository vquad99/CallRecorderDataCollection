// Journey: an admin must set up two-step sign-in before anything else (D-106).
// Runs only against a backend that requires it (REQUIRE_ADMIN_MFA=true, told here with
// E2E_ADMIN_MFA=1); the other journeys run with the rule off, as development and CI do. Uses the
// seeded Project Admin and leaves the account as it found it. If a run stops half-way, put the
// account back with: python -m app.cli reset-mfa demo.project-admin@example.org
// Requirements: AUTH-008, AUTH-016
import { createHmac } from "node:crypto";

import { expect, test, type Page } from "@playwright/test";

import { requireSetup, SEEDED_PASSWORD } from "./support";

const ADMIN = "demo.project-admin@example.org";
const STEP_MS = 30_000;

/** The 6-digit code an authenticator app shows for this key right now (RFC 6238, SHA-1). */
function totp(key: string, at = Date.now()): string {
  const alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567";
  let bits = "";
  for (const c of key) bits += alphabet.indexOf(c).toString(2).padStart(5, "0");
  const secret = Buffer.from((bits.match(/.{8}/g) ?? []).map((b) => parseInt(b, 2)));
  const counter = Buffer.alloc(8);
  counter.writeBigUInt64BE(BigInt(Math.floor(at / STEP_MS)));
  const digest = createHmac("sha1", secret).update(counter).digest();
  const offset = (digest[digest.length - 1] ?? 0) & 0x0f;
  const number = (digest.readUInt32BE(offset) & 0x7fffffff) % 1_000_000;
  return String(number).padStart(6, "0");
}

/** A code is accepted once only, so each new use waits for the app's next code. */
async function nextCode(page: Page, key: string): Promise<string> {
  await page.waitForTimeout(STEP_MS - (Date.now() % STEP_MS) + 1_500);
  return totp(key);
}

async function enterPassword(page: Page) {
  await page.goto("/login");
  await page.getByLabel(/^Email/).fill(ADMIN);
  await page.getByLabel(/^Password/).fill(SEEDED_PASSWORD);
  await page.getByRole("button", { name: "Sign in" }).click();
}

test("an admin sets up two-step sign-in before anything else and then signs in with a code", async ({
  browser,
}) => {
  test.skip(
    process.env.E2E_ADMIN_MFA !== "1",
    "this backend does not require two-step sign-in for admins (REQUIRE_ADMIN_MFA)",
  );
  requireSetup();
  test.setTimeout(240_000);
  const page = await (await browser.newContext()).newPage();
  const menu = page.getByRole("navigation", { name: "Main" });
  const setUp = page.getByRole("heading", { name: "Set up two-step sign-in" });
  let key = "";

  await test.step("the password alone opens only the set-up", async () => {
    await enterPassword(page);
    await expect(setUp).toBeVisible();
    await expect(
      page.getByText(/Your role \(Project Admin\) needs two-step sign-in/),
    ).toBeVisible();
    await expect(menu.getByRole("link")).toHaveCount(0);
    // A typed address leads back, and the server refuses the data as well.
    await page.goto("/projects");
    await expect(setUp).toBeVisible();
    expect(new URL(page.url()).pathname).toBe("/two-step-setup");
    const refused = await page.request.get("/api/v1/projects");
    expect(refused.status()).toBe(403);
    expect(((await refused.json()) as { error: { code: string } }).error.code).toBe(
      "MFA_SETUP_REQUIRED",
    );
  });

  await test.step("the admin adds the key to an authenticator app and enters its code", async () => {
    await page.getByLabel(/^Your password/).fill(SEEDED_PASSWORD);
    await page.getByRole("button", { name: "Turn on two-step sign-in" }).click();
    // A code to scan is shown; the key behind it can be typed instead.
    const code = page.getByRole("img", { name: "QR code for your authenticator app" });
    await expect(code).toBeVisible();
    expect(((await code.locator("path").getAttribute("d")) ?? "").length).toBeGreaterThan(2000);
    await page.getByText("Cannot scan? Type the key instead").click();
    key = ((await page.locator(".twostep__key").textContent()) ?? "").replace(/\s/g, "");
    expect(key).toMatch(/^[A-Z2-7]{16,}$/);
    await expect(
      page.getByRole("link", { name: "Open in an authenticator app on this device" }),
    ).toHaveAttribute("href", /^otpauth:\/\/totp\//);
    // A wrong code is refused and nothing opens.
    await page.getByLabel(/^Authenticator code/).fill("000000");
    await page.getByRole("button", { name: "Confirm" }).click();
    await expect(page.getByRole("alert")).toContainText("code is not valid");
    await page.getByLabel(/^Authenticator code/).fill(totp(key));
    await page.getByRole("button", { name: "Confirm" }).click();
    await expect(menu.getByRole("link", { name: "Projects" })).toBeVisible();
    await page.goto("/projects");
    await expect(page.getByRole("heading", { level: 1, name: "Projects" })).toBeVisible();
  });

  await test.step("the next sign-in asks for the password and then a code", async () => {
    await page.getByRole("button", { name: "Sign out" }).click();
    await expect(page.getByRole("heading", { name: "Sign in" })).toBeVisible();
    await enterPassword(page);
    await expect(page.getByLabel(/^Authenticator code/)).toBeVisible();
    await expect(menu).toHaveCount(0);
    await page.getByLabel(/^Authenticator code/).fill(await nextCode(page, key));
    await page.getByRole("button", { name: "Sign in" }).click();
    await expect(menu.getByRole("link", { name: "Projects" })).toBeVisible();
  });

  await test.step("turned off (to move to a new phone), the set-up comes first again", async () => {
    await page.goto("/account");
    const section = page.getByRole("region", { name: "Two-step sign-in" });
    await expect(section.getByText("Status: On")).toBeVisible();
    await section.getByLabel(/^Password/).fill(SEEDED_PASSWORD);
    await section.getByLabel(/^Authenticator code/).fill(await nextCode(page, key));
    await section.getByRole("button", { name: "Turn off two-step sign-in" }).click();
    await expect(setUp).toBeVisible();
    await expect(menu.getByRole("link")).toHaveCount(0);
    await page.getByRole("button", { name: "Sign out" }).click();
    await expect(page.getByRole("heading", { name: "Sign in" })).toBeVisible();
  });
});
