import { test, expect, type Page } from "@playwright/test";

const FOUNDER_PASSWORD = process.env.E2E_FOUNDER_PASSWORD ?? "";

async function login(page: Page) {
  await page.goto("/");
  await expect(page).toHaveURL(/\/login$/);
  await page.getByLabel("Password").fill(FOUNDER_PASSWORD);
  await page.getByRole("button", { name: "Sign in" }).click();
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
  test("desktop/mobile same-origin founder flow", async ({ page }) => {
    await login(page);

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

    // DOCX/PDF retrieval through the browser's same-origin proxy. These
    // assertions fail rather than silently passing when staging lacks the
    // Truth Pack or artifact backend required by A-16.
    const docx = await pageBinary(
      page,
      `/api/opportunities/${encodeURIComponent(first.id)}/artifacts/cv.docx?template=classic`
    );
    expect(docx.ok, `DOCX returned ${docx.status}`).toBe(true);
    expect(docx.contentType).toContain(
      "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    );
    expect(docx.contentDisposition.toLowerCase()).toContain("attachment");
    expect(docx.prefix.slice(0, 2)).toEqual([0x50, 0x4b]);
    expect(docx.size).toBeGreaterThan(0);

    const pdf = await pageBinary(
      page,
      `/api/opportunities/${encodeURIComponent(first.id)}/artifacts/cv.pdf?template=classic`
    );
    expect(pdf.ok, `PDF returned ${pdf.status}`).toBe(true);
    expect(pdf.contentType).toContain("application/pdf");
    expect(pdf.contentDisposition.toLowerCase()).toContain("inline");
    expect(pdf.prefix).toEqual([0x25, 0x50, 0x44, 0x46]);
    expect(pdf.size).toBeGreaterThan(0);

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
  });
});
