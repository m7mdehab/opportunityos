import { defineConfig, devices } from "@playwright/test";

/**
 * Cloud / Hosted Staging Playwright configuration for OpportunityOS Founder Alpha.
 *
 * Requirements:
 * - Accepts `OPOS_STAGING_WEB_URL` (the remote Cloudflare Workers staging URL)
 * - Accepts `E2E_FOUNDER_PASSWORD` (the founder password configured on staging)
 * - MUST NOT start local API, PostgreSQL, or web servers (no webServer defined).
 * - Exercises the actual remote staging URL.
 * - Projects: Desktop Chrome + 390px Mobile project (iPhone 12 / 13 / 14 equivalent).
 */

const stagingWebUrl = process.env.OPOS_STAGING_WEB_URL?.trim();
const founderPassword = process.env.E2E_FOUNDER_PASSWORD?.trim();
const founderEmail = process.env.E2E_FOUNDER_EMAIL?.trim();

if (!stagingWebUrl) {
  throw new Error(
    "playwright.staging.config.ts requires OPOS_STAGING_WEB_URL to be set to the remote Cloudflare staging URL (e.g. https://<worker>.workers.dev). Refusing to run without target URL."
  );
}

if (!founderPassword) {
  throw new Error(
    "playwright.staging.config.ts requires E2E_FOUNDER_PASSWORD to be set for authenticating against staging."
  );
}

if (!founderEmail) {
  throw new Error(
    "playwright.staging.config.ts requires E2E_FOUNDER_EMAIL to be set for authenticating against staging."
  );
}

export default defineConfig({
  testDir: "./tests/e2e",
  testMatch: /staging-smoke\.spec\.ts$/,
  fullyParallel: false,
  workers: 1,
  retries: 1,
  reporter: [
    ["list"],
    ["html", { open: "never", outputFolder: "playwright-report-staging" }],
  ],
  use: {
    baseURL: stagingWebUrl.replace(/\/+$/, ""),
    trace: "on-first-retry",
    screenshot: "only-on-failure",
  },
  projects: [
    {
      name: "Desktop Chrome",
      use: { ...devices["Desktop Chrome"] },
    },
    {
      name: "Mobile 390px",
      use: {
        viewport: { width: 390, height: 844 },
        userAgent:
          "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1",
        hasTouch: true,
        isMobile: true,
      },
    },
  ],
});