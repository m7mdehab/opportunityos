import { test, expect, type Page } from "@playwright/test"
import AxeBuilder from "@axe-core/playwright"

const FOUNDER_PASSWORD = process.env.E2E_FOUNDER_PASSWORD ?? "founder-mock-pass"
const VIEW_NAME = "A-27 synthetic query"

async function login(page: Page) {
  await page.goto("/")
  await expect(page).toHaveURL(/\/login$/)
  await page.getByLabel("Password").fill(FOUNDER_PASSWORD)
  await page.getByRole("button", { name: "Sign in" }).click()
  await expect(page).toHaveURL(/\/$/)
  await expect(page.getByTestId("workspace-jobs")).toBeVisible()
  await expect(page.locator('[data-testid^="opportunity-card-"]').first()).toBeVisible()
}

async function expectNoHorizontalOverflow(page: Page, surface: string) {
  const dimensions = await page.evaluate(() => ({
    viewport: window.innerWidth,
    client: document.documentElement.clientWidth,
    document: document.documentElement.scrollWidth,
    body: document.body.scrollWidth,
    offscreen: Array.from(document.querySelectorAll<HTMLElement>("body *"))
      .map((element) => {
        const rect = element.getBoundingClientRect()
        return {
          tag: element.tagName,
          id: element.id,
          testId: element.dataset.testid,
          className: typeof element.className === "string" ? element.className : "",
          left: Math.round(rect.left),
          right: Math.round(rect.right),
          width: Math.round(rect.width),
          scrollWidth: element.scrollWidth,
          clientWidth: element.clientWidth,
        }
      })
      .filter((element) => element.right > window.innerWidth + 1 || element.left < -1)
      .sort((left, right) => right.right - left.right)
      .slice(0, 10),
  }))
  expect(
    Math.max(dimensions.document, dimensions.body),
    `${surface} overflowed horizontally: ${JSON.stringify(dimensions)}`,
  ).toBeLessThanOrEqual(dimensions.client)
}

async function expectAxeClean(page: Page, surface: string) {
  const results = await new AxeBuilder({ page }).analyze()
  expect(results.violations, `${surface} axe violations:\n${JSON.stringify(results.violations, null, 2)}`).toEqual([])
}

async function quickAction(page: Page, id: string, action: "save" | "apply" | "reject") {
  const [response] = await Promise.all([
    page.waitForResponse((item) => item.request().method() === "POST" && item.url().includes("/actions")),
    page.getByTestId(`quick-${action}-${id}`).click(),
  ])
  expect(response.status(), await response.text()).toBe(200)
  await expect(page.getByTestId(`opportunity-card-${id}`)).toHaveCount(0)
}

async function undoLatestAction(page: Page, restoredId: string) {
  const [response] = await Promise.all([
    page.waitForResponse((item) => item.request().method() === "POST" && item.url().includes("/restore")),
    page.getByTestId("undo-tracker-action").click(),
  ])
  expect(response.status(), await response.text()).toBe(200)
  expect(((await response.json()) as { tracker_state: string }).tracker_state).toBe("to_review")
  await expect(page.getByTestId(`opportunity-card-${restoredId}`)).toBeVisible()
}

