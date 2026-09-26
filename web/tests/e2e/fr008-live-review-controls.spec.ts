import { expect, test, type Page } from "@playwright/test"

const FOUNDER_PASSWORD = process.env.E2E_FOUNDER_PASSWORD ?? "founder-mock-pass"

async function login(page: Page) {
  await page.goto("/")
  await expect(page).toHaveURL(/\/login$/)
  await page.getByLabel("Password").fill(FOUNDER_PASSWORD)
  await page.getByRole("button", { name: "Sign in" }).click()
  await expect(page).toHaveURL(/\/(?:\?.*)?$/)
  await expect(page.getByTestId("opportunity-count")).toBeVisible()
}

test.describe("FR-008 live review controls", () => {
  test("primary and advanced filters are checkbox multi-selects", async ({ page }) => {
    await login(page)

    const track = page.getByTestId("filter-facet-track")
    await track.locator("summary").click()
    await track.getByRole("checkbox", { name: "employment" }).check()
    await track.getByRole("checkbox", { name: "contract" }).check()
    await expect(track.getByRole("checkbox", { name: "employment" })).toBeChecked()
    await expect(track.getByRole("checkbox", { name: "contract" })).toBeChecked()
    await expect.poll(() =>
      page.evaluate(() => new URLSearchParams(window.location.search).getAll("track").length)
    ).toBe(2)

    await page.getByRole("button", { name: "Clear filters" }).click()
    await expect.poll(() =>
      page.evaluate(() => new URLSearchParams(window.location.search).getAll("track").length)
    ).toBe(0)

    await page.getByRole("button", { name: "More filters" }).click()
    const drawer = page.getByTestId("feed-query-drawer")
    const workMode = drawer.getByTestId("feed-facet-work_mode")
    await workMode.locator("summary").click()
    await workMode.getByRole("checkbox", { name: /remote/i }).check()
    await workMode.getByRole("checkbox", { name: /hybrid/i }).check()
    await expect(workMode.getByRole("checkbox", { name: /remote/i })).toBeChecked()
    await expect(workMode.getByRole("checkbox", { name: /hybrid/i })).toBeChecked()
    await drawer.getByRole("button", { name: "Apply filters" }).click()

    await expect.poll(() =>
      page.evaluate(() => new URLSearchParams(window.location.search).getAll("work_mode").length)
    ).toBe(2)
    await expect(page.getByTestId("feed-query-chips")).toContainText("Work mode")
  })

  test("visible cards can be multi-selected and batch saved", async ({ page }) => {
    await login(page)

    const cardsBefore = await page.locator('[data-testid^="opportunity-card-"]').count()
    expect(cardsBefore).toBeGreaterThanOrEqual(2)

    await page.getByRole("button", { name: "Select all visible" }).click()
    const selectedCount = page.getByText(/selected$/).first()
    await expect(selectedCount).not.toHaveText("0 selected")
    await expect(page.getByTestId("batch-action-toolbar")).toBeVisible()

    const selectedBoxes = page.locator('input[type="checkbox"][aria-label^="Select "]')
    const count = await selectedBoxes.count()
    expect(count).toBeGreaterThanOrEqual(2)
    await expect(selectedBoxes.first()).toBeChecked()
    await expect(selectedBoxes.nth(1)).toBeChecked()

    await page.getByTestId("batch-action-toolbar").getByRole("button", { name: "Save", exact: true }).click()
    await expect(page.getByTestId("batch-action-status")).toContainText("updated successfully")
    await expect(page.getByText("0 selected", { exact: true })).toBeVisible()
    expect(await page.locator('[data-testid^="opportunity-card-"]').count()).toBeLessThan(cardsBefore)
  })
})
