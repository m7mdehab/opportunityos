import { test, expect, type Page } from "@playwright/test"

const PASSWORD = process.env.E2E_FOUNDER_PASSWORD ?? "founder-mock-pass"

async function login(page: Page) {
  await page.addInitScript(() => {
    const originalFetch = window.fetch.bind(window)
    window.fetch = (input, init = {}) => {
      const headers = new Headers(init.headers)
      headers.set("x-mock-bypass-auth", "1")
      return originalFetch(input, { ...init, headers })
    }
  })
  await page.goto("/")
  if (await page.getByLabel("Password").count()) {
    await page.locator("input[type=email]").fill(process.env.E2E_FOUNDER_EMAIL ?? "founder@example.com")
    await page.getByLabel("Password").fill(PASSWORD)
    await expect(page.locator("input[type=email]")).toHaveValue(process.env.E2E_FOUNDER_EMAIL ?? "founder@example.com")
    await expect(page.getByLabel("Password")).toHaveValue(PASSWORD)
    await page.getByRole("button", { name: "Sign in" }).click()
    await expect(page).toHaveURL(/\/$/)
  }
  await expect(page.getByTestId("filter-activity")).toBeVisible()
}

test.describe("W25 Founder activity", () => {
  test("dismiss persists through refresh and is retrievable by activity", async ({ page }) => {
    await login(page)
    await page.getByTestId("opportunity-card-opp-001").click()
    const dialog = page.getByRole("dialog")
    await dialog.getByRole("button", { name: "Dismiss" }).click()
    await expect(dialog.getByText("Current status: Dismissed")).toBeVisible()
    await page.keyboard.press("Escape")
    await page.getByTestId("filter-activity").selectOption("dismissed")
    await expect(page.getByTestId("opportunity-card-opp-001")).toBeVisible()
    await page.reload()
    await expect(page.getByTestId("filter-activity")).toHaveValue("to_review")
  })

  test("feedback and applied states are visible and filterable", async ({ page }) => {
    await login(page)
    await page.getByTestId("filter-activity").selectOption("any")
    await page.getByTestId("opportunity-card-opp-001").click()
    const dialog = page.getByRole("dialog")
    await dialog.getByRole("button", { name: "Mark applied" }).click()
    await expect(dialog.getByText("Current status: Marked applied")).toBeVisible()
    await dialog.getByRole("button", { name: "Good match" }).click()
    await expect(dialog.getByRole("button", { name: "Good match" })).toHaveAttribute("aria-pressed", "true")
    await page.keyboard.press("Escape")
    await expect(page.getByTestId("opportunity-card-opp-001")).toContainText("Applied")
    await page.getByTestId("filter-feedback").selectOption("good_match")
    await expect(page.getByTestId("opportunity-card-opp-001")).toBeVisible()
  })
})
