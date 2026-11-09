// Requirements: FND-023, FND-015, AUTH-016
// Backend calls are answered by page.route so this checks the frontend alone.
import { expect, test, type Page } from "@playwright/test";

const ME = {
  id: "u1",
  email: "admin@example.org",
  display_name: "Ada Admin",
  roles: ["SUPER_ADMIN"],
  permissions: ["projects.view", "projects.create", "users.manage", "settings.manage"],
  project_ids: [],
  mfa_enabled: false,
};

async function backend(page: Page, signedIn: { value: boolean }) {
  await page.route("**/api/v1/auth/csrf", (route) => route.fulfill({ status: 204 }));
  await page.route("**/api/v1/auth/me", (route) =>
    signedIn.value
      ? route.fulfill({ json: ME })
      : route.fulfill({
          status: 401,
          json: { error: { code: "UNAUTHENTICATED", message: "Sign in required" } },
        }),
  );
  await page.route("**/api/v1/auth/login", (route) => {
    signedIn.value = true;
    return route.fulfill({ json: ME });
  });
  await page.route("**/api/v1/projects?*", (route) =>
    route.fulfill({ json: { items: [], total: 0, page: 1, page_size: 25 } }),
  );
  await page.route("**/health/ready", (route) =>
    route.fulfill({ json: { status: "ready", checks: { database: "ok", redis: "ok" } } }),
  );
  await page.route("**/api/v1/version", (route) =>
    route.fulfill({
      json: { name: "conversation-collection-platform", version: "0.1.0", environment: "test" },
    }),
  );
}

function collectErrors(page: Page): string[] {
  const errors: string[] = [];
  page.on("console", (message) => {
    // The deliberate 401 from /auth/me while signed out is a normal answer, not an app error.
    if (message.type() === "error" && !message.text().includes("401")) errors.push(message.text());
  });
  page.on("pageerror", (error) => errors.push(error.message));
  return errors;
}

test("sign in, then main pages render with no console errors", async ({ page }) => {
  const signedIn = { value: false };
  await backend(page, signedIn);
  const errors = collectErrors(page);

  await page.goto("/projects");
  await expect(page.getByRole("heading", { name: "Sign in" })).toBeVisible();
  await page.getByLabel("Email").fill("admin@example.org");
  await page.getByLabel("Password").fill("a-long-password");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("heading", { name: "Projects", exact: true })).toBeVisible();
  await expect(page.getByRole("navigation", { name: "Main" })).toContainText("Users");

  await page.goto("/status");
  await expect(page.getByText("Ready", { exact: true })).toBeVisible();

  await page.goto("/missing-page");
  await expect(page.getByRole("heading", { name: "Page not found" })).toBeVisible();

  expect(errors).toEqual([]);
});
