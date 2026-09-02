import { defineConfig, devices } from "@playwright/test"

/**
 * Phase 1: runs against the mock layer (NEXT_PUBLIC_USE_MOCK_API=1, set in
 * .env.local) served by a production build (`next build && next start`).
 * Phase 2 changes only `use.baseURL` / `webServer` (pointing at the real API
 * + seeded PostgreSQL) — the test files and their assertions do not change.
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
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
})
