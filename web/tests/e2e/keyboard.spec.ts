import { test, expect, type Page } from "@playwright/test"

/**
 * C3 required behaviour #4 — j/k move the keyboard cursor (and real DOM
 * focus with it), o opens the drawer for the focused card, a marks it
 * applied, x dismisses it. Every assertion here is the *state change* the
 * shortcut causes (focus moved to a different card's real DOM node, the
 * drawer opened with that card's own title, the action badge appeared, a
 * live network request fired) — never just "nothing threw". Shortcuts are
 * also proven inert while a text input has focus.
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

function focusedCard(page: Page) {
  return page.locator('[data-keyboard-focused="true"]')
}

test.describe("C3 keyboard flow (j/k/o/a/x)", () => {
  test("j/k move the cursor and move real DOM focus with it", async ({ page }) => {
    await login(page)
    await expect(
      page.locator('[data-testid^="opportunity-card-"]').first()
    ).toBeVisible()

    await expect(focusedCard(page)).toHaveCount(1)
    const firstId = await focusedCard(page).getAttribute("data-testid")

    await page.keyboard.press("j")
    await expect(focusedCard(page)).toHaveCount(1)
    const secondId = await focusedCard(page).getAttribute("data-testid")
    expect(secondId).not.toBe(firstId)
    // Real DOM focus, not a CSS-only highlight the browser's own focus
    // never actually reaches.
    const activeTestId = await page.evaluate(() =>
      document.activeElement?.getAttribute("data-testid")
    )
    expect(activeTestId).toBe(secondId)

    await page.keyboard.press("k")
    await expect(focusedCard(page)).toHaveCount(1)
    const backId = await focusedCard(page).getAttribute("data-testid")
    expect(backId).toBe(firstId)
    const activeAfterK = await page.evaluate(() =>
      document.activeElement?.getAttribute("data-testid")
    )
    expect(activeAfterK).toBe(firstId)
  })

  test("o opens the drawer for the focused card", async ({ page }) => {
    await login(page)
    await expect(
      page.locator('[data-testid^="opportunity-card-"]').first()
    ).toBeVisible()
    const card = focusedCard(page)
    const title = (await card.locator("h2").innerText()).trim()

    await page.keyboard.press("o")
    const drawer = page.getByRole("dialog")
    await expect(drawer).toBeVisible()
    await expect(drawer.getByRole("heading", { name: title })).toBeVisible()
    await expect(drawer.getByTestId("detail-fit-score")).toContainText(/Fit\s+\d+/)

    await page.keyboard.press("Escape")
    await expect(drawer).not.toBeVisible()
  })

  test("a marks the focused card applied; moving on, x dismisses the next one", async ({
    page,
  }) => {
    await login(page)
    await expect(
      page.locator('[data-testid^="opportunity-card-"]').first()
    ).toBeVisible()

    const beforeId = await focusedCard(page).getAttribute("data-testid")
    const [applyResponse] = await Promise.all([
      page.waitForResponse(
        (res) => res.request().method() === "POST" && res.url().includes("/actions")
      ),
      page.keyboard.press("a"),
    ])
    expect(applyResponse.status(), await applyResponse.text()).toBe(200)
    const applyBody = (await applyResponse.json()) as { action_state: string }
    expect(applyBody.action_state).toBe("submitted")
    const appliedCard = page.locator(`[data-testid="${beforeId}"]`)
    await expect(appliedCard.getByText("Applied", { exact: true })).toBeVisible()

    await page.keyboard.press("j")
    const nextId = await focusedCard(page).getAttribute("data-testid")
    expect(nextId).not.toBe(beforeId)

    const [dismissResponse] = await Promise.all([
      page.waitForResponse(
        (res) => res.request().method() === "POST" && res.url().includes("/actions")
      ),
      page.keyboard.press("x"),
    ])
    expect(dismissResponse.status(), await dismissResponse.text()).toBe(200)
    const dismissBody = (await dismissResponse.json()) as { action_state: string }
    expect(dismissBody.action_state).toBe("dismissed")
    const dismissedCard = page.locator(`[data-testid="${nextId}"]`)
    await expect(dismissedCard.getByText("Dismissed", { exact: true })).toBeVisible()
  })

  test("shortcuts do not fire while a text input has focus", async ({ page }) => {
    await login(page)
    await expect(
      page.locator('[data-testid^="opportunity-card-"]').first()
    ).toBeVisible()

    let actionRequests = 0
    page.on("request", (req) => {
      if (req.method() === "POST" && req.url().includes("/actions")) {
        actionRequests += 1
      }
    })

    const search = page.locator("#filter-search")
    await search.click()
    const activeTag = await page.evaluate(() => document.activeElement?.tagName)
    expect(activeTag).toBe("INPUT")

    // "a" typed into the search box must only ever change the search text
    // (which re-queries the feed) — never trigger the "mark applied"
    // shortcut. Waiting for that re-query's own response is what makes
    // this deterministic instead of a fixed sleep.
    const [listResponse] = await Promise.all([
      page.waitForResponse(
        (res) =>
          res.request().method() === "GET" && res.url().includes("/api/opportunities?")
      ),
      search.pressSequentially("a"),
    ])
    expect(listResponse.ok(), await listResponse.text()).toBe(true)
    await expect(search).toHaveValue("a")
    expect(actionRequests).toBe(0)
  })
})
