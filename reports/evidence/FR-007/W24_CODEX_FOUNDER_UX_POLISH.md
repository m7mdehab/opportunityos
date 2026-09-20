# W24 Founder UX Polish — Codex Evidence

- Base: `work/fr007-overseer-integration` @ `bebf581256dbc30a627efd714f52c8f2d27b8eb6`
- Branch: `work/fr007-codex-founder-ux-v2`
- Final clean SHA: `03b843b1be00e12b1fac6d9e7777fe7a2f17a0ff`
- Remote proof: `git ls-remote origin refs/heads/work/fr007-codex-founder-ux-v2` returned `03b843b1be00e12b1fac6d9e7777fe7a2f17a0ff`.

## Implemented

- Equal-height responsive opportunity cards with a two-column title/score header, two-line title clamp, bounded body, anchored footer, and safe `Quick apply` source links.
- Compact detail drawer with Role at a glance facts, concise strengths/watch-outs, collapsed sanitized original description, and persistent original-source link.
- One unified responsive toolbar owning Track, Decision, score, search, Source/Board, Filters, Facets, Check manually, and Tutoring Lane.
- Numeric source-health summary categories (Healthy, Empty, Attention, Never polled, Disabled), with the individual dot strip removed.
- Added deterministic W24 browser coverage at desktop 1920px and mobile 390px.

## Verification

- `npm run lint`: PASS.
- `npm run build`: PASS.
- `npm run build:worker`: PASS; OpenNext produced `.open-next/worker.js`.
- `npx playwright test tests/e2e/founder-ux-polish.spec.ts`: 3 passed.
- `npx playwright test tests/e2e/smoke.spec.ts tests/e2e/keyboard.spec.ts tests/e2e/axe.spec.ts`: 7 passed.
- `npm run test:e2e`: 27 passed.
- `git diff --check`: PASS after restoring generated screenshot outputs.

## Acceptance

- A: PASS locally — first-page card heights equal within 1px, score remains in the fixed header column, and the 1920px test covers overflow.
- B: PASS locally — every rendered card exposes an exact source URL in a new tab with `noopener`; body click still opens the drawer and existing keyboard tests remain green.
- C: PASS locally — compact facts, strengths/watch-outs, collapsed disclosure and sanitized expansion are covered.
- D: PASS locally — unified toolbar controls are rendered in one form and focused desktop checks pass.
- E: PASS locally — numeric categories are rendered; mock polled fixtures prove Healthy/Empty/Disabled and live data showed Healthy/Never polled categories.
- F: PASS locally — 390px no-overflow check and readable card/detail checks pass.
- G: PASS for the existing local web suite (27/27), including smoke, keyboard, accessibility, filters/facets, artifacts, screenshots and degraded truth-pack tests.

## Live deployment

A temporary branch-scoped caller was used only for deployment and dependent smoke, then removed in the cleanup commit.

- Deployment run: `35517119693` (`https://github.com/m7mdehab/opportunityos/actions/runs/35517119693`)
- Deploy job: SUCCESS; deployed commit `a33191d1304f10df6ec42aacca2e28169ed1e2c5`.
- Cloudflare version ID: not exposed by the public workflow API/log surface available in this session.
- Hosted smoke job: FAILURE (same run, job `106094971099`); the reusable workflow reached the Cloud Playwright Smoke step, but the hosted surface did not provide the seeded smoke dataset/session expected by the staging spec. No production or data-plane claim is made from this run.
- Live URL: `https://opportunityos.m7mdehab.com/` responded HTTP 200. A cache-busted browser inspection showed the deployed numeric source-health summary (`198 Healthy`, `0 Empty`, `0 Attention`, `145 Never polled`, `0 Disabled`) and unified toolbar. The live surface had no opportunity fixture data, so live card/detail assertions could not be completed.

## Files changed

- `web/app/page.tsx`
- `web/components/feed/detail-drawer.tsx`
- `web/components/feed/filter-bar.tsx`
- `web/components/feed/header-strip.tsx`
- `web/components/feed/opportunity-card.tsx`
- `web/tests/e2e/founder-ux-polish.spec.ts`

## Unresolved

- Hosted smoke requires a seeded staging Founder account and opportunity dataset; it failed before proving live card/detail behavior.
- Cloudflare Worker version ID and live screenshots were not available through the accessible workflow/browser surface.
- This is a UI polish branch only; no claim is made that FR-007 is closed.

READY FOR OVERSEER REVIEW: YES (with the hosted smoke/data limitation above).
