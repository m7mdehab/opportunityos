import path from "node:path"
import fs from "node:fs"
import { test, expect } from "@playwright/test"

const FOUNDER_PASSWORD =
  process.env.E2E_FOUNDER_PASSWORD ?? "founder-mock-pass"

// reports/evidence/FR-005/ at the repo-worktree root (sibling of web/).
// This is the one place this suite writes outside `web/`, and only PNGs.
//
// It pointed at FR-004 until BRIEF-FR-005, which meant every `npx playwright
// test` run silently rewrote a *closed* brief's committed evidence -- the
// D3-web implementer had to `git checkout -- reports/evidence/FR-004/...`
// after each full run to get a clean `git status`. Evidence for a brief that
// has already passed its gate must not be mutable by a later brief's test
// run, so this now writes into the active brief's own directory. Whoever
// opens FR-006 should move it again.
const EVIDENCE_DIR = path.resolve(__dirname, "../../../reports/evidence/FR-005")

const VIEWPORTS = [
  { name: "360", width: 360, height: 800 },
  { name: "1280", width: 1280, height: 900 },
] as const

test.describe("evidence screenshots", () => {
  test.beforeAll(() => {
    fs.mkdirSync(EVIDENCE_DIR, { recursive: true })
  })

  for (const vp of VIEWPORTS) {
    test(`login page @ ${vp.name}px`, async ({ page }) => {
      await page.setViewportSize({ width: vp.width, height: vp.height })
      await page.goto("/login")
      await expect(page.getByRole("heading", { name: "OpportunityOS" })).toBeVisible()
      await page.screenshot({
        path: path.join(EVIDENCE_DIR, `d7-login-${vp.name}.png`),
        fullPage: true,
      })
    })

    test(`feed page @ ${vp.name}px`, async ({ page }) => {
      await page.setViewportSize({ width: vp.width, height: vp.height })
      await page.goto("/login")
      await page.getByLabel("Password").fill(FOUNDER_PASSWORD)
      await page.getByRole("button", { name: "Sign in" }).click()
      await expect(page).toHaveURL(/\/$/)
      await expect(
        page.getByTestId("opportunity-card-opp-001")
      ).toBeVisible()
      await page.screenshot({
        path: path.join(EVIDENCE_DIR, `d7-feed-${vp.name}.png`),
        fullPage: true,
      })
    })
  }
})
