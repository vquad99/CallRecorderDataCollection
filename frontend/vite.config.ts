import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";

import react from "@vitejs/plugin-react";
import type { Plugin } from "vite";
import { defineConfig } from "vitest/config";

// Development server forwards API and health calls to the backend (same-origin in the browser).
const backend = process.env.VITE_BACKEND_URL ?? "http://127.0.0.1:8000";

/** Writes /sw.js for the built application (D-110): the service worker's text with a first
 * line that names this build, so every release has a different file and browsers see the new
 * version. The name is made from the names of the built files, which change with their content. */
function serviceWorker(): Plugin {
  return {
    name: "ccp-service-worker",
    apply: "build",
    generateBundle(_options, bundle) {
      const build = createHash("sha256")
        .update(Object.keys(bundle).sort().join("\n"))
        .digest("hex")
        .slice(0, 16);
      this.emitFile({
        type: "asset",
        fileName: "sw.js",
        source:
          `const BUILD = ${JSON.stringify(build)};\n` +
          readFileSync(new URL("./pwa/sw.template.js", import.meta.url), "utf8"),
      });
    },
  };
}

export default defineConfig({
  plugins: [react(), serviceWorker()],
  server: {
    proxy: {
      "/api": backend,
      "/health": backend,
    },
  },
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    include: ["src/**/*.test.{ts,tsx}"],
    restoreMocks: true,
  },
});