for (const viewport of [
  { name: "desktop", width: 1280, height: 844 },
  { name: "390px mobile", width: 390, height: 844 },
]) {
  test(`FR-008 A-27 responsive, accessible journey at ${viewport.name}`, async ({ page }) => {
    test.setTimeout(90_000)
    await page.setViewportSize({ width: viewport.width, height: viewport.height })
    await login(page)
    await expectNoHorizontalOverflow(page, "feed")
    await expectAxeClean(page, "feed")

    await expect.poll(() => page.getByTestId("stat-fetched").innerText()).not.toBe("—")
    const initialMetricValue = await page.getByTestId("stat-fetched").innerText()
    const [yesterdayMetrics] = await Promise.all([
      page.waitForResponse((response) => response.url().includes("/api/dashboard/daily") && response.url().includes("period=yesterday")),
      page.getByTestId("metric-period").selectOption("yesterday"),
    ])
    expect((await yesterdayMetrics.json()).series[0].date).toBe(new Date(Date.now() - 86_400_000).toISOString().slice(0, 10))
    await expect(page.getByTestId("stat-fetched")).toHaveText("0")
    const specificDate = new Date(Date.now() - 2 * 86_400_000).toISOString().slice(0, 10)
    await page.getByTestId("metric-period").selectOption("date")
    const [specificMetrics] = await Promise.all([
      page.waitForResponse((response) => response.url().includes("period=date") && response.url().includes(`date=${specificDate}`)),
      page.getByTestId("metric-specific-date").fill(specificDate),
    ])
    expect((await specificMetrics.json()).series[0].date).toBe(specificDate)
    const [allTimeMetrics] = await Promise.all([
      page.waitForResponse((response) => response.url().includes("period=all_time")),
      page.getByTestId("metric-period").selectOption("all_time"),
    ])
    expect((await allTimeMetrics.json()).series[0].date).toBe("all-time")
    await page.getByTestId("metric-period").selectOption("today")
    await expect(page.getByTestId("stat-fetched")).toHaveText(initialMetricValue)

    let actionRequests = 0
    page.on("request", (request) => {
      if (request.method() === "POST" && request.url().includes("/actions")) actionRequests += 1
    })

    const search = page.locator("#filter-search")
    await search.focus()
    await page.keyboard.press("a")
    await expect(search).toHaveValue("a")
    expect(actionRequests).toBe(0)
    await search.fill("")

    const initialCard = page.locator('[data-testid^="opportunity-card-"]').first()
    const initialTestId = await initialCard.getAttribute("data-testid")
    if (!initialTestId) throw new Error("first opportunity card has no stable test id")
    const initialId = initialTestId.replace("opportunity-card-", "")
    await page.getByTestId(`quick-apply-${initialId}`).focus()
    await page.keyboard.press("a")
    expect(actionRequests).toBe(0)

    await initialCard.click()
    const detail = page.getByRole("dialog")
    await expect(detail).toBeVisible()
    expect(await detail.evaluate((element) => element.contains(document.activeElement))).toBe(true)
    await detail.getByRole("link", { name: "View original source" }).focus()
    await page.keyboard.press("a")
    expect(actionRequests).toBe(0)
    await expectAxeClean(page, "opportunity detail drawer")
    await expectNoHorizontalOverflow(page, "detail drawer")
    await page.keyboard.press("Escape")
    await expect(detail).not.toBeVisible()
    await expect(initialCard).toBeFocused()

    const filterTrigger = page.getByTestId("open-advanced-feed-filters")
    await filterTrigger.focus()
    await page.keyboard.press("a")
    expect(actionRequests).toBe(0)
    await filterTrigger.click()
    const filterDrawer = page.getByTestId("feed-query-drawer")
    await expect(filterDrawer).toBeVisible()
    expect(await filterDrawer.evaluate((element) => element.contains(document.activeElement))).toBe(true)
    await expectAxeClean(page, "advanced filters drawer")
    await expectNoHorizontalOverflow(page, "advanced filters drawer")
    await page.keyboard.press("Escape")
    await expect(filterDrawer).not.toBeVisible()
    await expect(filterTrigger).toBeFocused()

    await page.locator("#filter-track").click()
    await page.getByTestId("filter-facet-track").getByRole("checkbox", { name: "employment" }).check()
    await page.locator("#filter-track").click()
    await page.locator("#filter-decision").click()
    await page.getByTestId("filter-facet-decision").getByRole("checkbox", { name: "qualified" }).check()
    await page.getByTestId("filter-facet-decision").getByRole("checkbox", { name: "uncertain" }).check()
    await expect(page).toHaveURL(/track=employment/)
    await expect(page).toHaveURL(/decision=qualified/)
    await expect(page).toHaveURL(/decision=uncertain/)
    await page.getByLabel("Sort").selectOption("fit_asc")
    await expect(page).toHaveURL(/track=employment/)
    await expect(page).toHaveURL(/sort_by=fit_asc/)

    await page.getByTestId("open-advanced-feed-filters").click()
    const savedViewDrawer = page.getByTestId("feed-query-drawer")
    const sourceFacet = savedViewDrawer.getByTestId("feed-facet-source_id")
    await sourceFacet.locator("summary").click()
    await sourceFacet.locator('input[type="checkbox"]').nth(0).check()
    await sourceFacet.locator('input[type="checkbox"]').nth(1).check()
    await sourceFacet.locator('input[type="checkbox"]').nth(2).check()
    await expect.poll(() => new URL(page.url()).searchParams.getAll("source_id").length).toBe(3)
    await sourceFacet.locator("summary").click()
    const workModeFacet = savedViewDrawer.getByTestId("feed-facet-work_mode")
    await workModeFacet.locator("summary").click()
    await workModeFacet.locator('input[type="checkbox"]').first().check()
    await expect.poll(() => new URL(page.url()).searchParams.getAll("work_mode").length).toBe(1)
    await workModeFacet.locator("summary").click()
    const feedbackFacet = savedViewDrawer.getByTestId("feed-facet-feedback_label")
    await feedbackFacet.locator("summary").click()
    await feedbackFacet.locator('input[type="checkbox"]').nth(0).check()
    await feedbackFacet.locator('input[type="checkbox"]').nth(1).check()
    await feedbackFacet.locator('input[type="checkbox"]').nth(2).check()
    await expect.poll(() => new URL(page.url()).searchParams.getAll("feedback_label").length).toBe(3)
    await feedbackFacet.locator("summary").click()
    const activityFacet = savedViewDrawer.getByTestId("feed-facet-activity_type")
    await activityFacet.locator("summary").click()
    await activityFacet.locator('input[type="checkbox"]').nth(0).check()
    await activityFacet.locator('input[type="checkbox"]').nth(1).check()
    await activityFacet.locator('input[type="checkbox"]').nth(2).check()
    await expect.poll(() => new URL(page.url()).searchParams.getAll("activity_type").length).toBe(3)
    await activityFacet.locator("summary").click()
    await sourceFacet.locator("summary").click()
    await sourceFacet.locator('input[type="checkbox"]').nth(1).uncheck()
    await expect.poll(() => new URL(page.url()).searchParams.getAll("source_id").length).toBe(2)
    await expect(page.getByTestId("feed-query-chips")).toContainText("Source")
    await expect(page.getByTestId("feed-query-chips")).toContainText("Feedback")
    await expect(page.getByTestId("feed-query-chips")).toContainText("Activity")
    await savedViewDrawer.getByLabel("Saved feed view name").fill(VIEW_NAME)
    await savedViewDrawer.getByRole("button", { name: "Save view" }).click()
    const savedViewButton = savedViewDrawer.getByRole("button", { name: VIEW_NAME, exact: true })
    await expect(savedViewButton).toBeVisible()
    await savedViewDrawer.getByRole("button", { name: "Clear all" }).click()
    await expect(page).not.toHaveURL(/track=/)
    await expect(page).toHaveURL(/sort_by=recommended/)
    await savedViewDrawer.getByRole("button", { name: VIEW_NAME, exact: true }).click()
    await expect(savedViewDrawer).not.toBeVisible()
    await expect(page).toHaveURL(/track=employment/)
    await expect(page).toHaveURL(/sort_by=fit_asc/)
    await expect(page.getByTestId("feed-query-chips")).toContainText("employment")
    await page.getByTestId("feed-query-chips").getByRole("button", { name: "Clear all" }).click()
    await expect(page).not.toHaveURL(/track=/)
    await page.getByTestId("toggle-hidden-opportunities").click()
    await expect(page.getByTestId("opportunity-count")).toContainText("including hidden")

    const triageButtons = page.locator('[data-testid^="quick-save-"]')
    await expect(triageButtons.first()).toBeVisible()
    const ids = await triageButtons.evaluateAll((elements) => elements.slice(0, 3).map((element) =>
      element.getAttribute("data-testid")?.replace("quick-save-", "") ?? "",
    ))
    expect(ids.length).toBeGreaterThan(0)
    expect(ids.every(Boolean)).toBe(true)
    const triageId = ids[0]

    await quickAction(page, triageId, "save")
    await expect(page.getByTestId("tracker-undo-notice")).toBeVisible()
    await page.getByTestId("workspace-tracker").click()
    const tracker = page.getByTestId("tracker-view")
    await expect(tracker).toBeVisible()
    await expectNoHorizontalOverflow(page, "tracker")
    await expectAxeClean(page, "tracker")
    await page.getByTestId("tracker-bucket-saved").click()
    await expect(page.getByTestId(`opportunity-card-${triageId}`)).toBeVisible()

    await page.getByTestId("workspace-jobs").click()
    await undoLatestAction(page, triageId)
    await quickAction(page, triageId, "reject")
    await page.getByTestId("workspace-tracker").click()
    await page.getByTestId("tracker-bucket-rejected").click()
    await expect(page.getByTestId(`opportunity-card-${triageId}`)).toBeVisible()

    await page.getByTestId("workspace-jobs").click()
    await undoLatestAction(page, triageId)
    await quickAction(page, triageId, "apply")
    await page.getByTestId("workspace-tracker").click()
    await page.getByTestId("tracker-bucket-applied").click()
    await expect(page.getByTestId(`opportunity-card-${triageId}`)).toBeVisible()
    await page.getByTestId(`opportunity-card-${triageId}`).click()

    const appliedDetail = page.getByRole("dialog")
    await expect(appliedDetail).toBeVisible()
    await appliedDetail.getByLabel("Application stage").selectOption("assessment")
    const [stageResponse] = await Promise.all([
      page.waitForResponse((response) => response.request().method() === "POST" && response.url().includes("/actions")),
      appliedDetail.getByRole("button", { name: "Update stage", exact: true }).click(),
    ])
    expect(stageResponse.status(), await stageResponse.text()).toBe(200)

    const dueDate = new Date(Date.now() + 3 * 24 * 60 * 60 * 1000).toISOString().slice(0, 10)
    const followUps = appliedDetail.getByTestId("tracker-follow-ups")
    await followUps.getByLabel("Follow-up due date").fill(dueDate)
    await followUps.getByLabel("Follow-up note").fill("W7.4 synthetic reminder")
    await followUps.getByRole("button", { name: "Add follow-up" }).click()
    const activity = appliedDetail.getByTestId("tracker-activity-timeline")
    await expect(activity.getByTestId("tracker-activity-item").first()).toContainText("Follow-up added")
    await expect(activity).toContainText("Application stage changed to Assessment")
    await expectNoHorizontalOverflow(page, "applied detail with follow-up")
    await page.keyboard.press("Escape")
    await expect(appliedDetail).not.toBeVisible()

    await page.reload()
    await expect(page.getByTestId("workspace-jobs")).toBeVisible()
    await page.getByTestId("workspace-tracker").click()
    await page.getByTestId("tracker-bucket-applied").click()
    await expect(page.getByTestId(`opportunity-card-${triageId}`)).toBeVisible()
    await page.getByTestId(`opportunity-card-${triageId}`).click()
    const refreshedAppliedDetail = page.getByRole("dialog")
    const refreshedAppliedActivity = refreshedAppliedDetail.getByTestId("tracker-activity-timeline")
    await expect(refreshedAppliedActivity).toContainText("Application stage changed to Assessment")
    await expect(refreshedAppliedActivity).toContainText("Follow-up added")
    await expect(refreshedAppliedActivity).toContainText("Saved job")
    await expect(refreshedAppliedActivity).toContainText("Rejected job")
    await expect(refreshedAppliedActivity).toContainText("Application stage changed to Assessment")
    await expect(refreshedAppliedActivity).toContainText("Follow-up added")
    await expect(refreshedAppliedActivity).toContainText("Undo applied")
    await expectAxeClean(page, "refreshed tracker detail drawer")
    await expectNoHorizontalOverflow(page, "refreshed tracker detail drawer")
    await page.keyboard.press("Escape")

    await page.getByTestId("tracker-bucket-saved").click()
    await expect(page.getByTestId(`opportunity-card-${triageId}`)).toHaveCount(0)
    await page.getByTestId("tracker-bucket-rejected").click()
    await expect(page.getByTestId(`opportunity-card-${triageId}`)).toHaveCount(0)
    await expectNoHorizontalOverflow(page, "tracker buckets after refresh")

    await page.getByTestId("workspace-jobs").click()
    const checkboxes = page.locator('input[aria-label^="Select "]')
    await expect(checkboxes.first()).toBeVisible()
    await checkboxes.nth(0).check()
    await checkboxes.nth(1).check()
    await expect(page.getByText("2 selected", { exact: true })).toBeVisible()
    await page.getByRole("button", { name: "Clear selection" }).click()
    await expect(page.getByText("0 selected", { exact: true })).toBeVisible()
    await page.getByRole("button", { name: "Select all visible" }).click()
    await expect(page.getByText(/\d+ selected/)).toBeVisible()
    await expectNoHorizontalOverflow(page, "batch selection toolbar")
  })
}

