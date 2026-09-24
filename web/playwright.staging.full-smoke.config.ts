import { defineConfig, devices } from "@playwright/test";

const stagingWebUrl = process.env.OPOS_STAGING_WEB_URL?.trim();
const founderPassword = process.env.E2E_FOUNDER_PASSWORD?.trim();
const founderEmail = process.env.E2E_FOUNDER_EMAIL?.trim();

if (!stagingWebUrl || !founderPassword || !founderEmail) {
  throw new Error("Full staging smoke requires its protected target and Founder credentials.");
}

export default defineConfig({
  testDir: "./tests/e2e",
  testMatch: /staging-smoke\.spec\.ts$/,
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: "list",
  use: {
    baseURL: stagingWebUrl.replace(/\/+$/, ""),
    trace: "off",
    screenshot: "off",
    ...devices["Desktop Chrome"],
  },
});
