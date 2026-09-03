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
 *    and how many opportunities have any `fit_score` at all) are read
 *    directly from `GET /api/filters` / `GET /api/opportunities` before
 *    touching the UI, never assumed from the contract's stated defaults —
 *    a prior failed run, or a fresh seed, must not change what this spec
 *    can prove.
 *  - Every UI interaction that triggers a `PUT`/`GET` is paired with
 *    `page.waitForResponse` for that exact request, and the response body
 *    itself is asserted on. This spec's first version polled the DOM with
 *    a short, fixed window instead; that produced a false failure
 *    ("affected_count did not update") on a slower/loaded real Postgres
 *    instance where `api/filters.py::build_filter_contexts` (a
 *    per-opportunity query) legitimately took longer than the poll's
 *    timeout — the request had not returned yet, not that it never fired
 *    or was rejected. Waiting on the response itself removes that race
 *    entirely and, as a side effect, is what actually diagnoses a genuine
 *    failure (fires? status? body?) instead of reporting a vague timeout.
 *  - The one non-trivial numeric assertion (raising `min_score` above
 *    every real score must match exactly every *scored* opportunity) is
 *    computed from data read at runtime (`GET /api/opportunities
 *    ?include_hidden=true`), never a hard-coded seed fact.
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

/** How many opportunities currently have any `fit_score` at all —
 * `include_hidden=true` so a `hide`-mode filter from a prior test can't
 * hide the answer, and `decision`/`fit_score` are never touched by any
 * filter (contract §2), so this number is stable regardless of filter
 * settings. This is exactly the population `min_fit_score` can ever match
 * once its threshold is raised above every real score. */
async function getScoredOpportunityCount(page: Page): Promise<number> {
  const result = await pageFetch(page, "/api/opportunities?include_hidden=true&page_size=200")
  const body = parseJson<{ items: Array<{ fit_score: number | null }> }>(
    result,
    "GET /api/opportunities"
  )
  return body.items.filter((o) => o.fit_score !== null).length
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
    const scoredCount = await getScoredOpportunityCount(page)
    expect(
      scoredCount,
      "no opportunity in this seed has a fit_score -- min_fit_score's path is untestable against it"
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

    // ---- change the numeric param to a value above every possible score
    // (fit_score is documented 0-100; this is safely above any seed's
    // range), synchronised on the actual PUT round trip. The one param
    // input on this row is found generically (input[type=number]) rather
    // than by a hard-coded id, since the real API's param key
    // (min_score) differs from what this mock used before an earlier
    // repair (threshold) -- this spec must not re-hard-code either
    // name. ----
    const paramInput = row.locator('input[type="number"]').first()
    await expect(paramInput).toBeVisible()
    await paramInput.fill("1000000")

    const [paramPutResponse] = await Promise.all([
      page.waitForResponse(
        (res) =>
          res.request().method() === "PUT" &&
          res.url().includes("/api/filters/min_fit_score"),
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

    // The re-query this toggle caused actually changed what it hides. If
    // this fails against the real stack with feedBody.total unchanged and
    // feedBody's items all carrying hidden_by: [] despite enablePutBody
    // above showing enabled: true / the correct params / a non-zero
    // affected_count, that is not this spec racing the network (both PUT
    // responses and this GET are awaited via page.waitForResponse before
    // any assertion runs) -- it was reproduced this way against a real
    // FastAPI + real Postgres run and traced to api/routes_api.py::
    // list_opportunities's apply_filters(ctx, filter_settings) call
    // disagreeing with api/filters.py::filter_affected_count's identical
    // matcher call for the same filter/params/opportunities in the same
    // request cycle, reproducing on roughly 3 of 4 runs (never on the mock
    // config). Fixing that is outside this file's (web/**) scope.
    expect(feedBody.total).toBeLessThan(totalBefore)
    expect(feedBody.hidden_count).toBeGreaterThan(hiddenBefore)

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
