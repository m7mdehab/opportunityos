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
    await expect(dialog.getByTestId("detail-diagnostics")).not.toHaveAttribute("open")
    await expect(dialog.getByTestId("detail-fit-score")).toBeHidden()
    await dialog.getByTestId("detail-diagnostics").locator("summary").click()
    await expect(dialog.getByTestId("detail-fit-score")).toContainText(/Canonical fit score:/)
    const disclosure = dialog.getByTestId("full-description-disclosure")
    await expect(disclosure).not.toHaveAttribute("open")
    await disclosure.getByText("Show full job description").click()
    await expect(dialog.getByTestId("opportunity-description")).toBeVisible()
    await expect(dialog.getByRole("link", { name: "View original source" })).toBeVisible()
  })

  test("unified toolbar and numeric source health remain aligned and readable", async ({ page }) => {
    await page.setViewportSize({ width: 1920, height: 1080 })
    await login(page)
    await expect(page.getByLabel("Opportunity lists")).toBeVisible()
    await expect(page.locator("#filter-search")).toBeVisible()
    await expect(page.locator("#feed-sort")).toBeVisible()
    await expect(page.getByTestId("more-filters-dropdown").locator(":scope > summary")).toContainText("More filters")
    await expect(page.getByTestId("open-advanced-feed-filters")).toContainText("Advanced query")
    const diagnostics = page.getByRole("search", { name: "Filter opportunities" }).locator("details").filter({ hasText: "Diagnostics & tools" })
    await diagnostics.locator(":scope > summary").click()
    await expect(page.getByTestId("open-founder-filters")).toBeVisible()
    await expect(page.getByTestId("open-facets-panel")).toBeVisible()
    await expect(page.getByTestId("open-manual-sources-panel")).toBeVisible()
    await expect(page.getByTestId("toggle-tutoring-lane")).toBeVisible()
    await page.locator("details").filter({ hasText: "Operations" }).locator(":scope > summary").click()
    await expect(page.getByTestId("source-health-summary")).toBeVisible()
    for (const key of ["healthy", "empty", "attention", "never-polled", "disabled"]) {
      await expect(page.getByTestId(`source-health-${key}`)).toContainText(/\d+/)
    }
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
    const dialogFitsViewport = await dialog.evaluate((element) => {
      const box = element.getBoundingClientRect()
      return (
        box.left >= -0.5 &&
        box.right <= window.innerWidth + 0.5 &&
        element.scrollWidth <= element.clientWidth
      )
    })
    expect(dialogFitsViewport).toBe(true)
  })

  test("primary job lists use recommendation and existing tracker filters", async ({ page }) => {
    await login(page)
    const feedRequests: string[] = []
    page.on("request", (request) => {
      if (request.url().includes("/api/opportunities?")) feedRequests.push(request.url())
    })
    const lists = page.getByRole("navigation", { name: "Opportunity lists" })
    await lists.getByRole("button", { name: "Saved" }).click()
    await expect(page).toHaveURL(/feed_view=saved/)
    await expect.poll(() => feedRequests.some((url) => new URL(url).searchParams.getAll("activity_type").includes("save"))).toBe(true)
    await lists.getByRole("button", { name: "Applied" }).click()
    await expect(page).toHaveURL(/feed_view=applied/)
    await expect.poll(() => feedRequests.some((url) => new URL(url).searchParams.getAll("activity_type").includes("mark_applied"))).toBe(true)
    await lists.getByRole("button", { name: "Later" }).click()
    await expect(page).toHaveURL(/feed_view=later/)
    await expect.poll(() => feedRequests.some((url) => new URL(url).searchParams.getAll("activity_type").includes("snooze"))).toBe(true)
    await lists.getByRole("button", { name: "For You" }).click()
    await expect(page).not.toHaveURL(/feed_view=/)
    await expect.poll(() => feedRequests.some((url) => new URL(url).searchParams.getAll("recommendation_state").includes("for_you"))).toBe(true)
    await expect.poll(() => feedRequests.some((url) => new URL(url).searchParams.get("sort_by") === "for_you")).toBe(true)
  })

  test("advanced metadata and source health load only when those controls open", async ({ page }) => {
    const requests: string[] = []
    page.on("request", (request) => requests.push(new URL(request.url()).pathname))
    await login(page)
    await expect.poll(() => page.locator('[data-testid^="opportunity-card-"]').count()).toBeGreaterThan(0)
    expect(requests).not.toContain("/api/feed/filter-metadata")
    expect(requests).not.toContain("/api/sources/health")

    const filterMetadata = page.waitForRequest((request) => new URL(request.url()).pathname === "/api/feed/filter-metadata")
    await page.getByTestId("open-advanced-feed-filters").click()
    await filterMetadata
    await page.keyboard.press("Escape")

    const sourceHealth = page.waitForRequest((request) => new URL(request.url()).pathname === "/api/sources/health")
    await page.locator("details").filter({ hasText: "Operations" }).locator(":scope > summary").click()
    await sourceHealth
  })
})
