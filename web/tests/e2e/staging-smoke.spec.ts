import { test, expect, type Page } from "@playwright/test";

const FOUNDER_EMAIL = process.env.E2E_FOUNDER_EMAIL ?? "";
const FOUNDER_PASSWORD = process.env.E2E_FOUNDER_PASSWORD ?? "";

async function login(page: Page) {
  await page.goto("/");
  await expect(page).toHaveURL(/\/login/);

  // Support both email/password Supabase Auth and legacy password forms
  const emailInput = page.getByLabel(/email/i);
  if ((await emailInput.count()) > 0 && (await emailInput.isVisible())) {
    if (!FOUNDER_EMAIL) {
      throw new Error("E2E_FOUNDER_EMAIL environment variable is required for Supabase email+password login.");
    }
    await emailInput.fill(FOUNDER_EMAIL);
  }

  const passwordInput = page.getByLabel(/password/i);
  await passwordInput.fill(FOUNDER_PASSWORD);
  await page.getByRole("button", { name: /sign in|log in/i }).click();
  await expect(page).toHaveURL(/\/$/);
  await expect(page.getByRole("heading", { name: "OpportunityOS" })).toBeVisible();
}

async function pageJson<T>(
  page: Page,
  path: string,
  init?: { method?: string; body?: unknown }
): Promise<{ status: number; ok: boolean; body: T }> {
  return page.evaluate(
    async ({ path: p, init: i }) => {
      const response = await fetch(p, {
        method: i?.method,
        credentials: "same-origin",
        headers: i?.body === undefined ? undefined : { "Content-Type": "application/json" },
        body: i?.body === undefined ? undefined : JSON.stringify(i.body),
      });
      const text = await response.text();
      return {
        status: response.status,
        ok: response.ok,
        body: text ? JSON.parse(text) : null,
      };
    },
    { path, init }
  ) as Promise<{ status: number; ok: boolean; body: T }>;
}

async function pageBinary(page: Page, path: string) {
  return page.evaluate(async (p) => {
    const response = await fetch(p, { credentials: "same-origin" });
    const bytes = new Uint8Array(await response.arrayBuffer());
    return {
      status: response.status,
      ok: response.ok,
      contentType: response.headers.get("content-type") ?? "",
      contentDisposition: response.headers.get("content-disposition") ?? "",
      prefix: Array.from(bytes.slice(0, 4)),
      size: bytes.length,
    };
  }, path);
}

