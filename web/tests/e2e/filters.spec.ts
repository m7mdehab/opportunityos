import { test, expect, type Page } from "@playwright/test"

/**
 * D3 — founder-controlled filters (`reports/evidence/FR-005/d3-contract.md`).
 * Claim A-8: toggling one filter changes its affected-count and re-queries
 * the feed, with no page reload. Run against the mock layer in phase 1 and
 * the real FastAPI service + real PostgreSQL in phase 2 — this file is in
 * both `playwright.config.ts` and `playwright.real.config.ts`'s `testMatch`.
 *
 * Every assertion here is *behavioural* and *synchronised on the actual
 * network round trip*, not a fixture literal and not a fixed DOM-poll
 * window:
 *  - Baselines (`min_fit_score`'s current `enabled`/`mode`/`affected_count`,
 *    and every opportunity's `fit_score`/`hidden_by`) are read directly
 *    from `GET /api/filters` / `GET /api/opportunities` before touching the
 *    UI, never assumed from the contract's stated defaults — a prior
 *    failed run, or a fresh seed, must not change what this spec can prove.
 *  - Every UI interaction that triggers a `PUT`/`GET` is paired with
 *    `page.waitForResponse` for that exact request, and the response body
 *    itself is asserted on (status, and the field the interaction was
 *    supposed to change) — this is what makes a genuine failure
 *    self-diagnosing (fires? status? body?) instead of a vague timeout, and
 *    it is what actually caught that an earlier version of this spec used
 *    `min_score` values api/filters.py's own validation rejects with a 422
 *    (see the second test below) — a defect in the *spec*, not the API.
 *  - `min_score` is set to 100, the top of the documented fit_score scale
 *    (and the top of the range `api/filters.py::_validate_min_fit_score_
 *    params` accepts) — a contract fact, not a fixture literal — and the
 *    exact number of opportunities that transition is computed from a live
 *    read (`GET /api/opportunities?include_hidden=true`), correctly
 *    accounting for overlap with whatever `red_lines`/`excluded_industries`
 *    /etc. already hide, never assumed to be zero.
 *
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

interface FounderFilterJson {
  filter_id: string
  enabled: boolean
  mode: string
  affected_count: number
  [key: string]: unknown
}

interface FetchResult {
  ok: boolean
  status: number
  text: string
}

/** Every baseline/reset in this file goes through the *page's own*
 * `fetch()` (via `page.evaluate`), never `page.request`. `page.request`
 * makes its call from Playwright's Node process, outside the browser
 * entirely, so in the mock config it bypasses the MSW service worker
 * (which only intercepts `fetch()` calls made from inside the page) and
 * hits the bare Next.js server instead — a 500, not a real answer. Calling
 * from inside the page is also what actually exercises the same code path
 * (`lib/api/client.ts`'s `fetch`) the app itself uses in both configs. */
async function pageFetch(
  page: Page,
  path: string,
  init?: { method?: string; body?: unknown }
): Promise<FetchResult> {
  return page.evaluate(
    async ({ path: p, init: i }) => {
      const res = await fetch(p, {
        method: i?.method,
        headers: i?.body !== undefined ? { "Content-Type": "application/json" } : undefined,
        body: i?.body !== undefined ? JSON.stringify(i.body) : undefined,
      })
      const text = await res.text()
      return { ok: res.ok, status: res.status, text }
    },
    { path, init }
  )
}

function parseJson<T>(result: FetchResult, context: string): T {
  expect(result.ok, `${context} returned ${result.status}: ${result.text}`).toBe(true)
  return JSON.parse(result.text) as T
}

/** Reads the live filter list straight from the API (bypassing the drawer
 * entirely), so every baseline in this file is an actual reading, never an
 * assumption about what a fresh seed or a prior test left behind. */
async function getFilter(page: Page, filterId: string): Promise<FounderFilterJson> {
  const result = await pageFetch(page, "/api/filters")
  const body = parseJson<{ filters: FounderFilterJson[] }>(result, "GET /api/filters")
  const found = body.filters.find((f) => f.filter_id === filterId)
  expect(found, `${filterId} missing from GET /api/filters`).toBeTruthy()
  return found as FounderFilterJson
}

/** Every opportunity's `fit_score` and current `hidden_by`, read with
 * `include_hidden=true&include_tracked=true` so a `hide`-mode filter from a prior test can't
 * hide the answer. `decision`/`fit_score` are never touched by any filter
 * (contract §2), so `fit_score` here is stable regardless of filter
 * settings; `hidden_by` is what lets the caller compute an *exact*
 * transition when enabling another `hide` filter, correctly accounting
 * for overlap with whatever `red_lines`/`excluded_industries`/etc. are
 * already hiding, rather than assuming no overlap. */
