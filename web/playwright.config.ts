import { defineConfig, devices } from "@playwright/test"
import { definedProcessEnv } from "./tests/e2e/env"

/**
 * Phase 1: runs against the mock layer served by a production build
 * (`next build && next start`). `NEXT_PUBLIC_USE_MOCK_API=1` is set
 * directly on `webServer.env` below (not via a gitignored `.env.local`)
 * so a fresh clone with `npm ci` is green with no manual file creation —
 * an untracked dotenv file is not reproducible for anyone else. See
 * `playwright.real.config.ts` for phase 2 (the real API + seeded
 * PostgreSQL) — the test files and their assertions do not change between
 * the two.
 *
 * Production, not `next dev`, deliberately: React does not double-invoke
 * effects outside Strict Mode's dev-only behaviour, so this sidesteps a
 * dev-only MSW startup race, is closer to what the founder actually runs
 * (`scripts/alpha.py` starts the built app), and is faster/more stable in
 * CI. `web/lib/mock/browser.ts` still memoizes the worker-start promise so
 * `npm run dev` doesn't hang either.
 *
 * Port 3100 (not the framework default 3000) is used only to avoid
 * collisions with other Next servers that may be running concurrently on
 * this shared host (parallel worktrees/agents); `npm run dev` / `npm run
 * start` themselves are untouched and still default to 3000.
 */
const PORT = 3100

export default defineConfig({
  testDir: "./tests/e2e",
  // Hosted-only smoke requires a deployed Cloudflare/Azure staging stack.
  testIgnore: /staging-smoke\.spec\.ts$/,
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [
    ["list"],
    ["html", { open: "never", outputFolder: "playwright-report" }],
  ],
  use: {
    baseURL: `http://localhost:${PORT}`,
    trace: "on",
    screenshot: "only-on-failure",
  },
  webServer: {
    command: `npx next build && npx next start -p ${PORT}`,
    url: `http://localhost:${PORT}`,
    reuseExistingServer: !process.env.CI,
    timeout: 180_000,
    env: {
      ...definedProcessEnv(),
      NEXT_PUBLIC_USE_MOCK_API: "1",
    },
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
})
