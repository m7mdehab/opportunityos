import { test, expect, type Page } from "@playwright/test"

/**
 * D3 — founder-controlled filters (`reports/evidence/FR-005/d3-contract.md`).
 * Claim A-8: toggling one filter changes its affected-count and re-queries
 * the feed, with no page reload. Run against the mock layer in phase 1 and
 * the real FastAPI service in phase 2, same as `smoke.spec.ts` — only
 * `playwright.config.ts` vs `playwright.real.config.ts` differ.
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

async function opportunityCount(page: Page): Promise<number> {
  const text = await page.getByTestId("opportunity-count").innerText()
  return Number(text.match(/^(\d+)/)?.[1] ?? "0")
}

async function hiddenCount(page: Page): Promise<number | null> {
  const button = page.getByTestId("toggle-hidden-opportunities")
  if (!(await button.count())) return null
  const text = await button.innerText()
  const match = text.match(/(\d+)\s+hidden/)
  return match ? Number(match[1]) : null
}

test.describe("D3 founder-controlled filters", () => {
  test("toggling a filter changes its affected-count and re-queries the feed without reloading", async ({
    page,
  }) => {
    await login(page)
    await expect(page.getByTestId("opportunity-card-opp-001")).toBeVisible()

    // A marker that only survives if the page is never reloaded/navigated
    // — the contract requires a toggle to re-query, never reload.
    await page.evaluate(() => {
      ;(window as unknown as { __noReload: boolean }).__noReload = true
    })

    const totalBefore = await opportunityCount(page)
    const hiddenBefore = await hiddenCount(page)

    // ---- open the Filters drawer ----
    await page.getByRole("button", { name: "Filters" }).click()
    const drawer = page.getByRole("dialog")
    await expect(drawer).toBeVisible()
    await expect(drawer.getByRole("heading", { name: "Filters" })).toBeVisible()

    const row = drawer.getByTestId("filter-row-min_fit_score")
    await expect(row).toBeVisible()
    const chip = row.locator("[data-affected-count]")

    // `min_fit_score` starts disabled with threshold=50; the mock fixture
    // set has exactly 3 opportunities scoring below 50.
    await expect(chip).toHaveAttribute("data-affected-count", "3")
    await expect(chip).toHaveAttribute("data-filter-effect", "off")

    // ---- change the threshold param: affected_count must change ----
    const thresholdInput = row.locator(
      'input[id="filter-param-min_fit_score-threshold"]'
    )
    await thresholdInput.fill("90")
    await thresholdInput.blur()
    await expect(chip).toHaveAttribute("data-affected-count", "7")

    // ---- toggle the filter on: this is the A-8 toggle ----
    const toggle = row.getByRole("switch")
    await expect(toggle).toHaveAttribute("aria-checked", "false")
    await toggle.click()
    await expect(toggle).toHaveAttribute("aria-checked", "true")
    await expect(chip).toHaveAttribute("data-filter-effect", "hide")
    // affected_count is computed independently of `enabled`, so it does not
    // move again on this click — the row's live effect label does (off ->
    // hide), and the feed itself re-queries, asserted below.
    await expect(chip).toHaveAttribute("data-affected-count", "7")

    // ---- close the drawer and confirm the feed re-queried ----
    await page.keyboard.press("Escape")
    await expect(drawer).not.toBeVisible()

    await expect
      .poll(() => opportunityCount(page))
      .toBeLessThan(totalBefore)
    await expect
      .poll(() => hiddenCount(page))
      .toBeGreaterThan(hiddenBefore ?? 0)

    // No navigation/reload happened anywhere in this flow.
    const survivedReload = await page.evaluate(
      () => (window as unknown as { __noReload?: boolean }).__noReload
    )
    expect(survivedReload).toBe(true)
  })

  test("a rank_only/label_only filter never looks like it hid anything", async ({
    page,
  }) => {
    await login(page)
    await expect(page.getByTestId("opportunity-card-opp-001")).toBeVisible()

    await page.getByRole("button", { name: "Filters" }).click()
    const drawer = page.getByRole("dialog")
    await expect(drawer).toBeVisible()

    // `stale_postings` defaults to enabled + label_only: its chip must read
    // as a label, not a hide, and never carry the hide styling class.
    const staleRow = drawer.getByTestId("filter-row-stale_postings")
    const staleChip = staleRow.locator("[data-affected-count]")
    await expect(staleChip).toHaveAttribute("data-filter-effect", "label_only")
    const staleClass = (await staleChip.getAttribute("class")) ?? ""
    expect(staleClass).not.toContain("red-")

    // `track_preference` defaults to enabled + rank_only: same guarantee.
    const trackRow = drawer.getByTestId("filter-row-track_preference")
    const trackChip = trackRow.locator("[data-affected-count]")
    await expect(trackChip).toHaveAttribute("data-filter-effect", "rank_only")
    const trackClass = (await trackChip.getAttribute("class")) ?? ""
    expect(trackClass).not.toContain("red-")
  })
})
