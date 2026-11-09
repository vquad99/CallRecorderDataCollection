import { defineConfig, devices } from "@playwright/test";

// User journeys (Option D): a real browser against the real backend, database and file storage.
// The backend must already be running (VITE_BACKEND_URL, default http://127.0.0.1:8000), seeded
// with `python -m app.cli seed-dev`, writing emails to E2E_OUTBOX. See frontend/journeys/README.md.
const channel = process.env.PW_CHANNEL;
const port = 5181;
const fakeMedia = {
  launchOptions: {
    args: [
      "--use-fake-device-for-media-stream",
      "--use-fake-ui-for-media-stream",
      "--autoplay-policy=no-user-gesture-required",
    ],
  },
};

export default defineConfig({
  testDir: "./journeys",
  timeout: 180_000,
  expect: { timeout: 15_000 },
  workers: 1,
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
  webServer: {
    command: `npm run dev -- --host 127.0.0.1 --port ${port} --strictPort`,
    url: `http://127.0.0.1:${port}`,
    reuseExistingServer: false,
    timeout: 60_000,
  },
});
