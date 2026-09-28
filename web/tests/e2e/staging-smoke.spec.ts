import { test, expect, type Page } from "@playwright/test";

const FOUNDER_EMAIL = process.env.E2E_FOUNDER_EMAIL ?? "";
const FOUNDER_PASSWORD = process.env.E2E_FOUNDER_PASSWORD ?? "";

async function pageJson<T>(
  page: Page,
  path: string,
  init?: { method?: string; body?: unknown; cache?: RequestCache }
): Promise<{ status: number; ok: boolean; body: T; elapsed_ms: number }> {
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
      const text = await response.text();
      const elapsed_ms = performance.now() - started;
      return {
        status: response.status,
        ok: response.ok,
        body: text ? JSON.parse(text) : null,
        elapsed_ms,
      };
    },
    { path, init }
  ) as Promise<{ status: number; ok: boolean; body: T; elapsed_ms: number }>;
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
    await trackSummary.focus();
    await page.keyboard.press("Enter");
    await expect(trackFacet).toHaveAttribute("open", "");
    const employmentTrack = trackFacet.getByRole("checkbox", { name: "employment", exact: true });
    const contractTrack = trackFacet.getByRole("checkbox", { name: "contract", exact: true });
    await employmentTrack.check();
    await contractTrack.check();
    await expect(employmentTrack).toBeChecked();
    await expect(contractTrack).toBeChecked();
    await expect.poll(() =>
      page.evaluate(() => new URLSearchParams(window.location.search).getAll("track").length)
    ).toBe(2);
    await page.keyboard.press("Enter");
    await page.getByRole("search", { name: "Filter opportunities" }).getByRole("button", { name: "Clear filters" }).click();
    await expect.poll(() =>
      page.evaluate(() => new URLSearchParams(window.location.search).getAll("track").length)
    ).toBe(0);

    // 4c. Card multi-select and batch toolbar must be visible on the hosted UI.
    // A live filter clear triggers an async feed refresh; wait for the feed to
    const visibleCards = page.locator('[data-testid^="opportunity-card-"]');
    const selectAllVisible = page.getByRole("button", { name: "Select all visible" });
    const batchToolbar = page.getByTestId("batch-action-toolbar");
    if (await visibleCards.count()) {
      await expect(visibleCards.first()).toBeVisible({ timeout: 15_000 });
      await expect(selectAllVisible).toBeVisible({ timeout: 15_000 });
      await selectAllVisible.click();
      await expect(batchToolbar).toBeVisible();
      const selectionBoxes = page.locator('input[type="checkbox"][aria-label^="Select "]');
      expect(await selectionBoxes.count()).toBeGreaterThan(0);
      await expect(selectionBoxes.first()).toBeChecked();
      await page.getByRole("button", { name: "Clear selection" }).click();
      await expect(batchToolbar).toHaveCount(0);
    } else {
      // The live Founder feed can legitimately have no For You projection rows.
      // In that state, verify the batch action is unavailable rather than
      // fabricating jobs or mutating unrelated Founder state.
      await expect(selectAllVisible).toHaveCount(0);
      await expect(batchToolbar).toHaveCount(0);
      console.log("FR008_HOSTED_BATCH_SKIP reason=no_visible_for_you_jobs");
    }

    // 4d. Prove one hosted Save round-trip and immediately Undo it so the
    // founder-visible review state is restored after the smoke.
    const quickSave = page.locator('[data-testid^="quick-save-"]').first();
    if (await quickSave.count()) {
      await expect(quickSave).toBeVisible();
      const [liveSaveResponse] = await Promise.all([
        page.waitForResponse((response) =>
          response.request().method() === "POST" &&
          response.url().includes("/actions")
        ),
        quickSave.click(),
      ]);
      expect(liveSaveResponse.status(), await liveSaveResponse.text()).toBe(200);
      await expect(page.getByTestId("tracker-undo-notice")).toBeVisible();
      const [undoResponse] = await Promise.all([
        page.waitForResponse((response) =>
          response.request().method() === "POST" &&
          response.url().includes("/restore")
        ),
        page.getByTestId("undo-tracker-action").click(),
      ]);
      expect(undoResponse.status(), await undoResponse.text()).toBe(200);
      await expect(page.getByTestId("tracker-undo-notice")).toHaveCount(0);
    } else {
      console.log("FR008_HOSTED_SAVE_SKIP reason=no_visible_reviewable_jobs");
    }

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

    // 5a. FR-008 live productivity controls must be present and functional,
    // not merely compiled into an undeployed branch.
    await expect(page.getByTestId("filter-facet-track")).toBeVisible();
    const liveTrackSummary = page.getByTestId("filter-facet-track").locator("summary");
    await liveTrackSummary.focus();
    await page.keyboard.press("Enter");
    await expect(page.getByTestId("filter-facet-track").locator('input[type="checkbox"]').first()).toBeVisible();
    expect(await page.getByTestId("filter-facet-track").locator('input[type="checkbox"]').count()).toBeGreaterThan(1);
    await page.keyboard.press("Enter");

    const sourceFamilyFacet = page.getByTestId("filter-facet-source-family");
    const activityFacet = page.getByTestId("filter-facet-activity");
    const feedbackFacet = page.getByTestId("filter-facet-feedback");
    for (const facet of [sourceFamilyFacet, activityFacet, feedbackFacet]) {
      await expect(facet).toBeVisible();
      const summary = facet.locator("summary");
      await summary.focus();
      await page.keyboard.press("Enter");
      expect(await facet.locator('input[type="checkbox"]').count()).toBeGreaterThan(1);
      await page.keyboard.press("Enter");
    }

    // Prove the primary Source checklist uses repeated live query params, not
    // a single-select facade. Clear immediately so the rest of smoke remains
    // corpus-neutral.
    const sourceFamilySummary = sourceFamilyFacet.locator("summary");
    await sourceFamilySummary.focus();
    await page.keyboard.press("Enter");
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
    await sourceFacetSummary.focus();
    await page.keyboard.press("Enter");
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
    await metricPeriod.selectOption("yesterday");
    await expect(metricPeriod).toHaveValue("yesterday");
    await metricPeriod.selectOption("today");
    await expect(metricPeriod).toHaveValue("today");

    const reviewableSaveButtons = page.locator('[data-testid^="quick-save-"]');
    const batchIds: string[] = [];
    if (await reviewableSaveButtons.count() >= 2) {
      for (let index = 0; index < 2; index += 1) {
        const testId = await reviewableSaveButtons.nth(index).getAttribute("data-testid");
        expect(testId).toMatch(/^quick-save-.+/);
        const opportunityId = testId!.slice("quick-save-".length);
        batchIds.push(opportunityId);
        const card = page.getByTestId(`opportunity-card-${opportunityId}`);
        const listItem = card.locator("xpath=..");
        await listItem.getByRole("checkbox").check();
      }
      const batchToolbar = page.getByTestId("batch-action-toolbar");
      await expect(batchToolbar).toBeVisible();
      await expect(page.getByText("2 selected", { exact: true })).toBeVisible();
      await batchToolbar.getByRole("button", { name: "Save", exact: true }).click();
      await expect(page.getByTestId("batch-action-status")).toContainText("2 jobs updated successfully.");

      // Restore both jobs through the same hosted mutation boundary so smoke is
      // state-neutral and never leaves test activity as Founder review input.
      for (const opportunityId of batchIds) {
        const actionDetail = await pageJson<{
          action_history: Array<{ action_id: string; action_type: string }>;
        }>(
          page,
          `/api/opportunities/${encodeURIComponent(opportunityId)}?batch_restore=${Date.now()}`,
          { cache: "no-store" }
        );
        expect(actionDetail.ok, `batch detail returned ${actionDetail.status}`).toBe(true);
        const saveEvent = actionDetail.body.action_history.find((event) => event.action_type === "save");
        expect(saveEvent?.action_id, "Batch Save must create a reversible hosted activity event").toBeTruthy();
        const restored = await pageJson<{ tracker_state: string }>(
          page,
          `/api/opportunities/${encodeURIComponent(opportunityId)}/restore`,
          {
            method: "POST",
            body: {
              event_id: saveEvent!.action_id,
              idempotency_key: `staging-batch-restore-${opportunityId}-${Date.now()}`,
            },
          }
        );
        expect(restored.ok, `batch restore returned ${restored.status}`).toBe(true);
      }
      await page.reload();
      await expect(page.getByRole("heading", { name: "OpportunityOS" })).toBeVisible();
      await expect(page.getByTestId(`opportunity-card-${batchIds[0]}`)).toBeVisible();
    } else {
      console.log("FR008_HOSTED_BATCH_SAVE_SKIP reason=fewer_than_two_to_review_jobs");
    }

    // 5b. Hosted cold/warm feed SLO and logical-equivalence proof.
    // This smoke runs immediately after a fresh Cloudflare deployment. The
    // first authenticated feed read is the cold-edge observation; repeated
    // reads establish the normal-request p95 at the current hosted corpus.
    const feedLatencies = [firstPage.elapsed_ms];
    for (let i = 0; i < 19; i += 1) {
      const sample = await pageJson<{ total: number; items: Array<{ id: string }> }>(
        page,
        "/api/opportunities?page=1&page_size=1"
      );
      expect(sample.ok, `SLO sample ${i + 2} returned ${sample.status}`).toBe(true);
      // Live ingestion/evaluation is allowed to change the corpus between SLO
      // samples. This hosted smoke therefore proves the feed stays healthy and
      // contract-correct while work is landing, rather than incorrectly
      // requiring a numerically frozen production snapshot.
      expect(sample.body.total).toBeGreaterThan(0);
      expect(typeof sample.body.items[0]?.id).toBe("string");
      feedLatencies.push(sample.elapsed_ms);
    }
    const sortedLatencies = [...feedLatencies].sort((a, b) => a - b);
    const p95Index = Math.max(0, Math.ceil(sortedLatencies.length * 0.95) - 1);
    const p95Ms = sortedLatencies[p95Index];
    console.log(
      `FR007_HOSTED_FEED_SLO project=${test.info().project.name} cold_ms=${firstPage.elapsed_ms.toFixed(2)} p95_ms=${p95Ms.toFixed(2)} samples=${feedLatencies.length}`
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

    // 13. Founder Save -> Undo round-trip uses a reviewable live card where
    // available. Empty For You projections are recorded, not backfilled for smoke.
    if (batchIds.length > 0) {
      const activityOpportunityId = batchIds[0];
      const activityCard = page.getByTestId(`opportunity-card-${activityOpportunityId}`);
      await expect(activityCard).toBeVisible();

      const saveResponsePromise = page.waitForResponse((response) =>
        response.url().includes(`/api/opportunities/${activityOpportunityId}/actions`) &&
        response.request().method() === "POST"
      );
      await page.getByTestId(`quick-save-${activityOpportunityId}`).click();
      const saveResponse = await saveResponsePromise;
      expect(saveResponse.status()).toBe(200);
      await expect(page.getByTestId("tracker-undo-notice")).toBeVisible();
      await expect(page.getByTestId("undo-tracker-action")).toBeVisible();

      const restoreResponsePromise = page.waitForResponse((response) =>
        response.url().includes(`/api/opportunities/${activityOpportunityId}/restore`) &&
        response.request().method() === "POST"
      );
      await page.getByTestId("undo-tracker-action").click();
      const restoreResponse = await restoreResponsePromise;
      expect(restoreResponse.status()).toBe(200);
      await expect(page.getByTestId("undo-tracker-action")).toHaveCount(0);

      const activityDetail = await pageJson<{
        action_history: Array<{ action_type: string }>;
      }>(
        page,
        `/api/opportunities/${encodeURIComponent(activityOpportunityId)}?activity_proof=${Date.now()}`,
        { cache: "no-store" }
      );
      expect(activityDetail.ok, `activity detail returned ${activityDetail.status}`).toBe(true);
      expect(activityDetail.body.action_history.some((event) => event.action_type === "save")).toBe(true);
      expect(activityDetail.body.action_history.some((event) => event.action_type === "restore")).toBe(true);
      await expect(activityCard).toBeVisible();
    } else {
      console.log("FR008_HOSTED_ACTIVITY_SKIP reason=no_visible_reviewable_jobs");
    }

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
