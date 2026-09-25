import { test, expect, type Page } from "@playwright/test"

const FOUNDER_PASSWORD = process.env.E2E_FOUNDER_PASSWORD ?? "founder-mock-pass"

async function login(page: Page) {
  await page.goto("/")
  await expect(page).toHaveURL(/\/login$/)
  await page.getByLabel("Password").fill(FOUNDER_PASSWORD)
  await page.getByRole("button", { name: "Sign in" }).click()
  await expect(page).toHaveURL(/\/$/)
  await expect(page.getByTestId("workspace-jobs")).toBeVisible()
  await expect(page.locator('[data-testid^="opportunity-card-"]').first()).toBeVisible()
}

async function actOnFirstJob(page: Page, label: string, expectedState: string) {
  const card = page.locator('[data-testid^="opportunity-card-"]').first()
  await expect(card).toBeVisible()
  const testId = await card.getAttribute("data-testid")
  if (!testId) throw new Error("first job card has no stable test id")
  const opportunityId = testId.replace("opportunity-card-", "")

  await card.click()
  const drawer = page.getByRole("dialog")
  const [response] = await Promise.all([
    page.waitForResponse((res) => res.request().method() === "POST" && res.url().includes("/actions")),
    drawer.getByRole("button", { name: label, exact: true }).click(),
  ])
  expect(response.status(), await response.text()).toBe(200)
  const body = (await response.json()) as { tracker_state: string }
  expect(body.tracker_state).toBe(expectedState)
  await expect(page.locator(`[data-testid="opportunity-card-${opportunityId}"]`)).toHaveCount(0)
  await page.keyboard.press("Escape")
  await expect(drawer).not.toBeVisible()
  return opportunityId
}

test.describe("FR-008 basic triage tracker", () => {
  test("save, explicit apply, reject, bucket placement, and source-link truthfulness", async ({ page }) => {
    await login(page)

    let actionRequests = 0
    page.on("request", (request) => {
      if (request.method() === "POST" && request.url().includes("/actions")) actionRequests += 1
    })
    await page.context().route("https://example.invalid/**", (route) => route.abort())

    const sourceCard = page.locator('[data-testid^="opportunity-card-"]').first()
    const sourceId = await sourceCard.getAttribute("data-testid")
    await sourceCard.click()
    const [sourcePage] = await Promise.all([
      page.waitForEvent("popup"),
      page.getByRole("link", { name: "View original source" }).click(),
    ])
    await sourcePage.close()
    expect(actionRequests).toBe(0)
    await expect(page.locator(`[data-testid="${sourceId}"]`)).toBeVisible()
    await page.keyboard.press("Escape")

    const savedId = await actOnFirstJob(page, "Save for later", "saved")
    await page.getByTestId("workspace-tracker").click()
    await expect(page.getByTestId("tracker-view")).toBeVisible()
    await expect(page.getByTestId(`opportunity-card-${savedId}`)).toBeVisible()
    await expect(page.getByTestId(`opportunity-card-${savedId}`).getByText("Saved", { exact: true })).toBeVisible()

    await page.reload()
    await expect(page.getByTestId("workspace-jobs")).toBeVisible()
    await page.getByTestId("workspace-tracker").click()
    await page.getByTestId("tracker-bucket-saved").click()
    await expect(page.getByTestId(`opportunity-card-${savedId}`)).toBeVisible()

    await page.getByTestId("workspace-jobs").click()
    const appliedId = await actOnFirstJob(page, "Mark applied", "applied")
    await page.getByTestId("workspace-tracker").click()
    await page.getByTestId("tracker-bucket-applied").click()
    await expect(page.getByTestId(`opportunity-card-${appliedId}`)).toBeVisible()
    await expect(page.getByTestId(`opportunity-card-${appliedId}`).getByText("Applied", { exact: true })).toBeVisible()

    await page.getByTestId("workspace-jobs").click()
    const rejectedId = await actOnFirstJob(page, "Reject", "rejected_by_founder")
    await page.getByTestId("workspace-tracker").click()
    await page.getByTestId("tracker-bucket-rejected").click()
    await expect(page.getByTestId(`opportunity-card-${rejectedId}`)).toBeVisible()
    await expect(page.getByTestId(`opportunity-card-${rejectedId}`).getByText("Rejected", { exact: true })).toBeVisible()

    await page.getByTestId("tracker-bucket-all").click()
    await expect(page.getByTestId(`opportunity-card-${savedId}`)).toBeVisible()
    await expect(page.getByTestId(`opportunity-card-${appliedId}`)).toBeVisible()
    await expect(page.getByTestId(`opportunity-card-${rejectedId}`)).toBeVisible()
  })
})
