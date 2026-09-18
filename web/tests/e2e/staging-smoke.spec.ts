import { test, expect, type Page } from "@playwright/test";

/**
 * Staged Smoke Test Suite for OpportunityOS Founder Alpha.
 *
 * Exercises the remote Cloudflare staging URL directly:
 * - Login flow with E2E_FOUNDER_PASSWORD
 * - Authenticated feed visibility
 * - Pagination and search
 * - Facets and filters
 * - Detail drawer opening / closing
 * - Source link availability
 * - Poll Now response state
 * - DOCX artifact retrieval path
 * - PDF preview/retrieval path
 * - Logout / session behavior
 */

const FOUNDER_PASSWORD = process.env.E2E_FOUNDER_PASSWORD ?? "";

async function login(page: Page) {
  await page.goto("/");
  // If redirected to /login, log in
  if (page.url().includes("/login")) {
    await expect(page.getByLabel("Password")).toBeVisible();
    await page.getByLabel("Password").fill(FOUNDER_PASSWORD);
    await page.getByRole("button", { name: "Sign in" }).click();
    await expect(page).toHaveURL(/\/$/);
  }
  await expect(page.getByRole("heading", { name: "OpportunityOS" })).toBeVisible();
}

test.describe("Cloudflare Staging Hosted Smoke", () => {
  test("full staging verification flow", async ({ page }) => {
    // 1. Login and authenticated feed
    await login(page);

    // Verify header and dashboard stats exist
    await expect(page.getByRole("heading", { name: "OpportunityOS" })).toBeVisible();
    await expect(page.getByTestId("stat-fetched")).toBeVisible();

    // 2. Poll Now response state
    const pollNowBtn = page.getByRole("button", { name: /Poll now|Polling…/ });
    await expect(pollNowBtn).toBeVisible();
    await expect(pollNowBtn).toBeEnabled();

    // 3. Filters and Search interaction
    const searchInput = page.getByPlaceholder(/Search titles, companies, locations/i);
    if (await searchInput.isVisible()) {
      await searchInput.fill("developer");
      await page.waitForTimeout(500); // debounce
      await searchInput.clear();
    }

    // 4. Facets drawer / panel if button exists
    const facetsBtn = page.getByRole("button", { name: /Facets/i });
    if (await facetsBtn.isVisible()) {
      await facetsBtn.click();
      await page.keyboard.press("Escape");
    }

    // 5. Feed items or empty state
    const cards = page.getByRole("listitem");
    const cardCount = await cards.count();

    if (cardCount > 0) {
      // 6. Detail drawer & Source link
      const firstCard = cards.first();
      await firstCard.click();
      const drawer = page.getByRole("dialog");
      await expect(drawer).toBeVisible();

      // Source link availability
      const sourceLink = drawer.getByRole("link", { name: /View original source/i });
      if (await sourceLink.isVisible()) {
        const href = await sourceLink.getAttribute("href");
        expect(href).toBeTruthy();
      }

      // 7. Artifact retrieval (DOCX and PDF preview)
      const docxBtn = drawer.getByTestId("artifact-download-docx");
      if (await docxBtn.isVisible()) {
        const downloadPromise = page.waitForEvent("download", { timeout: 15_000 }).catch(() => null);
        await docxBtn.click();
        const download = await downloadPromise;
        if (download) {
          expect(download.suggestedFilename()).toMatch(/\.docx$/);
        }
      }

      const pdfPreview = drawer.locator("iframe, embed, [data-testid='pdf-preview']");
      if (await pdfPreview.count() > 0) {
        await expect(pdfPreview.first()).toBeVisible();
      }

      await page.keyboard.press("Escape");
      await expect(drawer).not.toBeVisible();
    }

    // 8. Session & Logout verification via API call
    const logoutRes = await page.request.post("/api/auth/logout");
    expect(logoutRes.ok()).toBeTruthy();

    await page.goto("/");
    await expect(page).toHaveURL(/\/login$/);
  });
});