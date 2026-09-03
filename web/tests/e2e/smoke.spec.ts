import { test, expect, type Page } from "@playwright/test"

/**
 * Full founder smoke test, run against the mock layer in phase 1
 * (`NEXT_PUBLIC_USE_MOCK_API=1`, `web/.env.local`) and against the real
 * FastAPI service + seeded PostgreSQL in phase 2. Only `playwright.config.ts`
 * (`baseURL`/`webServer`) and the password below change between phases —
 * these assertions do not.
 */
const FOUNDER_PASSWORD =
  process.env.E2E_FOUNDER_PASSWORD ?? "founder-mock-pass"

async function login(page: Page) {
  await page.goto("/")
  await expect(page).toHaveURL(/\/login$/)
  await page.getByLabel("Password").fill(FOUNDER_PASSWORD)
  await page.getByRole("button", { name: "Sign in" }).click()
  await expect(page).toHaveURL(/\/$/)
  await expect(page.getByRole("heading", { name: "OpportunityOS" })).toBeVisible()
}

async function statValue(page: Page, key: string): Promise<number> {
  const text = await page.getByTestId(`stat-${key}`).innerText()
  return Number(text.trim())
}

test.describe("founder alpha smoke", () => {
  test("login, feed, drawer, download, feedback, mark applied, dashboard counts", async ({
    page,
  }) => {
    // ---- 1. log in ----
    await login(page)

    // Seeded fixture cards are visible.
    await expect(
      page.getByTestId("opportunity-card-opp-001")
    ).toBeVisible()

    // D3 default founder filters hide the fixture set's red-line and
    // excluded-industry matches (opp-002 among them, needed below). Reveal
    // them here so the rest of this smoke test's assumptions about which
    // opportunities are on the page are unchanged from pre-D3 behaviour —
    // this control's own toggle behaviour is covered separately by
    // `filters.spec.ts` (A-8).
    const showHidden = page.getByTestId("toggle-hidden-opportunities")
    if (await showHidden.count()) {
      await showHidden.click()
      await expect(
        page.getByTestId("opportunity-card-opp-002")
      ).toBeVisible()
    }

    const initialCardCount = await page.getByRole("listitem").count()
    expect(initialCardCount).toBeGreaterThan(0)

    const openedBefore = await statValue(page, "opened")
    const labelledBefore = await statValue(page, "labelled")
    const appliedBefore = await statValue(page, "applied")

    // ---- 2. open a drawer whose checklist has PASS, FAIL, and UNKNOWN ----
    await page.getByTestId("opportunity-card-opp-002").click()
    const drawer = page.getByRole("dialog")
    await expect(drawer).toBeVisible()

    const failBadge = drawer.locator('[data-outcome="FAIL"]').first()
    const unknownBadge = drawer.locator('[data-outcome="UNKNOWN"]').first()
    await expect(failBadge).toBeVisible()
    await expect(unknownBadge).toBeVisible()

    // UNKNOWN must be distinguishable from FAIL: different label text and a
    // different colour class — never colour alone, and never the same text.
    await expect(failBadge).toHaveText("Failed")
    await expect(unknownBadge).toHaveText("Could not determine")
    await expect(failBadge).not.toHaveText(await unknownBadge.innerText())
    const failClass = (await failBadge.getAttribute("class")) ?? ""
    const unknownClass = (await unknownBadge.getAttribute("class")) ?? ""
    expect(failClass).toContain("red")
    expect(unknownClass).toContain("amber")
    expect(failClass).not.toContain("amber")
    expect(unknownClass).not.toContain("red")

    // Close this drawer via Escape (also exercises the close-on-Escape
    // requirement).
    await page.keyboard.press("Escape")
    await expect(drawer).not.toBeVisible()

    // ---- 3. an `uncertain` decision renders as uncertain, not ineligible ----
    await page.getByTestId("opportunity-card-opp-003").click()
    const uncertainDrawer = page.getByRole("dialog")
    await expect(uncertainDrawer).toBeVisible()
    const decisionBadge = uncertainDrawer
      .locator('[data-decision="uncertain"]')
      .first()
    await expect(decisionBadge).toBeVisible()
    await expect(decisionBadge).toHaveText("Uncertain")
    await expect(uncertainDrawer.locator('[data-decision="ineligible"]')).toHaveCount(
      0
    )
    await page.keyboard.press("Escape")
    await expect(uncertainDrawer).not.toBeVisible()

    // ---- 4. open opp-001, download the CV, submit feedback, mark applied ----
    await page.getByTestId("opportunity-card-opp-001").click()
    const mainDrawer = page.getByRole("dialog")
    await expect(mainDrawer).toBeVisible()
    await expect(
      mainDrawer.getByRole("heading", { name: "Senior Localization Program Manager" })
    ).toBeVisible()

    const downloadPromise = page.waitForEvent("download")
    await mainDrawer.getByTestId("artifact-download-docx").click()
    const download = await downloadPromise
    expect(download.suggestedFilename()).toContain("cv-opp-001")

    await mainDrawer.getByRole("button", { name: "Good match" }).click()
    await expect(
      mainDrawer.getByRole("button", { name: "Good match" })
    ).toHaveAttribute("aria-pressed", "true")

    await mainDrawer.getByRole("button", { name: "Mark applied" }).click()
    await expect(mainDrawer.getByText("Marked applied")).toBeVisible()

    await page.keyboard.press("Escape")
    await expect(mainDrawer).not.toBeVisible()

    // ---- 5. dashboard counts changed ----
    await expect
      .poll(() => statValue(page, "opened"))
      .toBeGreaterThan(openedBefore)
    await expect
      .poll(() => statValue(page, "labelled"))
      .toBeGreaterThan(labelledBefore)
    await expect
      .poll(() => statValue(page, "applied"))
      .toBeGreaterThan(appliedBefore)
  })
})