async function getOpportunitySummaries(
  page: Page
): Promise<Array<{ fit_score: number | null; hidden_by: string[] }>> {
  const result = await pageFetch(page, "/api/opportunities?include_hidden=true&include_tracked=true&page_size=200")
  const body = parseJson<{ items: Array<{ fit_score: number | null; hidden_by: string[] }> }>(
    result,
    "GET /api/opportunities"
  )
  return body.items
}

test.describe("D3 founder-controlled filters", () => {
  // Both filters this file enables are off by default; reset them after
  // every test via a direct API call (not the UI, to keep this fast) so
  // state never leaks into another test in this file, into
  // `smoke.spec.ts` (which runs later, alphabetically, against the same
  // mock singleton or the same real database row), or into a re-run.
  // Playwright runs `afterEach` regardless of whether the test passed or
  // failed (it is not conditional on the test body's outcome), and the
  // reset's own outcome is logged rather than silently swallowed, so a
  // reset that itself fails is visible in this test's output instead of
  // masquerading as "state leaked for no reason" in a later run.
  test.afterEach(async ({ page }) => {
    const resetMinFitScore = await pageFetch(page, "/api/filters/min_fit_score", {
      method: "PUT",
      body: { enabled: false, mode: "hide", params: { min_score: 0 } },
    }).catch((err) => {
      console.error("afterEach: PUT /api/filters/min_fit_score failed to send:", err)
      return null
    })
    if (resetMinFitScore && !resetMinFitScore.ok) {
      console.error(
        `afterEach: PUT /api/filters/min_fit_score returned ${resetMinFitScore.status}: ${resetMinFitScore.text}`
      )
    }

    const resetCompFloor = await pageFetch(page, "/api/filters/compensation_floor", {
      method: "PUT",
      body: { enabled: false, mode: "rank_only", params: { floor: 0, currency: null } },
    }).catch((err) => {
      console.error("afterEach: PUT /api/filters/compensation_floor failed to send:", err)
      return null
    })
    if (resetCompFloor && !resetCompFloor.ok) {
      console.error(
        `afterEach: PUT /api/filters/compensation_floor returned ${resetCompFloor.status}: ${resetCompFloor.text}`
      )
    }
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

    // ---- authoritative baselines, read directly from the API ----
    const summariesBefore = await getOpportunitySummaries(page)
    const scoredCount = summariesBefore.filter((o) => o.fit_score !== null).length
    expect(
      scoredCount,
      "no opportunity in this seed has a fit_score -- min_fit_score's path is untestable against it"
    ).toBeGreaterThan(0)
    // Exactly how many *additional* items min_score=100 will hide once
    // enabled: scored opportunities not already hidden by some other
    // filter (red_lines, excluded_industries, ...). Computed live so this
    // holds regardless of what those already happen to be hiding.
    const expectedNewlyHidden = summariesBefore.filter(
      (o) => o.fit_score !== null && o.hidden_by.length === 0
    ).length
    expect(
      expectedNewlyHidden,
      "every scored opportunity in this seed is already hidden by another filter -- min_fit_score's toggle would be vacuous here"
    ).toBeGreaterThan(0)
    const minFitBefore = await getFilter(page, "min_fit_score")

    const totalBefore = await opportunityCount(page)
    const hiddenBefore = await hiddenCount(page)

    // ---- open the Filters drawer, synchronised on its own fetch ----
    const [drawerFiltersResponse] = await Promise.all([
      page.waitForResponse(
        (res) => res.request().method() === "GET" && res.url().includes("/api/filters"),
        { timeout: 15_000 }
      ),
      page.getByRole("button", { name: "Filters" }).click(),
    ])
    expect(
      drawerFiltersResponse.ok(),
      `drawer's GET /api/filters returned ${drawerFiltersResponse.status()}: ${await drawerFiltersResponse.text()}`
    ).toBe(true)
    const drawer = page.getByRole("dialog")
    await expect(drawer).toBeVisible()
    await expect(drawer.getByRole("heading", { name: "Filters" })).toBeVisible()

    const row = drawer.getByTestId("filter-row-min_fit_score")
    await expect(row).toBeVisible()
    const chip = row.locator("[data-affected-count]")

    const expectedEffectBefore = minFitBefore.enabled ? minFitBefore.mode : "off"
    await expect(chip).toHaveAttribute("data-filter-effect", expectedEffectBefore)
    await expect(chip).toHaveAttribute(
      "data-affected-count",
      String(minFitBefore.affected_count)
    )

    // ---- change the numeric param to 100, the top of the documented
    // fit_score scale (api/filters.py::_validate_min_fit_score_params
    // rejects anything outside [0, 100] -- see the 422 test below), so
    // "fit_score < 100" matches every scored opportunity in any seed
    // without needing a value above the valid range. The one param input
    // on this row is found generically (input[type=number]) rather than
    // by a hard-coded id, since the real API's param key (min_score)
    // differs from what this mock used before an earlier repair
    // (threshold) -- this spec must not re-hard-code either name. ----
    const paramInput = row.locator('input[type="number"]').first()
    await expect(paramInput).toBeVisible()
    await paramInput.fill("100")

    // This param edit *also* triggers FiltersDrawer's onFiltersChanged
    // (the filter is still disabled, so it changes nothing visible), which
    // fires its own GET /api/opportunities?...include_hidden=false. That
    // request must be allowed to finish here, not left in flight: on a
    // real backend slow enough for it to still be pending when the enable
    // step below registers its own waitForResponse for the identical URL
    // pattern, that second registration could resolve on *this* stale,
    // still-disabled response instead of the fresh one the toggle click
    // causes -- which is exactly what produced a false "nothing changed"
    // failure here before this fix (feedBody.total stuck at its
    // before-toggle value). Waiting for both responses at every step that
    // triggers a re-query removes that ambiguity entirely.
    const [paramPutResponse] = await Promise.all([
      page.waitForResponse(
        (res) =>
          res.request().method() === "PUT" &&
          res.url().includes("/api/filters/min_fit_score"),
        { timeout: 15_000 }
      ),
      page.waitForResponse(
        (res) =>
          res.request().method() === "GET" &&
          res.url().includes("/api/opportunities?") &&
          res.url().includes("include_hidden=false"),
        { timeout: 15_000 }
      ),
      paramInput.blur(),
    ])
    expect(
      paramPutResponse.status(),
      `PUT /api/filters/min_fit_score (param change) returned ${paramPutResponse.status()}: ${await paramPutResponse.text()}`
    ).toBe(200)
    const paramPutBody = (await paramPutResponse.json()) as FounderFilterJson
    // Every scored opportunity now matches; nothing unscored ever can
    // (api/filters.py::_min_fit_score_matches returns False when
    // ctx.fit_score is None) -- an exact, dynamically-computed
    // expectation, not a fixture literal.
    expect(paramPutBody.affected_count).toBe(scoredCount)
    await expect(chip).toHaveAttribute("data-affected-count", String(scoredCount))

    // ---- toggle the filter on: this is the A-8 toggle. Also wait for the
    // feed re-query this triggers (FiltersDrawer's onFiltersChanged calls
    // refreshList()), so the assertions below never race a still-in-flight
    // request either. ----
    const toggle = row.getByRole("switch")
    await expect(toggle).toHaveAttribute(
      "aria-checked",
      minFitBefore.enabled ? "true" : "false"
    )

    const [enablePutResponse, feedResponse] = await Promise.all([
      page.waitForResponse(
        (res) =>
          res.request().method() === "PUT" &&
          res.url().includes("/api/filters/min_fit_score"),
        { timeout: 15_000 }
      ),
      page.waitForResponse(
        (res) =>
          res.request().method() === "GET" &&
          res.url().includes("/api/opportunities?") &&
          res.url().includes("include_hidden=false"),
        { timeout: 15_000 }
      ),
      toggle.click(),
    ])
    expect(
      enablePutResponse.status(),
      `PUT /api/filters/min_fit_score (enable) returned ${enablePutResponse.status()}: ${await enablePutResponse.text()}`
    ).toBe(200)
    const enablePutBody = (await enablePutResponse.json()) as FounderFilterJson
    expect(enablePutBody.enabled).toBe(true)
    expect(feedResponse.ok(), await feedResponse.text()).toBe(true)
    const feedBody = (await feedResponse.json()) as {
      total: number
      hidden_count: number
    }

    await expect(toggle).toHaveAttribute("aria-checked", "true")
    await expect(chip).toHaveAttribute("data-filter-effect", enablePutBody.mode)

    // The re-query this toggle caused actually changed what it hides, by
    // exactly the amount computed above -- not a vague direction, and not
    // assuming no overlap with whatever else is already hiding rows.
    expect(feedBody.total).toBe(totalBefore - expectedNewlyHidden)
    expect(feedBody.hidden_count).toBe(hiddenBefore + expectedNewlyHidden)

    // ---- close the drawer; the UI should already reflect the response
    // above (no further network round trip needed for that) ----
    await page.keyboard.press("Escape")
    await expect(drawer).not.toBeVisible()

    await expect
      .poll(() => opportunityCount(page), { timeout: 10_000 })
      .toBe(feedBody.total)
    await expect
      .poll(() => hiddenCount(page), { timeout: 10_000 })
      .toBe(feedBody.hidden_count)

    // No navigation/reload happened anywhere in this flow.
    const survivedReload = await page.evaluate(
      () => (window as unknown as { __noReload?: boolean }).__noReload
    )
    expect(survivedReload).toBe(true)
  })

  test("an out-of-range param is rejected with 422, and the feed keeps working", async ({
    page,
  }) => {
    // Council-found defect: api/filters.py::_validate_min_fit_score_params
    // rejects a min_score outside [0, 100] (fit_score's documented scale)
    // before anything is committed. Pinning this both proves the guard and
    // is what caught an earlier version of this very spec sending a
    // value (well above 100) that the API had every right to reject.
    await login(page)
    await expect(page.getByTestId("opportunity-card-opp-001")).toBeVisible()

    const totalBefore = await opportunityCount(page)

    const [drawerFiltersResponse] = await Promise.all([
      page.waitForResponse(
        (res) => res.request().method() === "GET" && res.url().includes("/api/filters"),
        { timeout: 15_000 }
      ),
      page.getByRole("button", { name: "Filters" }).click(),
    ])
    expect(drawerFiltersResponse.ok(), await drawerFiltersResponse.text()).toBe(true)
    const drawer = page.getByRole("dialog")
    await expect(drawer).toBeVisible()

    const row = drawer.getByTestId("filter-row-min_fit_score")
    await expect(row).toBeVisible()
    const paramInput = row.locator('input[type="number"]').first()
    await expect(paramInput).toBeVisible()
    await paramInput.fill("1000000")

    const [rejectedResponse] = await Promise.all([
      page.waitForResponse(
        (res) =>
          res.request().method() === "PUT" &&
          res.url().includes("/api/filters/min_fit_score"),
        { timeout: 15_000 }
      ),
      paramInput.blur(),
    ])
    expect(rejectedResponse.status(), await rejectedResponse.text()).toBe(422)

    // The founder sees that it failed, not silence.
    await expect(drawer.getByRole("alert")).toBeVisible()

    // A rejected write must not partially apply anywhere.
    await page.keyboard.press("Escape")
    await expect(drawer).not.toBeVisible()
    await expect(page.getByTestId("opportunity-card-opp-001")).toBeVisible()
    expect(await opportunityCount(page)).toBe(totalBefore)
  })

  test("a rank_only/label_only filter never looks like it hid anything", async ({
    page,
  }) => {
    await login(page)
    await expect(page.getByTestId("opportunity-card-opp-001")).toBeVisible()

    const compBefore = await getFilter(page, "compensation_floor")

    const [drawerFiltersResponse] = await Promise.all([
      page.waitForResponse(
        (res) => res.request().method() === "GET" && res.url().includes("/api/filters"),
        { timeout: 15_000 }
      ),
      page.getByRole("button", { name: "Filters" }).click(),
    ])
    expect(drawerFiltersResponse.ok(), await drawerFiltersResponse.text()).toBe(true)
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

    // `compensation_floor` is rank_only; enable it (from whatever its
    // current state actually is, read above, not assumed) and confirm the
    // same guarantee holds once it is actually acting, not just when it
    // happens to be off.
    const compRow = drawer.getByTestId("filter-row-compensation_floor")
    const [compPutResponse] = await Promise.all([
      page.waitForResponse(
        (res) =>
          res.request().method() === "PUT" &&
          res.url().includes("/api/filters/compensation_floor"),
        { timeout: 15_000 }
      ),
      compRow.getByRole("switch").click(),
    ])
    expect(
      compPutResponse.status(),
      `PUT /api/filters/compensation_floor returned ${compPutResponse.status()}: ${await compPutResponse.text()}`
    ).toBe(200)
    const compPutBody = (await compPutResponse.json()) as FounderFilterJson
    expect(compPutBody.enabled).toBe(!compBefore.enabled)
    expect(compPutBody.mode).toBe("rank_only")

    const compChip = compRow.locator("[data-affected-count]")
    await expect(compChip).toHaveAttribute("data-filter-effect", "rank_only")
    const compClass = (await compChip.getAttribute("class")) ?? ""
    expect(compClass).not.toContain("red-")
  })
})
