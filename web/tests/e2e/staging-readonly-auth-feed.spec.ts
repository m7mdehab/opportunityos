import { test, expect } from "@playwright/test";

const FOUNDER_EMAIL = process.env.E2E_FOUNDER_EMAIL ?? "";
const FOUNDER_PASSWORD = process.env.E2E_FOUNDER_PASSWORD ?? "";

test("Founder can authenticate and read the current feed without mutations", async ({ page }) => {
  const unexpectedWrites: string[] = [];
  const stagingOrigin = new URL(process.env.OPOS_STAGING_WEB_URL ?? "").origin;
  page.on("request", (request) => {
    const url = new URL(request.url());
    if (url.origin !== stagingOrigin) return;
    if (!url.pathname.startsWith("/api/")) return;
    const method = request.method().toUpperCase();
    if (method === "GET" || method === "HEAD" || (method === "POST" && url.pathname === "/api/auth/login")) return;
    unexpectedWrites.push(`${method} ${url.pathname}`);
  });

  await page.goto("/");
  await expect(page).toHaveURL(/\/login$/);
  await page.getByLabel(/Founder email/i).fill(FOUNDER_EMAIL);
  await page.getByLabel(/Password/i).fill(FOUNDER_PASSWORD);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/\/$/);
  await expect(page.getByRole("heading", { name: "OpportunityOS" })).toBeVisible();

  const feed = await page.evaluate(async () => {
    const response = await fetch("/api/opportunities?page=1&page_size=1", { credentials: "same-origin" });
    return { status: response.status, body: await response.json() };
  });
  expect(feed.status, "authenticated feed request must succeed").toBe(200);
  expect(typeof feed.body.total).toBe("number");
  expect(Array.isArray(feed.body.items)).toBe(true);
  const visibleCards = await page.locator('[data-testid^="opportunity-card-"]').count();
  console.log(`FOUNDER_READONLY_FEED_OBSERVED total=${feed.body.total} api_rows=${feed.body.items.length} cards=${visibleCards}`);
  expect(feed.body.items.length, "feed API must return at least one current opportunity").toBeGreaterThan(0);
  expect(feed.body.items[0]).toMatchObject({ id: expect.any(String), title: expect.any(String) });
  expect(visibleCards, "authenticated Founder page must render the current feed").toBeGreaterThan(0);
  expect(feed.body.total, "feed's reported result count must include its returned item").toBeGreaterThan(0);
  expect(unexpectedWrites, "smoke must not invoke Founder actions or source/queue operations").toEqual([]);
  console.log(`FOUNDER_READONLY_AUTH_FEED=PASS total=${feed.body.total} api_rows=${feed.body.items.length} cards=${visibleCards}`);
});
