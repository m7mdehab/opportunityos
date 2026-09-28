import { test, expect, type Page } from "@playwright/test";

const FOUNDER_EMAIL = process.env.E2E_FOUNDER_EMAIL ?? "";
const FOUNDER_PASSWORD = process.env.E2E_FOUNDER_PASSWORD ?? "";

async function pageJson<T>(
  page: Page,
  path: string,
  init?: { method?: string; body?: unknown; cache?: RequestCache }
): Promise<{ status: number; ok: boolean; body: T; ttfb_ms: number; elapsed_ms: number; server_timing: string }> {
  return page.evaluate(
    async ({ path: p, init: i }) => {
      const method = (i?.method ?? "GET").toUpperCase();
      const headers = new Headers();
      if (i?.body !== undefined) headers.set("Content-Type", "application/json");
      if (method !== "GET" && method !== "HEAD" && method !== "OPTIONS") {
        headers.set("X-OpportunityOS-CSRF", "1");
      }
      const started = performance.now();
      const response = await fetch(p, {
        method,
        cache: i?.cache,
        credentials: "same-origin",
        headers,
        body: i?.body === undefined ? undefined : JSON.stringify(i.body),
        signal: AbortSignal.timeout(25_000),
      });
      const ttfb_ms = performance.now() - started;
      const server_timing = response.headers.get("server-timing") ?? "unavailable";
      const text = await response.text();
      const elapsed_ms = performance.now() - started;
      return {
        status: response.status,
        ok: response.ok,
        body: text ? JSON.parse(text) : null,
        ttfb_ms,
        elapsed_ms,
        server_timing,
      };
    },
    { path, init }
  ) as Promise<{ status: number; ok: boolean; body: T; ttfb_ms: number; elapsed_ms: number; server_timing: string }>;
}