test("FR-008 batch actions reuse tracker transitions and preserve a partial failure", async ({ page }) => {
  test.setTimeout(90_000)
  await page.setViewportSize({ width: 1280, height: 844 })
  await login(page)
  const quickSaves = page.locator('[data-testid^="quick-save-"]')
  await expect(quickSaves.first()).toBeVisible()
  const firstId = (await quickSaves.first().getAttribute("data-testid"))!.replace("quick-save-", "")
  const visibleIds = await page.locator('[data-testid^="opportunity-card-"]').evaluateAll((cards) => cards.map((card) => card.getAttribute("data-testid")!.replace("opportunity-card-", "")))
  const failedId = visibleIds.find((id) => id !== firstId)!
  expect(failedId).toBeTruthy()
  for (const id of [firstId, failedId]) {
    await page.getByTestId(`opportunity-card-${id}`).locator("xpath=ancestor::li[1]").locator('input[aria-label^="Select "]').check()
  }

  await page.evaluate((id) => {
    const originalSetItem = Storage.prototype.setItem
    Storage.prototype.setItem = function (this: Storage, key: string, value: string) {
      if (key === "opportunityos.mock.tracker.default" && value.includes(`"id":"${id}","action_state":"saved"`)) {
        throw new DOMException("synthetic item persistence failure", "QuotaExceededError")
      }
      return originalSetItem.call(this, key, value)
    }
  }, failedId)
  await page.getByTestId("batch-action-toolbar").getByRole("button", { name: "Save", exact: true }).click()
  await expect(page.getByTestId("batch-action-status")).toContainText("1 succeeded; 1 failed.")
  await expect(page.getByTestId(`opportunity-card-${firstId}`)).toHaveCount(0)
  await expect(page.getByTestId(`opportunity-card-${failedId}`)).toBeVisible()
  await expect(page.getByTestId(`opportunity-card-${failedId}`).locator("xpath=ancestor::li[1]").locator('input[aria-label^="Select "]')).toBeChecked()

  await page.getByRole("button", { name: "Clear selection" }).click()
  await page.getByRole("button", { name: "Undo" }).click()
  await expect(page.getByTestId(`opportunity-card-${firstId}`)).toBeVisible()
  await page.getByTestId(`opportunity-card-${firstId}`).locator("xpath=ancestor::li[1]").locator('input[aria-label^="Select "]').check()
  await page.getByTestId("batch-action-toolbar").getByRole("button", { name: "Reject", exact: true }).click()
  await expect(page.getByTestId("batch-action-status")).toHaveText("1 jobs updated successfully.")
  await expect(page.getByTestId(`opportunity-card-${firstId}`)).toHaveCount(0)
  await page.getByRole("button", { name: "Undo" }).click()
  await expect(page.getByTestId(`opportunity-card-${firstId}`)).toBeVisible()
  await page.getByTestId(`opportunity-card-${firstId}`).locator("xpath=ancestor::li[1]").locator('input[aria-label^="Select "]').check()

  page.once("dialog", async (dialog) => {
    expect(dialog.message()).toBe("Mark 1 selected jobs as Applied?")
    await dialog.accept()
  })
  await page.getByTestId("batch-action-toolbar").getByRole("button", { name: "Mark Applied", exact: true }).click()
  await expect(page.getByTestId("batch-action-status")).toHaveText("1 jobs updated successfully.")
  await expect(page.getByTestId(`opportunity-card-${firstId}`)).toHaveCount(0)
  await page.getByTestId("workspace-tracker").click()
  await page.getByTestId("tracker-bucket-applied").click()
  await expect(page.getByTestId(`opportunity-card-${firstId}`)).toBeVisible()
})