test.describe("Cloudflare staging hosted smoke", () => {
  test("unauthorized access is rejected", async ({ page }) => {
    // 1. Unauthenticated navigation to root redirects to /login
    await page.goto("/");
    await expect(page).toHaveURL(/\/login/);

    // 2. Form submission with unauthorized/invalid credentials fails
    const emailInput = page.getByLabel(/email/i);
    if ((await emailInput.count()) > 0 && (await emailInput.isVisible())) {
      await emailInput.fill("unauthorized-user@example.com");
    }
    const passwordInput = page.getByLabel(/password/i);
    await passwordInput.fill("WrongPassword-12345678");
    await page.getByRole("button", { name: /sign in|log in/i }).click();

    // Verify user is not authenticated and remains on /login
    await expect(page).toHaveURL(/\/login/);

    // 3. Direct unauthenticated fetch to protected API endpoint fails with 401
    const unauthed = await pageJson<{ error?: string }>(page, "/api/opportunities");
    expect(unauthed.status).toBe(401);
  });

  test("desktop/mobile same-origin founder flow", async ({ page }) => {
    await login(page);

    // Session survival proof: reloading or navigating retains authenticated founder session
    await page.reload();
    await expect(page).toHaveURL(/\/$/);
    await expect(page.getByRole("heading", { name: "OpportunityOS" })).toBeVisible();

    // Persisted feed must already exist; this smoke does not poll in order to
    // make the page readable.
    const firstPage = await pageJson<{
      page: number;
      page_size: number;
      total: number;
      items: Array<{
        id: string;
        title: string;
        organization: string;
        source_url: string;
      }>;
    }>(page, "/api/opportunities?page=1&page_size=1");
    expect(firstPage.ok, `feed returned ${firstPage.status}`).toBe(true);
    expect(firstPage.body.total, "staging needs at least two rows to prove pagination").toBeGreaterThan(1);
    expect(firstPage.body.items).toHaveLength(1);
    const first = firstPage.body.items[0];

    // Pagination proof: page 2 resolves through the same Cloudflare /api proxy
    // and identifies a different canonical item.
    const secondPage = await pageJson<{
      page: number;
      page_size: number;
      total: number;
      items: Array<{ id: string }>;
    }>(page, "/api/opportunities?page=2&page_size=1");
    expect(secondPage.ok, `page 2 returned ${secondPage.status}`).toBe(true);
    expect(secondPage.body.items).toHaveLength(1);
    expect(secondPage.body.items[0].id).not.toBe(first.id);

    // Search proof uses a live title token from the feed rather than a
    // hard-coded staging fixture.
    const searchTerm =
      first.title.split(/\s+/).find((part) => part.replace(/[^\p{L}\p{N}+#]/gu, "").length >= 3) ??
      first.organization;
    const search = await pageJson<{ total: number; items: Array<{ id: string }> }>(
      page,
      `/api/opportunities?q=${encodeURIComponent(searchTerm)}&page_size=50`
    );
    expect(search.ok, `search returned ${search.status}`).toBe(true);
    expect(search.body.total).toBeGreaterThan(0);
    expect(search.body.items.some((item) => item.id === first.id)).toBe(true);

    const facets = await pageJson<{ facets: unknown[] }>(page, "/api/facets");
    expect(facets.ok, `facets returned ${facets.status}`).toBe(true);
    expect(facets.body.facets.length).toBeGreaterThan(0);

    const detail = await pageJson<{ id: string; source_url: string }>(
      page,
      `/api/opportunities/${encodeURIComponent(first.id)}`
    );
    expect(detail.ok, `detail returned ${detail.status}`).toBe(true);
    expect(detail.body.id).toBe(first.id);
    expect(detail.body.source_url).toBeTruthy();

    // UI detail/source-link proof.
    const firstCard = page.locator('[data-testid^="opportunity-card-"]').first();
    await expect(firstCard).toBeVisible();
    await firstCard.click();
    const drawer = page.getByRole("dialog");
    await expect(drawer).toBeVisible();
    const sourceLink = drawer.getByRole("link", { name: /View original source/i });
    await expect(sourceLink).toBeVisible();
    expect(await sourceLink.getAttribute("href")).toBeTruthy();

    const pdfPreview = drawer.getByTestId("artifact-pdf-preview");
    await expect(pdfPreview).toBeVisible();

    // ADR-0024 Fixed CV preview/download retrieval through same-origin proxy.
    // Fixed CV portfolio serves immutable approved PDFs as cv-final.pdf.
    const cvPreview = await pageBinary(
      page,
      `/api/opportunities/${encodeURIComponent(first.id)}/artifacts/cv-final.pdf`
    );
    expect(cvPreview.ok, `CV preview returned ${cvPreview.status}`).toBe(true);
    expect(cvPreview.contentType).toContain("application/pdf");
    expect(cvPreview.contentDisposition.toLowerCase()).toContain("inline");
    expect(cvPreview.prefix).toEqual([0x25, 0x50, 0x44, 0x46]); // %PDF
    expect(cvPreview.size).toBeGreaterThan(0);

    const cvDownload = await pageBinary(
      page,
      `/api/opportunities/${encodeURIComponent(first.id)}/artifacts/cv-final.pdf?download=true`
    );
    expect(cvDownload.ok, `CV download returned ${cvDownload.status}`).toBe(true);
    expect(cvDownload.contentType).toContain("application/pdf");
    expect(cvDownload.contentDisposition.toLowerCase()).toContain("attachment");
    expect(cvDownload.prefix).toEqual([0x25, 0x50, 0x44, 0x46]); // %PDF
    expect(cvDownload.size).toBeGreaterThan(0);

    // Generated artifact access where available (e.g. cover letter)
    const coverLetter = await pageBinary(
      page,
      `/api/opportunities/${encodeURIComponent(first.id)}/artifacts/cover-letter.pdf?template=classic`
    );
    if (coverLetter.ok) {
      expect(coverLetter.contentType).toContain("application/pdf");
      expect(coverLetter.prefix).toEqual([0x25, 0x50, 0x44, 0x46]);
    } else {
      // Cover letter generation may be ungenerated for this item; verify standard API response
      expect([404, 409, 412]).toContain(coverLetter.status);
    }

    await page.keyboard.press("Escape");
    await expect(drawer).not.toBeVisible();

    // Poll Now must respond asynchronously and must not destroy the already
    // visible persisted feed.
    const poll = await pageJson<{ enqueued: unknown[]; skipped: unknown[] }>(
      page,
      "/api/worker/poll-now",
      { method: "POST" }
    );
    expect(poll.ok, `Poll Now returned ${poll.status}`).toBe(true);
    expect(Array.isArray(poll.body.enqueued)).toBe(true);
    expect(Array.isArray(poll.body.skipped)).toBe(true);
    await expect(firstCard).toBeVisible();

    // Logout from inside the browser context so the session cookie exercised
    // above is the exact one invalidated here.
    const logout = await pageJson<{ authenticated: boolean }>(
      page,
      "/api/auth/logout",
      { method: "POST" }
    );
    expect(logout.ok, `logout returned ${logout.status}`).toBe(true);
    await page.goto("/");
    await expect(page).toHaveURL(/\/login$/);

    // Session invalidation proof: direct API calls now fail closed with 401 Unauthorized
    const postLogout = await pageJson<{ error?: string }>(page, "/api/opportunities");
    expect(postLogout.status).toBe(401);
  });
});