function safeApiErrorSummary(body: unknown): string {
  if (!body || typeof body !== "object" || Array.isArray(body)) return `body_type=${typeof body}`;
  const value = body as Record<string, unknown>;
  return JSON.stringify({
    code: typeof value.code === "string" ? value.code.slice(0, 64) : undefined,
    message: typeof value.message === "string" ? value.message.slice(0, 200) : undefined,
    details: typeof value.details === "string" ? value.details.slice(0, 200) : undefined,
    hint: typeof value.hint === "string" ? value.hint.slice(0, 200) : undefined,
    detail: typeof value.detail === "string" ? value.detail.slice(0, 200) : undefined,
  });
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
    const firstAuthenticatedFeed: Array<{ elapsed_ms: number; server_timing: string }> = [];
    page.on("requestfinished", (request) => {
      if (request.method() !== "GET" || !new URL(request.url()).pathname.endsWith("/api/opportunities")) return;
      void (async () => {
        const response = await request.response();
        if (!response?.ok() || firstAuthenticatedFeed.length) return;
        const timing = request.timing();
        firstAuthenticatedFeed.push({
          elapsed_ms: timing.responseEnd,
          server_timing: response.headers()["server-timing"] ?? "unavailable",
        });
      })();
    });
    // This hosted proof deliberately performs login, reversible mutations,
    // reloads, and 20 sequential live feed SLO samples. The default 30s
    // Playwright budget is therefore smaller than the work the test itself
    // requires even when every individual feed request satisfies the 1.5s SLO.
    // Hosted evidence continues through artifacts, reversible Founder action,
    // source health, logout, and mobile checks after the 20-sample SLO block.
    test.setTimeout(120_000);
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

    await expect(page).toHaveURL(/\/(?:\?.*)?$/);
    await expect(page.getByRole("heading", { name: "OpportunityOS" })).toBeVisible();

    // 4. Session survives page reload
    await page.reload();
    await expect(page).toHaveURL(/\/(?:\?.*)?$/);
    await expect(page.getByRole("heading", { name: "OpportunityOS" })).toBeVisible();

    // 4b. FR-008 live review controls are present and genuinely multi-select.
    await page.getByTestId("more-filters-dropdown").locator(":scope > summary").click();
    const trackFacet = page.getByTestId("filter-facet-track");
    await expect(trackFacet).toBeVisible();
    const trackSummary = trackFacet.locator("summary");
    await trackSummary.click();
    await expect(trackFacet).toHaveAttribute("open", "");
    await expect.poll(() => trackFacet.locator('input[type="checkbox"]').count(), { timeout: 15_000 }).toBeGreaterThan(1);
    const employmentTrack = trackFacet.getByRole("checkbox", { name: "employment", exact: true });
    const contractTrack = trackFacet.getByRole("checkbox", { name: "contract", exact: true });
    await employmentTrack.check();
    await contractTrack.check();
    await expect(employmentTrack).toBeChecked();
    await expect(contractTrack).toBeChecked();
    await expect.poll(() =>
      page.evaluate(() => new URLSearchParams(window.location.search).getAll("track").length)
    ).toBe(2);
    await trackSummary.click();
    await expect(trackFacet).not.toHaveAttribute("open", "");
    const moreFilters = page.getByTestId("more-filters-dropdown");
    await moreFilters.locator(":scope > summary").click();
    await expect(moreFilters).not.toHaveAttribute("open", "");
    await page.getByRole("search", { name: "Filter opportunities" }).getByRole("button", { name: "Clear filters" }).click();
    await expect.poll(() =>
      page.evaluate(() => new URLSearchParams(window.location.search).getAll("track").length)
    ).toBe(0);

    // 4c. Card multi-select and batch toolbar must be visible on the hosted UI.
    // A live filter clear triggers an async feed refresh; wait for the feed to
    const visibleCards = page.locator('[data-testid^="opportunity-card-"]');
    const selectAllVisible = page.getByRole("button", { name: "Select all visible" });
    const batchToolbar = page.getByTestId("batch-action-toolbar");
    await expect.poll(() => visibleCards.count(), { timeout: 15_000 }).toBeGreaterThan(0);
    await expect(visibleCards.first()).toBeVisible();
    await expect(selectAllVisible).toBeVisible();
    await selectAllVisible.click();
    await expect(batchToolbar).toBeVisible();
    const selectionBoxes = page.locator('input[type="checkbox"][aria-label^="Select "]');
    expect(await selectionBoxes.count()).toBeGreaterThan(0);
    await expect(selectionBoxes.first()).toBeChecked();
    await page.getByRole("button", { name: "Clear selection" }).click();
    await expect(batchToolbar).toHaveCount(0);

    // This hosted site uses real Founder history. Verify the Save affordance
    // without writing a Save/Undo event pair; action transitions run in the
    // disposable PostgreSQL/browser suites instead.
    const quickSave = page.locator('[data-testid^="quick-save-"]').first();
    await expect.poll(() => page.locator('[data-testid^="quick-save-"]').count(), { timeout: 15_000 }).toBeGreaterThan(0);
    await expect(quickSave).toBeVisible();
    await expect(quickSave).toBeEnabled();
    console.log("FR008_HOSTED_SAVE_MUTATION_SKIP reason=no_isolated_founder_fixture");

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
    }>(page, "/api/opportunities?sort_by=for_you&page=1&page_size=1");

    expect(firstPage.ok, `feed returned ${firstPage.status}: ${safeApiErrorSummary(firstPage.body)}`).toBe(true);
    expect(typeof firstPage.body.page).toBe("number");
    expect(typeof firstPage.body.page_size).toBe("number");
    expect(typeof firstPage.body.total).toBe("number");
    expect(Array.isArray(firstPage.body.items)).toBe(true);

    // Founder acceptance requires an actual For You recommendation, not a
    // review-only corpus that would make the card latency measurement vacuous.
    if (firstPage.body.total < 1) {
      throw new Error(
        `Staging corpus has no For You rows (total=${firstPage.body.total}); run the bounded BC candidate refresh before hosted acceptance.`
      );
    }

    expect(firstPage.body.items).toHaveLength(1);
    const first = firstPage.body.items[0];
    expect(typeof first.id).toBe("string");
    expect(first.title.length).toBeGreaterThan(0);
    expect(first.organization.length).toBeGreaterThan(0);
    expect(first.source_url.length).toBeGreaterThan(0);

    // 5a. FR-008 live productivity controls must be present and functional,
    // not merely compiled into an undeployed branch.
    // Clearing the earlier filter closes the containing disclosure, so reopen
    // it before checking the nested Track checklist on desktop and mobile.
    const liveMoreFilters = page.getByTestId("more-filters-dropdown");
    await liveMoreFilters.locator(":scope > summary").click();
    await expect(liveMoreFilters).toHaveAttribute("open", "");
    const liveTrackFacet = page.getByTestId("filter-facet-track");
    await expect(liveTrackFacet).toBeVisible();
    const liveTrackSummary = liveTrackFacet.locator("summary");
    await liveTrackSummary.click();
    await expect(liveTrackFacet.locator('input[type="checkbox"]').first()).toBeVisible();
    expect(await liveTrackFacet.locator('input[type="checkbox"]').count()).toBeGreaterThan(1);
    await page.keyboard.press("Enter");

    const sourceFamilyFacet = page.getByTestId("filter-facet-source-family");
    const activityFacet = page.getByTestId("filter-facet-activity");
    const feedbackFacet = page.getByTestId("filter-facet-feedback");
    for (const facet of [sourceFamilyFacet, activityFacet, feedbackFacet]) {
      await expect(facet).toBeVisible();
      const summary = facet.locator("summary");
      await summary.click();
      await expect(facet, `facet ${await facet.getAttribute("data-testid")} should open`).toHaveAttribute("open", "");
      await expect.poll(
        () => facet.locator('input[type="checkbox"]').count(),
        { timeout: 15_000, message: `facet ${await facet.getAttribute("data-testid")} should expose multiple options` }
      ).toBeGreaterThan(1);
      await summary.click();
    }

    // Prove the primary Source checklist uses repeated live query params, not
    // a single-select facade. Clear immediately so the rest of smoke remains
    // corpus-neutral.
    const sourceFamilySummary = sourceFamilyFacet.locator("summary");
    await sourceFamilySummary.click();
    const sourceFamilyBoxes = sourceFamilyFacet.locator('input[type="checkbox"]');
    await sourceFamilyBoxes.nth(0).check();
    await sourceFamilyBoxes.nth(1).check();
    await expect.poll(() =>
      page.evaluate(() => new URLSearchParams(window.location.search).getAll("source_family").length)
    ).toBe(2);
    await page.getByRole("search", { name: "Filter opportunities" }).getByRole("button", { name: "Clear filters" }).click();

    await page.getByTestId("open-advanced-feed-filters").click();
    const advancedDrawer = page.getByTestId("feed-query-drawer");
    await expect(advancedDrawer).toBeVisible();
    const sourceFacet = page.getByTestId("feed-facet-source_id");
    const sourceFacetSummary = sourceFacet.locator("summary");
    await sourceFacetSummary.click();
    const sourceIdOptions = sourceFacet.locator('input[type="checkbox"]');
    if (await sourceIdOptions.count() > 1) {
      await expect(sourceIdOptions.first()).toBeVisible();
    } else {
      // Board IDs depend on the selected source family and live projection.
      console.log("FR008_HOSTED_SOURCE_ID_SKIP reason=no_board_ids_available");
    }
    await page.keyboard.press("Escape");
    await expect(advancedDrawer).not.toBeVisible();

    const metricPeriod = page.getByTestId("metric-period");
    await expect(metricPeriod).toBeVisible();
    const metricsResponse = (period: string, date?: string) => page.waitForResponse((response) => {
      const url = new URL(response.url());
      return url.pathname === "/api/dashboard/daily"
        && url.searchParams.get("period") === period
        && (!date || url.searchParams.get("date") === date);
    });
    const yesterday = new Date(Date.now() - 86400000).toISOString().slice(0, 10);
    const yesterdayResponsePromise = metricsResponse("yesterday");
    await metricPeriod.selectOption("yesterday");
    await expect(metricPeriod).toHaveValue("yesterday");
    const yesterdayResponse = await yesterdayResponsePromise;
    expect(yesterdayResponse.ok(), "Yesterday metrics should load").toBe(true);
    const yesterdayMetrics = await yesterdayResponse.json() as { days: number; series: Array<{ date: string }> };
    expect(yesterdayMetrics.series[0]?.date).toBe(yesterday);
    await metricPeriod.selectOption("date");
    const selectedDate = page.getByTestId("metric-specific-date");
    await expect(selectedDate).toBeVisible();
    const specificDateResponsePromise = metricsResponse("date", yesterday);
    await selectedDate.fill(yesterday);
    const specificDateResponse = await specificDateResponsePromise;
    expect(specificDateResponse.ok(), "Specific-date metrics should load").toBe(true);
    const specificDateMetrics = await specificDateResponse.json() as { days: number; series: Array<{ date: string }> };
    expect(specificDateMetrics.series[0]?.date).toBe(yesterday);
    const allTimeResponsePromise = metricsResponse("all_time");
    await metricPeriod.selectOption("all_time");
    const allTimeResponse = await allTimeResponsePromise;
    expect(allTimeResponse.ok(), "All-time metrics should load").toBe(true);
    const allTimeMetrics = await allTimeResponse.json() as { days: number; series: Array<{ date: string }> };
    expect(allTimeMetrics.series).toHaveLength(1);
    expect(allTimeMetrics.series[0]?.date).toBe("all_time");
    const todayResponsePromise = metricsResponse("today");
    await metricPeriod.selectOption("today");
    await expect(metricPeriod).toHaveValue("today");
    const todayResponse = await todayResponsePromise;
    expect(todayResponse.ok(), "Today metrics should load").toBe(true);
    const todayMetrics = await todayResponse.json() as { days: number; series: Array<{ date: string }> };
    expect(todayMetrics.series[0]?.date).toBe(new Date().toISOString().slice(0, 10));
    console.log(`FR008_HOSTED_DASHBOARD_TIMING yesterday=${yesterdayResponse.headers()["server-timing"] ?? "unavailable"} all_time=${allTimeResponse.headers()["server-timing"] ?? "unavailable"} today=${todayResponse.headers()["server-timing"] ?? "unavailable"}`);

    const reviewableSaveButtons = page.locator('[data-testid^="quick-save-"]');
    if (await reviewableSaveButtons.count() >= 2) {
      const selectionBoxes = page.locator('input[type="checkbox"][aria-label^="Select "]');
      await selectionBoxes.nth(0).check();
      await selectionBoxes.nth(1).check();
      const batchToolbar = page.getByTestId("batch-action-toolbar");
      await expect(batchToolbar).toBeVisible();
      await expect(page.getByText("2 selected", { exact: true })).toBeVisible();
      await expect(batchToolbar.getByRole("button", { name: "Save", exact: true })).toBeEnabled();
      await expect(batchToolbar.getByRole("button", { name: "Reject", exact: true })).toBeEnabled();
      await expect(batchToolbar.getByRole("button", { name: "Mark Applied", exact: true })).toBeEnabled();
      await page.getByRole("button", { name: "Clear selection" }).click();
    } else {
      console.log("FR008_HOSTED_BATCH_CONTROLS_SKIP reason=fewer_than_two_reviewable_jobs");
    }

    // 5b. First authenticated UI feed request plus repeated same-origin probes.
    // The first request is captured from the real browser flow immediately
    // after login; edge/backend Server-Timing separates the subsequent hops.
    // It is reported as the first request, not treated as a guaranteed cold
    // process start because an unauthenticated request may have warmed the edge.
    const feedLatencies = [firstPage.elapsed_ms];
    const feedTtfbLatencies = [firstPage.ttfb_ms];
    const feedServerTimings = [firstPage.server_timing];
    for (let i = 0; i < 19; i += 1) {
      const sample = await pageJson<{ total: number; items: Array<{ id: string }> }>(
        page,
        "/api/opportunities?sort_by=for_you&page=1&page_size=1"
      );
      expect(sample.ok, `SLO sample ${i + 2} returned ${sample.status}`).toBe(true);
      // Live ingestion/evaluation is allowed to change the corpus between SLO
      // samples. This hosted smoke therefore proves the feed stays healthy and
      // contract-correct while work is landing, rather than incorrectly
      // requiring a numerically frozen production snapshot.
      expect(sample.body.total).toBeGreaterThan(0);
      expect(typeof sample.body.items[0]?.id).toBe("string");
      feedLatencies.push(sample.elapsed_ms);
      feedTtfbLatencies.push(sample.ttfb_ms);
      feedServerTimings.push(sample.server_timing);
    }
    const sortedLatencies = [...feedLatencies].sort((a, b) => a - b);
    const p95Index = Math.max(0, Math.ceil(sortedLatencies.length * 0.95) - 1);
    const p95Ms = sortedLatencies[p95Index];
    expect(firstAuthenticatedFeed.length).toBeGreaterThan(0);
    console.log(
      `FR007_HOSTED_FEED_SLO project=${test.info().project.name} first_authenticated_total_ms=${firstAuthenticatedFeed[0].elapsed_ms.toFixed(2)} first_authenticated_server_timing=${firstAuthenticatedFeed[0].server_timing} probe_first_total_ms=${firstPage.elapsed_ms.toFixed(2)} probe_first_ttfb_ms=${firstPage.ttfb_ms.toFixed(2)} warm_total_p95_ms=${p95Ms.toFixed(2)} warm_ttfb_p95_ms=${[...feedTtfbLatencies].sort((a, b) => a - b)[Math.max(0, Math.ceil(feedTtfbLatencies.length * 0.95) - 1)].toFixed(2)} samples=${feedLatencies.length} edge_and_backend=${feedServerTimings.join("|")}`
    );
    expect(p95Ms, "Hosted normal feed p95 must remain <= 1500ms").toBeLessThanOrEqual(1500);

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

    // 10. UI detail drawer, source link, and PDF preview when the live For You
    // projection contains a rendered card. The API detail/artifact contracts
    // below remain covered even when this Founder feed is legitimately empty.
    const firstCard = page.locator('[data-testid^="opportunity-card-"]').first();
    const drawer = page.getByRole("dialog");
    let interactiveOpportunityId = first.id;
    const hasRenderedCard = (await firstCard.count()) > 0;
    if (hasRenderedCard) {
      await expect(firstCard).toBeVisible();
      const firstCardTestId = await firstCard.getAttribute("data-testid");
      expect(firstCardTestId).toMatch(/^opportunity-card-.+/);
      interactiveOpportunityId = firstCardTestId!.slice("opportunity-card-".length);
      await firstCard.click();
      await expect(drawer).toBeVisible();

      // Founder detail view must use the desktop canvas rather than regress to
      // the component library's narrow default dialog width.
      const viewport = page.viewportSize();
      const drawerBox = await drawer.boundingBox();
      expect(drawerBox).not.toBeNull();
      if (viewport && viewport.width >= 1024 && drawerBox) {
        expect(
          drawerBox.width / viewport.width,
          "Desktop opportunity detail modal must use at least 65% of the viewport width"
        ).toBeGreaterThanOrEqual(0.65);
      }

      const sourceLink = drawer.getByRole("link", { name: /View original source/i });
      await expect(sourceLink).toBeVisible();
      expect(await sourceLink.getAttribute("href")).toBeTruthy();

      const pdfPreview = drawer.getByTestId("artifact-pdf-preview");
      await expect(pdfPreview).toBeVisible();
    } else {
      console.log("FR008_HOSTED_DETAIL_UI_SKIP reason=no_visible_for_you_jobs");
    }

    // 11. Fixed CV preview and download from founder-cv-portfolio (ADR-0024)
    const cvPreview = await pageBinary(
      page,
      `/api/opportunities/${encodeURIComponent(interactiveOpportunityId)}/artifacts/cv-final.pdf`
    );
    expect(cvPreview.ok, `CV preview returned ${cvPreview.status}`).toBe(true);
    expect(cvPreview.contentType).toContain("application/pdf");
    expect(cvPreview.contentDisposition.toLowerCase()).toContain("inline");
    expect(cvPreview.prefix).toEqual([0x25, 0x50, 0x44, 0x46]); // %PDF
    expect(cvPreview.size).toBeGreaterThan(0);

    const cvDownload = await pageBinary(
      page,
      `/api/opportunities/${encodeURIComponent(interactiveOpportunityId)}/artifacts/cv-final.pdf?download=true`
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
      `/api/opportunities/${encodeURIComponent(interactiveOpportunityId)}/artifacts/cover-letter.docx`
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

    if (hasRenderedCard) {
      await page.keyboard.press("Escape");
      await expect(drawer).not.toBeVisible();
    }

    // No Save/Undo mutation is made against the real Founder account here;
    // the authenticated UI affordance is covered above and transitions run in
    // the disposable real-PostgreSQL/browser suite.

    // 14. Read source health only; do not enqueue fresh polls after queue convergence.
    const sources = await pageJson<{ sources: Array<{ source_id: string }> }>(page, "/api/sources/health");
    expect(sources.ok, `source health returned ${sources.status}`).toBe(true);
    expect(Array.isArray(sources.body.sources)).toBe(true);
    expect(sources.body.sources.length).toBeGreaterThan(0);

    // 15. Logout invalidates hosted session and subsequent protected request is 401
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
