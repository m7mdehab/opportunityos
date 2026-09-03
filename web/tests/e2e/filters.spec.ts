import { test, expect, type Page, type Locator } from "@playwright/test"

/**
 * D3 — founder-controlled filters (`reports/evidence/FR-005/d3-contract.md`).
 * Claim A-8: toggling one filter changes its affected-count and re-queries
 * the feed, with no page reload. Run against the mock layer in phase 1 and
 * the real FastAPI service + real PostgreSQL in phase 2 — this file is in
 * both `playwright.config.ts` and `playwright.real.config.ts`'s `testMatch`.
 *
 * Every assertion here is *behavioural*, not a fixture literal: no absolute
 * `data-affected-count` value is ever asserted, only that it is a valid
 * non-negative integer, that it moves in the direction a param change can
 * only move it in, and that toggling the switch changes the feed. An
 * earlier version of this spec asserted exact counts ("3", "7") that were
 * true of the MSW mock's fixture set and happened to also be true of
 * `tests/e2e/seed_real.py`'s seed (it borrows the same synthetic fit
 * scores) — but that was a coincidence, not a contract, and asserting it
 * is exactly the FR-004 mistake this brief exists to not repeat: a mock
 * phase whose "real" run only re-proves what the mock already assumed.
 * See `filters-unavailable.spec.ts` for why that one test stays mock-only.
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
  // Zero visible opportunities is a real, valid state (page.tsx renders an
  // empty-state card instead of the "N opportunities" paragraph then) —
  // aggressively enabling a `hide` filter in this file can legitimately
  // reach it, so this must return 0 rather than time out waiting for an
  // element that correctly isn't there.
  const el = page.getByTestId("opportunity-count")
  if (!(await el.count())) return 0
  const text = await el.innerText()
  return Number(text.match(/^(\d+)/)?.[1] ?? "0")
}

async function hiddenCount(page: Page): Promise<number> {
  const button = page.getByTestId("toggle-hidden-opportunities")
  if (!(await button.count())) return 0
  const text = await button.innerText()
  const match = text.match(/(\d+)\s+hidden/)
  return match ? Number(match[1]) : 0
}

/** Reads `data-affected-count` off a filter row's chip and asserts it is a
 * well-formed non-negative integer — the one structural property every
 * implementation must satisfy, regardless of what data is seeded. */
async function readAffectedCount(chip: Locator): Promise<number> {
  const raw = await chip.getAttribute("data-affected-count")
  const n = Number(raw)
  expect(
    Number.isInteger(n) && n >= 0,
    `data-affected-count should be a non-negative integer, was ${JSON.stringify(raw)}`
  ).toBe(true)
  return n
}

test.describe("D3 founder-controlled filters", () => {
  // Both filters this file enables are off by default; reset them after
  // every test via a direct API call (not the UI, to keep this fast) so
  // state never leaks into another test in this file, into
  // `smoke.spec.ts` (which runs later, alphabetically, against the same
  // mock singleton or the same real database row), or into a re-run.
  test.afterEach(async ({ page }) => {
    await page.request
      .put("/api/filters/min_fit_score", {
        data: { enabled: false, mode: "hide", params: { min_score: 0 } },
      })
      .catch(() => undefined)
    await page.request
      .put("/api/filters/compensation_floor", {
        data: {
          enabled: false,
          mode: "rank_only",
          params: { floor: 0, currency: null },
        },
      })
      .catch(() => undefined)
  })

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

    // `min_fit_score` starts disabled — structural, per the contract's
    // default table, true regardless of seeded data.
    await expect(chip).toHaveAttribute("data-filter-effect", "off")
    const beforeParamCount = await readAffectedCount(chip)

    // ---- change the numeric param: affected_count must move, and only
    // upward — raising a minimum-score threshold can never stop matching
    // an opportunity that already matched a lower one. The default param
    // is 0, which can never match anything (`fit_score` is never
    // negative); a very high value matches every *scored* opportunity.
    // The one param input on this row, found generically rather than by a
    // hard-coded id, since the real API's param key (`min_score`) differs
    // from what this mock used before this repair (`threshold`) — this
    // spec must not re-hard-code either name. ----
    const paramInput = row.locator('input[type="number"]').first()
    await expect(paramInput).toBeVisible()
    await paramInput.fill("1000")
    await paramInput.blur()

    await expect
      .poll(() => readAffectedCount(chip), {
        message: "affected_count did not update after the param change",
      })
      .toBeGreaterThan(beforeParamCount)

    // ---- toggle the filter on: this is the A-8 toggle ----
    const toggle = row.getByRole("switch")
    await expect(toggle).toHaveAttribute("aria-checked", "false")
    await toggle.click()
    await expect(toggle).toHaveAttribute("aria-checked", "true")
    await expect(chip).toHaveAttribute("data-filter-effect", "hide")

    // ---- close the drawer and confirm the feed re-queried ----
    await page.keyboard.press("Escape")
    await expect(drawer).not.toBeVisible()

    await expect
      .poll(() => opportunityCount(page))
      .toBeLessThan(totalBefore)
    await expect
      .poll(() => hiddenCount(page))
      .toBeGreaterThan(hiddenBefore)

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

    // `geo_eligibility` defaults to enabled + label_only: its chip must
    // read as a label, not a hide, and never carry the hide styling class
    // — a structural property of the filter's *mode*, independent of how
    // many opportunities it actually matches.
    const geoRow = drawer.getByTestId("filter-row-geo_eligibility")
    const geoChip = geoRow.locator("[data-affected-count]")
    await expect(geoChip).toHaveAttribute("data-filter-effect", "label_only")
    const geoClass = (await geoChip.getAttribute("class")) ?? ""
    expect(geoClass).not.toContain("red-")

    // `compensation_floor` is rank_only but starts disabled; enable it and
    // confirm the same guarantee holds once it is actually acting, not
    // just when it happens to be off.
    const compRow = drawer.getByTestId("filter-row-compensation_floor")
    await compRow.getByRole("switch").click()
    const compChip = compRow.locator("[data-affected-count]")
    await expect(compChip).toHaveAttribute("data-filter-effect", "rank_only")
    const compClass = (await compChip.getAttribute("class")) ?? ""
    expect(compClass).not.toContain("red-")
  })
})
