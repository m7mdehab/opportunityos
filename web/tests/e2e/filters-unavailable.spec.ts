import { test, expect, type Page } from "@playwright/test"

/**
 * D3 — `unavailable_reason` (council finding, FR-005 D3 repair). Kept in
 * its own file, deliberately excluded from `playwright.real.config.ts`'s
 * `testMatch`: the real API has not shipped `unavailable_reason` on
 * `GET /api/filters` yet (it currently omits the key), so `stale_postings`
 * renders as an ordinary available filter against the real stack today —
 * there is nothing "Unavailable" for this spec to find there, and running
 * it there would either be a vacuous no-op or a false failure, not a
 * meaningful real-stack proof. `web/components/feed/filters-drawer.tsx`'s
 * `normalizeUnavailableReason` is what keeps that same absence from
 * breaking anything in `filters.spec.ts`/`smoke.spec.ts`, which do run
 * against the real stack. Once the API half ships the field, this file
 * should move into `playwright.real.config.ts`'s `testMatch` alongside it.
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

test.describe("D3 founder-controlled filters — unavailable_reason", () => {
  test("an unavailable filter renders as inert, shows its reason, and stays switchable", async ({
    page,
  }) => {
    // Council finding, FR-005 D3 repair: `stale_postings` can never match
    // anything (nothing outside tests writes `is_stale=True`), but before
    // this repair it read as an ordinary enabled label_only filter with
    // `affected_count: 0` — indistinguishable from "no stale postings
    // right now". This asserts that ambiguity is gone.
    await login(page)
    await expect(page.getByTestId("opportunity-card-opp-001")).toBeVisible()

    await page.getByRole("button", { name: "Filters" }).click()
    const drawer = page.getByRole("dialog")
    await expect(drawer).toBeVisible()

    // Unavailable filters get their own section, surfaced first.
    await expect(
      drawer.getByRole("heading", { name: /Unavailable/ })
    ).toBeVisible()

    const row = drawer.getByTestId("filter-row-stale_postings")
    await expect(row).toBeVisible()

    // Distinct inert state: icon + colour + text together, never a bare
    // suppressed "0" and never colour alone.
    const notice = row.locator('[data-filter-effect="unavailable"]')
    await expect(notice).toBeVisible()
    await expect(notice).toContainText("Unavailable")
    await expect(notice).toContainText(
      "No source-polling code path outside tests"
    )

    // The affected-count chip must not render at all for this row — a
    // suppressed "0" is exactly the misleading signal this repair removes.
    await expect(row.locator("[data-affected-count]")).toHaveCount(0)

    // Still switchable: `enabled`/`mode` remain a real, durable founder
    // preference here (see the reasoning documented in
    // filters-drawer.tsx), so the control is not disabled.
    const toggle = row.getByRole("switch")
    await expect(toggle).toBeEnabled()
    const wasChecked = (await toggle.getAttribute("aria-checked")) === "true"
    await toggle.click()
    await expect(toggle).toHaveAttribute(
      "aria-checked",
      wasChecked ? "false" : "true"
    )

    // Reset, so this does not leak into a later test/spec file sharing the
    // same mock singleton.
    await page.request
      .put("/api/filters/stale_postings", {
        data: { enabled: true, mode: "label_only" },
      })
      .catch(() => undefined)
  })
})
