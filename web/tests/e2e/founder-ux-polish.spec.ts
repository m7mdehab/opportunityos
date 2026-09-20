import { test, expect, type Page } from "@playwright/test"

const PASSWORD = process.env.E2E_FOUNDER_PASSWORD ?? "founder-mock-pass"

async function login(page: Page) {
  await page.goto("/")
  await expect(page).toHaveURL(/\/login$/)
  await page.getByLabel("Password").fill(PASSWORD)
  await page.getByRole("button", { name: "Sign in" }).click()
  await expect(page.getByRole("heading", { name: "OpportunityOS" })).toBeVisible()
}

test.describe("W24 Founder UX polish", () => {
  test("equal-height cards expose safe quick apply links and compact detail", async ({ page }) => {
    await page.setViewportSize({ width: 1920, height: 1080 })
    await login(page)
    const cards = page.locator("article")
    await expect(cards.first()).toBeVisible()
    const boxes = await cards.evaluateAll((els) => els.slice(0, 9).map((el) => el.getBoundingClientRect().height))
    expect(Math.max(...boxes) - Math.min(...boxes)).toBeLessThanOrEqual(1)
    const links = page.locator('[data-testid^="quick-apply-"]')
    expect(await links.count()).toBeGreaterThan(0)
    for (let i = 0; i < await links.count(); i += 1) {
      await expect(links.nth(i)).toHaveAttribute("target", "_blank")
      await expect(links.nth(i)).toHaveAttribute("rel", /noopener/)
      await expect(links.nth(i)).toHaveAttribute("href", /https?:\/\//)
    }
    await page.getByTestId("opportunity-card-opp-001").click()
    const dialog = page.getByRole("dialog")
    await expect(dialog.getByTestId("role-at-a-glance")).toBeVisible()
    const disclosure = dialog.getByTestId("full-description-disclosure")
    await expect(disclosure).not.toHaveAttribute("open")
    await disclosure.getByText("Show full job description").click()
    await expect(dialog.getByTestId("opportunity-description")).toBeVisible()
    await expect(dialog.getByRole("link", { name: "View original source" })).toBeVisible()
  })

  test("unified toolbar and numeric source health remain aligned and readable", async ({ page }) => {
    await page.setViewportSize({ width: 1920, height: 1080 })
    await login(page)
    for (const id of ["filter-track", "filter-decision", "filter-min-score", "filter-search", "filter-source-family", "open-facets-panel", "open-manual-sources-panel", "toggle-tutoring-lane"]) {
      await expect(page.locator(`#${id}, [data-testid="${id}"]`).first()).toBeVisible()
    }
    await expect(page.getByTestId("source-health-summary")).toBeVisible()
    await expect(page.getByTestId("source-health-healthy")).toContainText("3")
    await expect(page.getByTestId("source-health-empty")).toContainText("1")
    await expect(page.getByTestId("source-health-disabled")).toContainText("1")
  })

  test("390px mobile surface has no horizontal overflow", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 })
    await login(page)
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
    await expect(page.getByTestId("quick-apply-opp-001")).toBeVisible()
    await page.getByTestId("opportunity-card-opp-001").click()
    const dialog = page.getByRole("dialog")
    await expect(dialog.getByTestId("role-at-a-glance")).toBeVisible()
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
  })
})
