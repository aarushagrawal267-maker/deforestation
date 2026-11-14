import { defineConfig } from "@playwright/test";

// Expects the app to be running (start.ps1 or scripts/dev.sh). Override with SYLVA_URL.
// PW_CHROMIUM_PATH lets CI/containers use a preinstalled Chromium; otherwise run `npx playwright install chromium`.
export default defineConfig({
  testDir: "tests/e2e",
  timeout: 60_000,
  retries: 0,
  reporter: [["list"]],
  use: {
    baseURL: process.env.SYLVA_URL ?? "http://localhost:5173",
    viewport: { width: 1440, height: 900 },
    trace: "off",
    launchOptions: process.env.PW_CHROMIUM_PATH ? { executablePath: process.env.PW_CHROMIUM_PATH } : {},
  },
});
