// Requirements: FND-023, FND-015
// Backend calls are answered by page.route so this checks the frontend alone.
import { expect, test } from "@playwright/test";

test.beforeEach(async ({ page }) => {
  await page.route("**/health/ready", (route) =>
    route.fulfill({ json: { status: "ready", checks: { database: "ok", redis: "ok" } } }),
  );
  await page.route("**/api/v1/version", (route) =>
    route.fulfill({
      json: { name: "conversation-collection-platform", version: "0.1.0", environment: "test" },
    }),
  );
});

test("main pages render with no console errors", async ({ page }) => {
  const errors: string[] = [];
  page.on("console", (message) => {
    if (message.type() === "error") errors.push(message.text());
  });
  page.on("pageerror", (error) => errors.push(error.message));

  await page.goto("/");
  await expect(page.getByRole("heading", { name: "System status" })).toBeVisible();
  await expect(page.getByText("Ready", { exact: true })).toBeVisible();

  await page.goto("/missing-page");
  await expect(page.getByRole("heading", { name: "Page not found" })).toBeVisible();

  expect(errors).toEqual([]);
});
