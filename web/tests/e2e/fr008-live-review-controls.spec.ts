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
    await page.getByTestId("more-filters-dropdown").locator(":scope > summary").click()

    const track = page.getByTestId("filter-facet-track")
    await track.locator("summary").click()
    await track.getByRole("checkbox", { name: "employment" }).check()
    await track.getByRole("checkbox", { name: "contract" }).check()
    await expect(track.getByRole("checkbox", { name: "employment" })).toBeChecked()
    await expect(track.getByRole("checkbox", { name: "contract" })).toBeChecked()
    await expect.poll(() =>
      page.evaluate(() => new URLSearchParams(window.location.search).getAll("track").length)
    ).toBe(2)

    await page.getByRole("search", { name: "Filter opportunities" }).getByRole("button", { name: "Clear filters" }).click()
    await expect.poll(() =>
      page.evaluate(() => new URLSearchParams(window.location.search).getAll("track").length)
    ).toBe(0)

    const source = page.getByTestId("filter-facet-source-family")
    await source.locator("summary").click()
    const sourceOptions = source.getByRole("checkbox")
    expect(await sourceOptions.count()).toBeGreaterThanOrEqual(2)
    await sourceOptions.nth(0).check()
    await sourceOptions.nth(1).check()
    await expect.poll(() =>
      page.evaluate(() => new URLSearchParams(window.location.search).getAll("source_family").length)
    ).toBe(2)
    await page.getByRole("search", { name: "Filter opportunities" }).getByRole("button", { name: "Clear filters" }).click()

    const activity = page.getByTestId("filter-facet-activity")
    await activity.locator("summary").click()
    await activity.getByRole("checkbox", { name: "Save", exact: true }).check()
    await activity.getByRole("checkbox", { name: "Reject", exact: true }).check()
    await expect.poll(() =>
      page.evaluate(() => new URLSearchParams(window.location.search).getAll("activity_type").sort())
    ).toEqual(["reject", "save"])
    await page.getByRole("search", { name: "Filter opportunities" }).getByRole("button", { name: "Clear filters" }).click()

    const feedback = page.getByTestId("filter-facet-feedback")
    await feedback.locator("summary").click()
    await feedback.getByRole("checkbox", { name: "Good match", exact: true }).check()
    await feedback.getByRole("checkbox", { name: "Bad match", exact: true }).check()
    await expect.poll(() =>
      page.evaluate(() => new URLSearchParams(window.location.search).getAll("feedback_label").sort())
    ).toEqual(["bad_match", "good_match"])
    await page.getByRole("search", { name: "Filter opportunities" }).getByRole("button", { name: "Clear filters" }).click()

    await page.getByTestId("open-advanced-feed-filters").click()
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
    await expect(page.getByTestId("batch-action-toolbar")).toHaveCount(0)
    await expect(page.locator('input[type="checkbox"][aria-label^="Select "]:checked')).toHaveCount(0)
    expect(await page.locator('[data-testid^="opportunity-card-"]').count()).toBeLessThan(cardsBefore)
  })
})
