import path from "node:path"
import { defineConfig, devices } from "@playwright/test"
import { definedProcessEnv, ensureEnv, syntheticSecret } from "./tests/e2e/env"

/**
 * Phase 2 (BRIEF-FR-004 D7, extended by BRIEF-FR-005 D3's A-8): the same
 * `tests/e2e/smoke.spec.ts` and `tests/e2e/filters.spec.ts` used by
 * `playwright.config.ts` (phase 1, the MSW mock), run instead against the
 * real FastAPI service (`api.app:app`) backed by real PostgreSQL, seeded
 * by `tests/e2e/seed_real.py`. Per those files' own docstrings, only this
 * config's `use.baseURL` / `webServer` differ from phase 1 -- the test
 * files and their assertions are untouched. (`filters-unavailable.spec.ts`
 * stays mock-only for now -- see its own docstring for why.)
 *
 * A separate config file (not a branch inside playwright.config.ts) so
 * phase 1 stays a single, simple, always-safe-to-run mock config, and this
 * one can own real-service concerns (a Postgres URL, two extra processes,
 * a seeding step) without an `if` ladder inside one file.
 *
 * Ports: 3210 (web) and 8210 (API) -- deliberately high and specific, not
 * 3000/3100/8000, because this host runs several parallel worktrees/agents
 * and 3000/8000 collide with other projects.
 *
 * `OPPORTUNITYOS_DB_URL` must already be set in the environment before
 * running this config (see `docs/templates/truth_pack.template.yaml`'s
 * sibling setup note and the brief's "Your database" section) -- it is
 * never defaulted to a literal connection string here, both because a
 * password-bearing PostgreSQL URL literal trips
 * `scripts/check_guard.py`'s `SECRET_CONNECTION_STRING` rule and because a
 * real database's credentials are inherently host-specific, not something
 * a committed file can supply. `OPPORTUNITYOS_FOUNDER_PASSWORD` and
 * `OPPORTUNITYOS_SESSION_SECRET` (alpha-grade, local-only secrets for a
 * throwaway test database -- see ADR-0013) are synthesized at run time via
 * `syntheticSecret()` instead: no assignment site is ever a quoted 12+
 * character literal, so this file cannot itself trip
 * `SECRET_ASSIGNED_SECRET` regardless of the generated value's shape.
 */
if (!process.env.OPPORTUNITYOS_DB_URL) {
  throw new Error(
    "playwright.real.config.ts requires OPPORTUNITYOS_DB_URL to be set " +
      "(a real PostgreSQL URL for a disposable test database -- see the " +
      "brief's 'Your database' setup section). Refusing to default to a " +
      "hard-coded connection string."
  )
}

const REPO_ROOT = path.resolve(__dirname, "..")
const WEB_PORT = 3210
const API_PORT = 8210
// Deliberately `tests/e2e/truth_pack.e2e.yaml`, not
// `docs/templates/truth_pack.template.yaml`: the shipped template's
// employment-title and skill evidence are not relationally linked, which
// makes the compiler's "Professional Summary" composite claim fail
// ClaimValidator's relational composition guard on every real download --
// see that fixture file's header for the full writeup and REPORT-FR-004
// (D7 phase 2) for the defect report. This fixture uses the same
// single-evidence-skill shape api/test_api.py's own
// `_clean_truth_pack_graph()` uses for the identical reason.
const TRUTH_PACK_PATH = path.join(
  REPO_ROOT,
  "web",
  "tests",
  "e2e",
  "truth_pack.e2e.yaml"
)

// Every value in this file is synthetic. Loading it directly (never
// private/) is what lets the CV/cover-letter download step in
// smoke.spec.ts exercise the real ClaimValidator path.
const FOUNDER_PASSWORD = ensureEnv("E2E_FOUNDER_PASSWORD", () =>
  syntheticSecret("founder-pw")
)
const SESSION_SECRET = syntheticSecret("session-secret")

const baseEnv = definedProcessEnv()

export default defineConfig({
  testDir: "./tests/e2e",
  // Covers smoke.spec.ts and filters.spec.ts, not filters-unavailable.spec.ts
  // or axe.spec.ts/screenshots.spec.ts -- a pattern, not a file list, so a
  // new real-stack-safe spec only needs the right filename to be included.
  testMatch: /\/(smoke|filters)\.spec\.ts$/,
  // Hosted-only smoke must never run against local/mock webServer configs.
  testIgnore: /staging-smoke\.spec\.ts$/,
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [
    ["list"],
    ["html", { open: "never", outputFolder: "playwright-report-real" }],
  ],
  use: {
    baseURL: `http://localhost:${WEB_PORT}`,
    trace: "on",
    screenshot: "only-on-failure",
  },
  webServer: [
    {
      // Seeds the real database, then starts uvicorn in the same shell
      // invocation so the API is never accepting connections against an
      // unseeded (or stale) database. `py -3.12` (the Windows Python
      // launcher) is used rather than bare `python` because this host's
      // default `python` on PATH is 3.10; the launcher resolves 3.12
      // regardless of the caller's PATH ordering.
      command:
        "py -3.12 web/tests/e2e/seed_real.py && " +
        `py -3.12 -m uvicorn api.app:app --host 127.0.0.1 --port ${API_PORT}`,
      cwd: REPO_ROOT,
      port: API_PORT,
      reuseExistingServer: false,
      timeout: 60_000,
      // Piped (not the default "ignore") so uvicorn's access log -- one
      // line per request, e.g. `"POST /api/auth/login HTTP/1.1" 200` --
      // is visible in this config's own output. That access log is the
      // concrete evidence that a run against this config reached the
      // real API rather than the mock, which never produces one.
      stdout: "pipe",
      env: {
        ...baseEnv,
        OPPORTUNITYOS_DB_URL: process.env.OPPORTUNITYOS_DB_URL,
        OPPORTUNITYOS_FOUNDER_PASSWORD: FOUNDER_PASSWORD,
        OPPORTUNITYOS_SESSION_SECRET: SESSION_SECRET,
        OPPORTUNITYOS_TRUTH_PACK_PATH: TRUTH_PACK_PATH,
        OPPORTUNITYOS_HIGH_FIT_THRESHOLD: "70",
      },
    },
    {
      // NEXT_PUBLIC_USE_MOCK_API is deliberately absent here (unlike
      // playwright.config.ts, which sets it to "1"): the mock provider
      // (components/mock-provider.tsx) only imports MSW when that flag is
      // "1", so leaving it unset keeps the mock code out of this build
      // entirely and every /api/* request reaches the Next rewrite.
      command: `npx next build && npx next start -p ${WEB_PORT}`,
      cwd: path.join(REPO_ROOT, "web"),
      port: WEB_PORT,
      reuseExistingServer: false,
      timeout: 180_000,
      env: {
        ...baseEnv,
        // Explicitly cleared, not just omitted: guards against an ambient
        // NEXT_PUBLIC_USE_MOCK_API=1 already present in the parent shell
        // (e.g. left over from a phase 1 run in the same session) leaking
        // into this build via the `...baseEnv` spread above.
        NEXT_PUBLIC_USE_MOCK_API: "",
        OPPORTUNITYOS_API_PORT: String(API_PORT),
      },
    },
  ],
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
})
