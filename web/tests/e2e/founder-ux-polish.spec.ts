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
    const controlIds = [
      "filter-track",
      "filter-decision",
      "filter-min-score",
      "filter-search",
      "filter-source-family",
      "filter-activity",
      "filter-feedback",
      "open-founder-filters",
      "open-facets-panel",
      "open-manual-sources-panel",
      "toggle-tutoring-lane",
    ]
    const controls = controlIds.map((id) => page.locator(`#${id}, [data-testid="${id}"]`).first())
    for (const control of controls) await expect(control).toBeVisible()

    const boxes = await Promise.all(controls.map((control) => control.boundingBox()))
    const visibleBoxes = boxes.filter((box): box is NonNullable<typeof box> => box !== null)
    expect(visibleBoxes).toHaveLength(controlIds.length)
    const bottoms = visibleBoxes.map((box) => box.y + box.height)
    const centers = visibleBoxes.map((box) => box.y + box.height / 2)
    expect(Math.max(...bottoms) - Math.min(...bottoms)).toBeLessThanOrEqual(2)
    expect(Math.max(...centers) - Math.min(...centers)).toBeLessThanOrEqual(2)
    expect(new Set(visibleBoxes.map((box) => Math.round(box.height))).size).toBe(1)

    await expect(page.getByTestId("source-health-summary")).toBeVisible()
    for (const key of ["healthy", "empty", "attention", "never-polled", "disabled"]) {
      await expect(page.getByTestId(`source-health-${key}`)).toContainText(/\d+/)
    }
    await expect(page.getByTestId("source-health-healthy")).toContainText("3")
    await expect(page.getByTestId("source-health-empty")).toContainText("1")
    await expect(page.getByTestId("source-health-disabled")).toContainText("1")
  })

  test("Founder actions and feedback persist into retrievable activity views", async ({ page }) => {
    await page.setViewportSize({ width: 1920, height: 1080 })
    await login(page)

    const activity = page.getByTestId("filter-activity")
    const feedback = page.getByTestId("filter-feedback")
    await expect(activity).toHaveValue("all")

    const firstCard = page.locator('[data-testid^="opportunity-card-"]').first()
    await expect(firstCard).toBeVisible()
    const firstTestId = await firstCard.getAttribute("data-testid")
    expect(firstTestId).toBeTruthy()
    const firstId = firstTestId!.replace("opportunity-card-", "")

    await firstCard.click()
    const dialog = page.getByRole("dialog")
    await dialog.getByRole("button", { name: "Good match" }).click()
    await expect(dialog.getByRole("button", { name: "Good match" })).toHaveAttribute("aria-pressed", "true")

    const strengths = dialog.getByTestId("scoring-strengths")
    const gaps = dialog.getByTestId("scoring-gaps")
    const unknowns = dialog.getByTestId("scoring-unknowns")
    const scoringBoxes = await Promise.all([strengths.boundingBox(), gaps.boundingBox(), unknowns.boundingBox()])
    expect(scoringBoxes.every(Boolean)).toBe(true)
    expect(scoringBoxes[0]!.y).toBeLessThan(scoringBoxes[1]!.y)
    expect(scoringBoxes[1]!.y).toBeLessThan(scoringBoxes[2]!.y)
    expect(Math.max(...scoringBoxes.map((box) => box!.width)) - Math.min(...scoringBoxes.map((box) => box!.width))).toBeLessThanOrEqual(2)

    await dialog.getByRole("button", { name: "Mark applied" }).click()
    await expect(dialog.getByText(/Current status:/)).toContainText("Marked applied")
    await page.keyboard.press("Escape")

    await activity.selectOption("applied")
    await expect(page.getByTestId(`opportunity-card-${firstId}`)).toBeVisible()
    await expect(page.getByTestId(`opportunity-card-${firstId}`)).toContainText("Applied")

    await feedback.selectOption("good_match")
    await expect(page.getByTestId(`opportunity-card-${firstId}`)).toBeVisible()
    await expect(page.getByTestId(`opportunity-card-${firstId}`)).toContainText("good match")

    await feedback.selectOption("")
    await activity.selectOption("all")

    const secondCard = page.locator('[data-testid^="opportunity-card-"]').first()
    const secondTestId = await secondCard.getAttribute("data-testid")
    expect(secondTestId).toBeTruthy()
    const secondId = secondTestId!.replace("opportunity-card-", "")
    await secondCard.click()
    await page.getByRole("dialog").getByRole("button", { name: "Dismiss" }).click()
    await page.keyboard.press("Escape")
    await activity.selectOption("dismissed")
    await expect(page.getByTestId(`opportunity-card-${secondId}`)).toBeVisible()
    await expect(page.getByTestId(`opportunity-card-${secondId}`)).toContainText("Dismissed")

    await activity.selectOption("all")
    const thirdCard = page.locator('[data-testid^="opportunity-card-"]').first()
    const thirdTestId = await thirdCard.getAttribute("data-testid")
    expect(thirdTestId).toBeTruthy()
    const thirdId = thirdTestId!.replace("opportunity-card-", "")
    await thirdCard.click()
    const thirdDialog = page.getByRole("dialog")
    await thirdDialog.getByRole("button", { name: "Snooze", exact: true }).click()
    await thirdDialog.getByLabel("Snooze until").fill("2026-10-10")
    await thirdDialog.getByRole("button", { name: "Confirm snooze" }).click()
    await page.keyboard.press("Escape")
    await activity.selectOption("snoozed")
    await expect(page.getByTestId(`opportunity-card-${thirdId}`)).toBeVisible()
    await expect(page.getByTestId(`opportunity-card-${thirdId}`)).toContainText("Snoozed")

    await activity.selectOption("any_activity")
    await expect(page.getByTestId(`opportunity-card-${firstId}`)).toBeVisible()
    await expect(page.getByTestId(`opportunity-card-${secondId}`)).toBeVisible()
    await expect(page.getByTestId(`opportunity-card-${thirdId}`)).toBeVisible()
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
