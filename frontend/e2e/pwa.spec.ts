// The installable application in a real browser, against the built files (D-110): the manifest
// and its icons, a service worker that keeps static files only, the offline page.
// Requirements: PWA-001, PWA-004, PWA-006
import { expect, test, type Route } from "@playwright/test";

const APP = "http://127.0.0.1:5182"; // `vite preview` of dist/ (playwright.config.ts)

test("the built application has a manifest, keeps static files only, and says when it is offline", async ({
  page,
  context,
}) => {
  // No backend here: the API answers like a server where nobody is signed in.
  let apiCalls = 0;
  const signedOut = (route: Route) => {
    apiCalls++;
    if (route.request().url().endsWith("/auth/csrf")) return route.fulfill({ status: 204 });
    return route.fulfill({
      status: 401,
      contentType: "application/json",
      body: JSON.stringify({ error: { code: "UNAUTHENTICATED", message: "Sign in required" } }),
    });
  };
  await context.route(`${APP}/api/**`, signedOut);

  await page.goto(`${APP}/login`);
  await expect(page.getByRole("heading", { name: "Sign in" })).toBeVisible();

  await test.step("the manifest names the application and its icons exist", async () => {
    await expect(page.locator('link[rel="manifest"]')).toHaveAttribute(
      "href",
      "/manifest.webmanifest",
    );
    const answer = await page.request.get(`${APP}/manifest.webmanifest`);
    expect(answer.status()).toBe(200);
    const manifest = (await answer.json()) as {
      name: string;
      short_name: string;
      display: string;
      start_url: string;
      theme_color: string;
      background_color: string;
      icons: { src: string; sizes: string; purpose: string }[];
    };
    expect(manifest.name).toBe("Conversation Collection");
    expect([manifest.display, manifest.start_url]).toEqual(["standalone", "/"]);
    expect(manifest.theme_color).toMatch(/^#[0-9a-f]{6}$/);
    expect(manifest.background_color).toMatch(/^#[0-9a-f]{6}$/);
    expect(manifest.icons.map((i) => `${i.sizes} ${i.purpose}`).sort()).toEqual([
      "192x192 any",
      "512x512 any",
      "512x512 maskable",
    ]);
    for (const icon of manifest.icons) {
      const file = await page.request.get(`${APP}${icon.src}`);
      expect(file.status(), icon.src).toBe(200);
      expect(file.headers()["content-type"]).toBe("image/png");
    }
  });

  await test.step("a service worker takes the page and keeps built files only", async () => {
    const script = await page.evaluate(async () => {
      const registration = await navigator.serviceWorker.ready;
      return registration.active?.scriptURL ?? "";
    });
    expect(script).toBe(`${APP}/sw.js`);
    // Loaded again, the page is in the worker's hands and its files go through it.
    await page.reload();
    await expect(page.getByRole("heading", { name: "Sign in" })).toBeVisible();
    await expect
      .poll(() => page.evaluate(() => navigator.serviceWorker.controller !== null))
      .toBe(true);
    const kept = await page.evaluate(async () => {
      const paths: string[] = [];
      for (const name of await caches.keys()) {
        const cache = await caches.open(name);
        for (const request of await cache.keys()) paths.push(new URL(request.url).pathname);
      }
      return { names: await caches.keys(), paths };
    });
    expect(kept.names).toHaveLength(1);
    expect(kept.names[0]).toMatch(/^ccp-static-[0-9a-f]{16}$/);
    expect(kept.paths.some((p) => p.startsWith("/assets/"))).toBe(true);
    const offline = ["/offline.html", "/offline.css", "/icon-192.png", "/favicon.svg"];
    for (const path of kept.paths) {
      expect(path.startsWith("/assets/") || offline.includes(path), path).toBe(true);
    }
    // The API was asked (who am I), and nothing of it was kept.
    expect(apiCalls).toBeGreaterThan(0);
    expect(kept.paths.filter((p) => p.startsWith("/api/"))).toEqual([]);
    // Nothing private in the browser's own stores either.
    const stores = await page.evaluate(() => ({
      local: Object.keys(window.localStorage),
      session: Object.keys(window.sessionStorage),
    }));
    expect(stores.local).toEqual([]);
    expect(stores.session.every((k) => !/token|session|user|auth/i.test(k))).toBe(true);
  });

  await test.step("the browser itself reads the manifest without complaint and finds nothing against installing", async () => {
    // Chromium's own judgement (the DevTools protocol), with the worker in charge of the page.
    const devtools = await context.newCDPSession(page);
    const manifest = await devtools.send("Page.getAppManifest");
    expect(manifest.url).toBe(`${APP}/manifest.webmanifest`);
    expect(manifest.errors).toEqual([]);
    const { installabilityErrors } = await devtools.send("Page.getInstallabilityErrors");
    // A test browser is a private window, where nothing can be installed: that one objection
    // is expected here and says nothing about the application.
    expect(
      installabilityErrors.map((e) => e.errorId).filter((id) => id !== "in-incognito"),
    ).toEqual([]);
  });

  await test.step("without a connection a page says so, and the API is not answered from a store", async () => {
    // From here the stand-in for the API is off: an answer could only come from a store.
    await context.unroute(`${APP}/api/**`, signedOut);
    await context.setOffline(true);
    await page.goto(`${APP}/projects`);
    await expect(page.getByRole("heading", { name: "You are offline" })).toBeVisible();
    await expect(page.getByText(/needs a connection/)).toBeVisible();
    const fromStore = await page.evaluate(() =>
      fetch("/api/v1/version").then(
        () => "answered",
        () => "failed",
      ),
    );
    expect(fromStore).toBe("failed");
    await context.setOffline(false);
    await context.route(`${APP}/api/**`, signedOut);
    await page.getByRole("link", { name: "Try again" }).click();
    await expect(page.getByRole("heading", { name: "Sign in" })).toBeVisible();
  });
});
