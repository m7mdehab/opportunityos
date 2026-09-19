import { test, expect, type Page } from "@playwright/test";

const FOUNDER_EMAIL = process.env.E2E_FOUNDER_EMAIL ?? "";
const FOUNDER_PASSWORD = process.env.E2E_FOUNDER_PASSWORD ?? "";

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
    // 1. Unauthenticated root access redirects to login gate
    await page.goto("/");
    await expect(page).toHaveURL(/\/login$/);

    // 1b. Unauthenticated API request returns 401
    const unauthApi = await pageJson(page, "/api/opportunities");
    expect(unauthApi.status, "Unauthenticated API request must return 401").toBe(401);

    // 2. Invalid login is rejected
    const emailField = page.getByLabel(/Email/i);
    const hasEmail = await emailField.isVisible().catch(() => false);
    if (hasEmail) {
      await emailField.fill("invalid-founder@example.com");
    }
    const passwordField = page.getByLabel(/Password/i);
    await passwordField.fill("completely-wrong-password-9999");
    await page.getByRole("button", { name: /Sign in/i }).click();

    await expect(page.locator('[role="alert"], #login-error, .text-destructive')).toBeVisible();
    await expect(page).toHaveURL(/\/login$/);

    // 3. Founder email/password login succeeds
    if (hasEmail) {
      await emailField.fill(FOUNDER_EMAIL);
    }
    await passwordField.fill(FOUNDER_PASSWORD);
    await page.getByRole("button", { name: /Sign in/i }).click();

    await expect(page).toHaveURL(/\/$/);
    await expect(page.getByRole("heading", { name: "OpportunityOS" })).toBeVisible();

    // 4. Session survives page reload
    await page.reload();
    await expect(page).toHaveURL(/\/$/);
    await expect(page.getByRole("heading", { name: "OpportunityOS" })).toBeVisible();

    // 5. Feed endpoint returns exact contract
    const firstPage = await pageJson<{
      page: number;
      page_size: number;
      total: number;
      hidden_count: number;
      items: Array<{
        id: string;
        title: string;
        organization: string;
        source_id: string;
        source_url: string;
        track: string;
        decision: string | null;
        fit_score: number | null;
        top_reasons: string[];
        work_mode: string;
        remote_scope: string;
        employment_type: string;
        seniority_level: string;
      }>;
    }>(page, "/api/opportunities?page=1&page_size=1");

    expect(firstPage.ok, `feed returned ${firstPage.status}`).toBe(true);
    expect(typeof firstPage.body.page).toBe("number");
    expect(typeof firstPage.body.page_size).toBe("number");
    expect(typeof firstPage.body.total).toBe("number");
    expect(Array.isArray(firstPage.body.items)).toBe(true);

    // Bootstrap prerequisite: staging corpus must have at least two feed rows
    if (firstPage.body.total < 2) {
      throw new Error(
        `Staging corpus has fewer than two feed rows (total=${firstPage.body.total}); run protected bootstrap workflow before running smoke.`
      );
    }

    expect(firstPage.body.items).toHaveLength(1);
    const first = firstPage.body.items[0];
    expect(typeof first.id).toBe("string");
    expect(first.title.length).toBeGreaterThan(0);
    expect(first.organization.length).toBeGreaterThan(0);
    expect(first.source_url.length).toBeGreaterThan(0);

    // 6. Pagination proof: page 2 returns a different item
    const secondPage = await pageJson<{
      page: number;
      page_size: number;
      total: number;
      items: Array<{ id: string }>;
    }>(page, "/api/opportunities?page=2&page_size=1");
    expect(secondPage.ok, `page 2 returned ${secondPage.status}`).toBe(true);
    expect(secondPage.body.items).toHaveLength(1);
    expect(secondPage.body.items[0].id).not.toBe(first.id);

    // 7. Live search returns target row
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

    // 8. Facets response has the real contract shape, not arrays of bare strings
    const facets = await pageJson<{
      facets: Array<{
        facet_id: string;
        value_type?: string;
        values: Array<{ value: string; count: number }>;
      }>;
    }>(page, "/api/facets");
    expect(facets.ok, `facets returned ${facets.status}`).toBe(true);
    expect(Array.isArray(facets.body.facets)).toBe(true);
    expect(facets.body.facets.length).toBeGreaterThan(0);
    for (const facet of facets.body.facets) {
      expect(typeof facet.facet_id).toBe("string");
      expect(Array.isArray(facet.values)).toBe(true);
      for (const val of facet.values) {
        expect(typeof val.value).toBe("string");
        expect(typeof val.count).toBe("number");
      }
    }

    // 9. Opportunity detail includes nested qualification/scoring arrays safe for DetailDrawer
    const detail = await pageJson<{
      id: string;
      title: string;
      source_url: string;
      qualification: {
        decision: string | null;
        constraints: Array<{ constraint_name: string; outcome: string }>;
      };
      scoring: {
        fit_score: number | null;
        dimension_scores: Array<{ dimension: string; score: number }>;
        strengths: string[];
        gaps: string[];
        unknowns: string[];
      };
    }>(page, `/api/opportunities/${encodeURIComponent(first.id)}`);

    expect(detail.ok, `detail returned ${detail.status}`).toBe(true);
    expect(detail.body.id).toBe(first.id);
    expect(detail.body.source_url).toBeTruthy();
    expect(detail.body.qualification).toBeDefined();
    expect(Array.isArray(detail.body.qualification.constraints)).toBe(true);
    expect(detail.body.scoring).toBeDefined();
    expect(Array.isArray(detail.body.scoring.dimension_scores)).toBe(true);
    expect(Array.isArray(detail.body.scoring.strengths)).toBe(true);
    expect(Array.isArray(detail.body.scoring.gaps)).toBe(true);
    expect(Array.isArray(detail.body.scoring.unknowns)).toBe(true);

    // 10. UI detail drawer, source link, and PDF preview
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

    // 11. Fixed CV preview and download from founder-cv-portfolio (ADR-0024)
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
    expect(cvDownload.contentDisposition.toLowerCase()).toContain("filename=");
    expect(cvDownload.prefix).toEqual([0x25, 0x50, 0x44, 0x46]); // %PDF
    expect(cvDownload.size).toBeGreaterThan(0);

    // 12. Generated artifact is either correctly returned (200) or legitimate 404/409/412
    const coverLetter = await pageBinary(
      page,
      `/api/opportunities/${encodeURIComponent(first.id)}/artifacts/cover-letter.docx`
    );
    if (coverLetter.ok) {
      expect(coverLetter.contentType).toContain(
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
      );
      expect(coverLetter.prefix.slice(0, 2)).toEqual([0x50, 0x4b]); // PK (zip)
      expect(coverLetter.size).toBeGreaterThan(0);
    } else {
      expect(
        [404, 409, 412],
        `Generated artifact returned unexpected status ${coverLetter.status}`
      ).toContain(coverLetter.status);
    }

    await page.keyboard.press("Escape");
    await expect(drawer).not.toBeVisible();

    // 13. Poll Now response contains arrays of {source_id,job_id} and {source_id,reason}
    // and existing feed remains visible
    const poll = await pageJson<{
      enqueued: Array<{ source_id: string; job_id: string }>;
      skipped: Array<{ source_id: string; reason: string }>;
    }>(page, "/api/worker/poll-now", { method: "POST" });
    expect(poll.ok, `Poll Now returned ${poll.status}`).toBe(true);
    expect(Array.isArray(poll.body.enqueued)).toBe(true);
    expect(Array.isArray(poll.body.skipped)).toBe(true);
    for (const item of poll.body.enqueued) {
      expect(typeof item.source_id).toBe("string");
      expect(typeof item.job_id).toBe("string");
    }
    for (const item of poll.body.skipped) {
      expect(typeof item.source_id).toBe("string");
      expect(typeof item.reason).toBe("string");
    }
    await expect(firstCard).toBeVisible();

    // 14. Logout invalidates hosted session and subsequent protected request is 401
    const logout = await pageJson<{ authenticated: boolean }>(
      page,
      "/api/auth/logout",
      { method: "POST" }
    );
    expect(logout.ok, `logout returned ${logout.status}`).toBe(true);

    await page.goto("/");
    await expect(page).toHaveURL(/\/login$/);

    const postLogoutApi = await pageJson(page, "/api/opportunities");
    expect(
      postLogoutApi.status,
      "Protected API request after logout must return 401"
    ).toBe(401);
  });
});
