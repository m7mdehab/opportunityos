import { test, expect, type Page } from "@playwright/test"

/**
 * C1 UI half (facets + saved views), C4 UI half (hidden-reasons table +
 * the >10% over-hiding warning), and Master's addition #2 (the `language`
 * facet is permanently unavailable). See `filters.spec.ts` for the
 * `pageFetch`-via-`page.evaluate` rationale this file reuses verbatim
 * (MSW only intercepts `fetch()` calls made from inside the page).
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

interface FetchResult {
  ok: boolean
  status: number
  text: string
}

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

interface FacetJson {
  facet_id: string
  available: boolean
  unavailable_reason: string | null
  values: { value: string; count: number; state: string }[]
  excluded_count: number
  include: string[]
  exclude: string[]
}

async function getFacet(page: Page, facetId: string): Promise<FacetJson> {
  const result = await pageFetch(page, "/api/facets")
  const body = parseJson<{ facets: FacetJson[] }>(result, "GET /api/facets")
  const found = body.facets.find((f) => f.facet_id === facetId)
  expect(found, `${facetId} missing from GET /api/facets`).toBeTruthy()
  return found as FacetJson
}

async function resetFacet(page: Page, facetId: string) {
  await pageFetch(page, `/api/facets/${facetId}`, {
    method: "PUT",
    body: { include: [], exclude: [] },
  }).catch(() => undefined)
}

test.describe("C1 facets panel", () => {
  test.afterEach(async ({ page }) => {
    await resetFacet(page, "track")
    await resetFacet(page, "decision")
  })

  test("one include and one exclude exercised through the UI; 'Show N excluded' restores the rows", async ({
    page,
  }) => {
    await login(page)
    await expect(page.getByTestId("opportunity-count")).toBeVisible()

    const trackBefore = await getFacet(page, "track")
    const values = trackBefore.values.filter((v) => v.count > 0)
    expect(values.length, "need at least 2 distinct track values in this seed").toBeGreaterThan(1)
    const excludeValue = values[0].value

    const [drawerFacetsResponse] = await Promise.all([
      page.waitForResponse(
        (res) => res.request().method() === "GET" && res.url().includes("/api/facets")
      ),
      page.getByTestId("open-facets-panel").click(),
    ])
    expect(drawerFacetsResponse.ok(), await drawerFacetsResponse.text()).toBe(true)
    const panel = page.getByRole("dialog")
    await expect(panel).toBeVisible()

    const row = panel.getByTestId(`facet-value-track-${excludeValue}`)
    await expect(row).toBeVisible()
    const select = row.locator("select")

    const [excludePut, excludeFeed] = await Promise.all([
      page.waitForResponse(
        (res) => res.request().method() === "PUT" && res.url().includes("/api/facets/track")
      ),
      page.waitForResponse(
        (res) => res.request().method() === "GET" && res.url().includes("/api/opportunities?")
      ),
      select.selectOption("exclude"),
    ])
    expect(excludePut.status(), await excludePut.text()).toBe(200)
    expect(excludeFeed.ok(), await excludeFeed.text()).toBe(true)

    await expect(panel.getByTestId(`facet-chip-exclude-track-${excludeValue}`)).toBeVisible()

    const showExcludedButton = panel.getByTestId("facet-show-excluded-track")
    await expect(showExcludedButton).toBeVisible()
    await expect(showExcludedButton).toContainText(String(excludeValue))

    // Restores the rows: clears the facet back to off.
    const [resetPut] = await Promise.all([
      page.waitForResponse(
        (res) => res.request().method() === "PUT" && res.url().includes("/api/facets/track")
      ),
      showExcludedButton.click(),
    ])
    const resetBody = (await resetPut.json()) as { include: string[]; exclude: string[] }
    expect(resetBody.exclude).toEqual([])
    await expect(panel.getByTestId(`facet-chip-exclude-track-${excludeValue}`)).toHaveCount(0)
    await expect(showExcludedButton).toHaveCount(0)
  })

  test("the language facet renders as permanently unavailable", async ({ page }) => {
    await login(page)
    await expect(page.getByTestId("opportunity-count")).toBeVisible()
    await page.getByTestId("open-facets-panel").click()
    const panel = page.getByRole("dialog")
    await expect(panel).toBeVisible()

    const row = panel.getByTestId("facet-row-language")
    await expect(row).toBeVisible()
    const notice = row.locator('[data-facet-effect="unavailable"]')
    await expect(notice).toBeVisible()
    await expect(notice).toContainText("Unavailable")
    // No select control at all for an unavailable facet — never rendered
    // as though it works.
    await expect(row.locator("select")).toHaveCount(0)
  })
})

test.describe("C1 saved views", () => {
  test("create, select, set default, reload — the view survives", async ({ page }) => {
    await login(page)
    await expect(page.getByTestId("opportunity-count")).toBeVisible()

    const viewName = `E2E view ${Date.now()}`

    await page.getByTestId("open-facets-panel").click()
    const panel = page.getByRole("dialog")
    await expect(panel).toBeVisible()

    await panel.getByTestId("new-saved-view-name").fill(viewName)
    const [createResponse] = await Promise.all([
      page.waitForResponse(
        (res) => res.request().method() === "POST" && res.url().includes("/api/saved-views")
      ),
      panel.getByTestId("create-saved-view").click(),
    ])
    expect(createResponse.status(), await createResponse.text()).toBe(200)
    const created = (await createResponse.json()) as { id: string; is_default: boolean }
    expect(created.is_default).toBe(false)

    const row = panel.getByTestId(`saved-view-${created.id}`)
    await expect(row).toBeVisible()
    await expect(row).toContainText(viewName)

    const [defaultResponse] = await Promise.all([
      page.waitForResponse(
        (res) =>
          res.request().method() === "PUT" &&
          res.url().includes(`/api/saved-views/${created.id}`)
      ),
      panel.getByTestId(`saved-view-set-default-${created.id}`).click(),
    ])
    const defaultBody = (await defaultResponse.json()) as { is_default: boolean }
    expect(defaultBody.is_default).toBe(true)
    await expect(
      panel.getByTestId(`saved-view-set-default-${created.id}`)
    ).toBeDisabled()

    // "Select" it — applies its (empty) facet selection.
    await panel.getByTestId(`saved-view-select-${created.id}`).click()

    await page.reload()
    await page.getByTestId("open-facets-panel").click()
    const panelAfterReload = page.getByRole("dialog")
    await expect(panelAfterReload).toBeVisible()
    const rowAfterReload = panelAfterReload.getByTestId(`saved-view-${created.id}`)
    await expect(rowAfterReload).toBeVisible()
    await expect(rowAfterReload).toContainText(viewName)
    await expect(
      panelAfterReload.getByTestId(`saved-view-set-default-${created.id}`)
    ).toBeDisabled()
  })
})

test.describe("C4 hidden-reasons audit", () => {
  test.afterEach(async ({ page }) => {
    await pageFetch(page, "/api/filters/min_fit_score", {
      method: "PUT",
      body: { enabled: false, mode: "hide", params: { min_score: 0 } },
    }).catch(() => undefined)
  })

  test("the dashboard's HIDDEN number links to the table, and unhide-by-reason changes the visible count", async ({
    page,
  }) => {
    await login(page)
    await expect(page.getByTestId("opportunity-card-opp-001").or(page.getByTestId("opportunity-count"))).toBeVisible()

    // Construct a real hidden row: enable a hide-mode filter through the
    // live API, exactly as filters.spec.ts does (min_score=100 matches
    // every scored opportunity in any seed).
    const summaries = parseJson<{ items: { id: string; fit_score: number | null }[] }>(
      await pageFetch(page, "/api/opportunities?include_hidden=true&page_size=200"),
      "GET /api/opportunities"
    )
    const scoredCount = summaries.items.filter((o) => o.fit_score !== null).length
    expect(scoredCount, "no scored opportunity in this seed").toBeGreaterThan(0)

    await pageFetch(page, "/api/filters/min_fit_score", {
      method: "PUT",
      body: { enabled: true, mode: "hide", params: { min_score: 100 } },
    })

    const [dashboardResponse] = await Promise.all([
      page.waitForResponse(
        (res) => res.request().method() === "GET" && res.url().includes("/api/dashboard/daily")
      ),
      page.reload(),
    ])
    expect(dashboardResponse.ok(), await dashboardResponse.text()).toBe(true)
    await expect(page.getByTestId("opportunity-count")).toBeVisible()

    const hiddenStat = page.getByTestId("stat-hidden_by_filters")
    await expect(hiddenStat).toBeVisible()
    const hiddenBefore = Number(await hiddenStat.innerText())
    expect(hiddenBefore).toBeGreaterThan(0)

    const [reasonsResponse] = await Promise.all([
      page.waitForResponse(
        (res) => res.request().method() === "GET" && res.url().includes("/api/hidden-reasons")
      ),
      hiddenStat.click(),
    ])
    expect(reasonsResponse.ok(), await reasonsResponse.text()).toBe(true)
    const table = page.getByRole("dialog")
    await expect(table).toBeVisible()

    const row = table.getByTestId("hidden-reason-row-filter: min_fit_score")
    await expect(row).toBeVisible()

    const [unhideResponse, feedAfterUnhide] = await Promise.all([
      page.waitForResponse(
        (res) =>
          res.request().method() === "POST" && res.url().includes("/api/hidden-reasons/unhide")
      ),
      page.waitForResponse(
        (res) => res.request().method() === "GET" && res.url().includes("/api/opportunities?")
      ),
      table.getByTestId("unhide-reason-filter: min_fit_score").click(),
    ])
    expect(unhideResponse.status(), await unhideResponse.text()).toBe(200)
    expect(feedAfterUnhide.ok(), await feedAfterUnhide.text()).toBe(true)
    const feedBody = (await feedAfterUnhide.json()) as { hidden_count: number }
    expect(feedBody.hidden_count).toBeLessThan(hiddenBefore)
  })

  test("the >10% over-hiding warning is visible once constructed", async ({ page }) => {
    await login(page)
    await expect(page.getByTestId("opportunity-count")).toBeVisible()

    await expect(page.getByTestId("over-hiding-warning")).toHaveCount(0)

    const summaries = parseJson<{ items: { id: string; fit_score: number | null }[] }>(
      await pageFetch(page, "/api/opportunities?include_hidden=true&page_size=200"),
      "GET /api/opportunities"
    )
    const scoredCount = summaries.items.filter((o) => o.fit_score !== null).length
    expect(scoredCount).toBeGreaterThan(0)

    await pageFetch(page, "/api/filters/min_fit_score", {
      method: "PUT",
      body: { enabled: true, mode: "hide", params: { min_score: 100 } },
    })

    const [dashboardResponse] = await Promise.all([
      page.waitForResponse(
        (res) => res.request().method() === "GET" && res.url().includes("/api/dashboard/daily")
      ),
      page.reload(),
    ])
    const dashboardBody = (await dashboardResponse.json()) as {
      series: { unique_new: number; hidden_by_filters: number }[]
    }
    const today = dashboardBody.series[0]
    expect(
      today.hidden_by_filters / today.unique_new,
      "this construction must actually exceed 10% for the warning to be meaningful"
    ).toBeGreaterThan(0.1)

    const warning = page.getByTestId("over-hiding-warning")
    await expect(warning).toBeVisible()
    await expect(warning).toContainText(`${today.hidden_by_filters} of ${today.unique_new}`)
  })
})
