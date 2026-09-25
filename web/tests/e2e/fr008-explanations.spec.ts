import { test, expect, type Page } from "@playwright/test"

const FOUNDER_PASSWORD = process.env.E2E_FOUNDER_PASSWORD ?? "founder-mock-pass"

async function login(page: Page, scenario?: "no-truth-pack") {
  if (scenario) {
    await page.addInitScript((selectedScenario) => {
      const originalPushState = window.history.pushState.bind(window.history)
      window.history.pushState = (data, unused, url) => {
        if (url) {
          const target = new URL(String(url), window.location.href)
          target.searchParams.set("mock_scenario", selectedScenario)
          return originalPushState(data, unused, target.pathname + target.search + target.hash)
        }
        return originalPushState(data, unused, url)
      }
    }, scenario)
  }
  await page.goto(scenario ? "/login?mock_scenario=" + scenario : "/")
  await page.getByLabel("Password").fill(FOUNDER_PASSWORD)
  await page.getByRole("button", { name: "Sign in" }).click()
  await expect(page).toHaveURL(scenario ? new RegExp("mock_scenario=" + scenario) : /\/(?:\?.*)?$/)
  await expect(page.getByTestId("workspace-jobs")).toBeVisible()
  await expect(page.locator('[data-testid^="opportunity-card-"]').first()).toBeVisible()
}

async function openFirstDetail(page: Page) {
  await page.locator('[data-testid^="opportunity-card-"]').first().click()
  return page.getByRole("dialog")
}

test.describe("FR-008 job detail explanations", () => {
  test("separates eligibility, fit, preference, and confidence with evidence", async ({ page }) => {
    await login(page)
    const drawer = await openFirstDetail(page)
    await expect(drawer.getByTestId("match-overview")).toBeVisible()
    await expect(drawer.getByTestId("eligibility-explanation")).toContainText(/Qualified|Uncertain|Ineligible/)
    await expect(drawer.getByTestId("eligibility-explanation")).toContainText("No mandatory contradiction was found")
    await expect(drawer.getByTestId("capability-fit-summary")).toContainText(/\d+ \/ 100/)
    await expect(drawer.getByTestId("preference-score-summary")).toContainText("76 / 100")
    await expect(drawer.getByTestId("preference-score-summary")).toContainText("does not change eligibility or Capability Fit")
    await expect(drawer.getByTestId("confidence-score-summary")).toContainText("82 / 100")
    await expect(drawer.getByTestId("confidence-factors").getByText("Description completeness")).toBeVisible()
    await expect(drawer.getByRole("heading", { name: "Capability Fit dimensions" })).toBeVisible()
    await expect(drawer.getByText("Displayed weights are provisional", { exact: false })).toBeVisible()
  })

  test("shows neutral unavailable states when no Founder truth pack has been evaluated", async ({ page }) => {
    await login(page, "no-truth-pack")
    const drawer = await openFirstDetail(page)
    await expect(drawer.getByTestId("eligibility-explanation")).toContainText("No eligibility assessment is available")
    await expect(drawer.getByTestId("capability-fit-summary")).toContainText("Not available")
    await expect(drawer.getByTestId("preference-score-summary")).toContainText("Not available")
    await expect(drawer.getByTestId("confidence-score-summary")).toContainText("Not available")
    await expect(drawer.getByTestId("confidence-factors-unavailable")).toBeVisible()
    await expect(drawer.getByText("No scoring available yet.")).toBeVisible()
  })

  test("treats absent score fields in a legacy detail response as unavailable", async ({ page }) => {
    await page.addInitScript(() => {
      const originalFetch = window.fetch.bind(window)
      window.fetch = async (input: RequestInfo | URL, init?: RequestInit) => {
        const response = await originalFetch(input, init)
        const requestUrl = typeof input === "string" ? input : input instanceof Request ? input.url : input.toString()
        const url = new URL(requestUrl, window.location.origin)
        const method = init?.method ?? (input instanceof Request ? input.method : "GET")
        if (method.toUpperCase() !== "GET" || !/^\/api\/opportunities\/[^/]+$/.test(url.pathname)) return response
        const body = await response.clone().json() as { scoring?: Record<string, unknown> }
        if (body.scoring) {
          delete body.scoring.preference_score
          delete body.scoring.confidence_score
          delete body.scoring.confidence_factors
        }
        const headers = new Headers(response.headers)
        headers.delete("content-length")
        return new Response(JSON.stringify(body), { status: response.status, statusText: response.statusText, headers })
      }
    })
    await login(page)
    const drawer = await openFirstDetail(page)
    await expect(drawer.getByTestId("capability-fit-summary")).toContainText(/\d+ \/ 100/)
    await expect(drawer.getByTestId("preference-score-summary")).toContainText("Not available")
    await expect(drawer.getByTestId("confidence-score-summary")).toContainText("Not available")
    await expect(drawer.getByTestId("confidence-factors-unavailable")).toBeVisible()
  })
})
