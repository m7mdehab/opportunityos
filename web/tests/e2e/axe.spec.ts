import { test, expect } from "@playwright/test"
import AxeBuilder from "@axe-core/playwright"

const FOUNDER_PASSWORD =
  process.env.E2E_FOUNDER_PASSWORD ?? "founder-mock-pass"

test.describe("accessibility", () => {
  test("/login is axe-clean", async ({ page }) => {
    await page.goto("/login")
    await expect(page.getByRole("heading", { name: "OpportunityOS" })).toBeVisible()
    const results = await new AxeBuilder({ page }).analyze()
    expect(results.violations, JSON.stringify(results.violations, null, 2)).toEqual(
      []
    )
  })

  test("/ (the feed) is axe-clean", async ({ page }) => {
    await page.goto("/login")
    await page.getByLabel("Password").fill(FOUNDER_PASSWORD)
    await page.getByRole("button", { name: "Sign in" }).click()
    await expect(page).toHaveURL(/\/$/)
    await expect(
      page.getByTestId("opportunity-card-opp-001")
    ).toBeVisible()
    const results = await new AxeBuilder({ page }).analyze()
    expect(results.violations, JSON.stringify(results.violations, null, 2)).toEqual(
      []
    )
  })
})
