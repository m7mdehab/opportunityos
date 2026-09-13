import { test, expect, type Page } from "@playwright/test"

const FOUNDER_PASSWORD =
  process.env.E2E_FOUNDER_PASSWORD ?? "founder-mock-pass"

async function loginInScenario(page: Page, scenario: "no-truth-pack" | "invalid-truth-pack") {
  await page.addInitScript((selectedScenario) => {
    const originalPushState = window.history.pushState.bind(window.history)
    window.history.pushState = (data, unused, url) => {
      if (url) {
        const target = new URL(String(url), window.location.href)
        target.searchParams.set("mock_scenario", selectedScenario)
        return originalPushState(data, unused, `${target.pathname}${target.search}${target.hash}`)
      }
      return originalPushState(data, unused, url)
    }
  }, scenario)

  await page.goto(`/login?mock_scenario=${scenario}`)
  await page.getByLabel("Password").fill(FOUNDER_PASSWORD)
  await page.getByRole("button", { name: "Sign in" }).click()
  await expect(page).toHaveURL(new RegExp(`mock_scenario=${scenario}`))
}

test.describe("truth-pack degraded browsing", () => {
  test("a missing pack is identified correctly and does not hide live opportunities", async ({ page }) => {
    await loginInScenario(page, "no-truth-pack")

    const warning = page.getByTestId("truth-pack-warning")
    await expect(warning).toContainText("Founder profile not loaded")
    await expect(warning).toContainText("browse the live opportunity feed")
    await expect(page.getByTestId("opportunity-count")).toBeVisible()
    await expect(page.locator('[data-decision="null"]').first()).toContainText("Not yet evaluated")
  })

  test("an invalid pack keeps the feed visible while evaluation remains disabled", async ({ page }) => {
    await loginInScenario(page, "invalid-truth-pack")

    const warning = page.getByTestId("truth-pack-warning")
    await expect(warning).toContainText("Founder profile needs attention")
    await expect(warning).toContainText("identity.full_name")
    await expect(page.getByTestId("opportunity-count")).toBeVisible()
    await expect(page.locator('[data-decision="null"]').first()).toContainText("Not yet evaluated")
  })
})
