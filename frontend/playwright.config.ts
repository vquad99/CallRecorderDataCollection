import { defineConfig, devices } from "@playwright/test";

// PW_CHANNEL=chrome uses the installed Google Chrome (no browser download); CI uses Playwright's Chromium.
// PW_EDGE=1 adds a second run in the installed Microsoft Edge (CI sets it; Edge is on its runners).
const channel = process.env.PW_CHANNEL;
const port = 5180;
const builtPort = 5182;
// A built-in fake microphone so the recorder can be exercised without hardware.
const fakeMedia = {
  launchOptions: {
    args: ["--use-fake-device-for-media-stream", "--use-fake-ui-for-media-stream"],
  },
};

export default defineConfig({
  testDir: "./e2e",
  // Microsoft Edge's first start plus the dev server's first compile took 26 s on CI runners
  // (Option C run); 30 s left no margin.
  timeout: 60_000,
  expect: { timeout: 15_000 },
  reporter: [["list"]],
  use: { baseURL: `http://127.0.0.1:${port}`, trace: "retain-on-failure" },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"], ...(channel ? { channel } : {}), ...fakeMedia },
    },
    ...(process.env.PW_EDGE === "1"
      ? [{ name: "edge", use: { ...devices["Desktop Edge"], channel: "msedge", ...fakeMedia } }]
      : []),
  ],
  webServer: [
    {
      command: `npm run dev -- --host 127.0.0.1 --port ${port} --strictPort`,
      url: `http://127.0.0.1:${port}`,
      reuseExistingServer: false,
      timeout: 60_000,
    },
    {
      // The built application (dist/, made by `npm run build`), for what exists only there: the
      // service worker and the web app manifest (e2e/pwa.spec.ts).
      command: `npm run preview -- --host 127.0.0.1 --port ${builtPort} --strictPort`,
      url: `http://127.0.0.1:${builtPort}`,
      reuseExistingServer: false,
      timeout: 60_000,
    },
  ],
});
