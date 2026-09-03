# C3 acceptance run

Worktree `wt/fr006-c3`, ports web 3100 / api 8100 (mock config's built-in
port matches; `npx playwright test` runs the MSW mock, not the real API).

## C3.1 — `npm run build`

Exit 0. Route list:

```
Route (app)
┌ ○ /
├ ○ /_not-found
└ ○ /login
```

`/` and `/login` only (plus Next's internal `/_not-found`, unchanged from
before this order).

## C3.2 — `npm run lint` (run after a Playwright run had created `test-results/`)

```
> web@0.1.0 lint
> eslint . --max-warnings=0
```

Clean, `--max-warnings=0`, exit 0.

## C3.3 — `npx playwright test`

```
Running 20 tests using 1 worker
...
  20 passed (1.2m)
```

20 tests, 20 passed, 0 failed. Not a zero-test run.

## C3.4 — keyboard spec (`tests/e2e/keyboard.spec.ts`)

- `j`/`k`: asserted by which card carries `data-keyboard-focused="true"`
  changing, **and** `document.activeElement`'s own `data-testid` matching
  it (real DOM focus, not a CSS-only highlight).
- `o`: asserted by the drawer opening with that card's own title as its
  heading.
- `a`: asserted by the `POST .../actions` response body
  (`action_state: "submitted"`) and the "Applied" badge appearing.
- `x`: asserted by the `POST .../actions` response body
  (`action_state: "dismissed"`) and the "Dismissed" badge appearing.
- Suppression: asserted by zero `POST .../actions` requests firing while
  typing "a" into the search input, with `document.activeElement` proven
  to be that `INPUT` first.

All 4 tests pass (see C3.3's full list).

## C3.5 — axe (`tests/e2e/axe.spec.ts`)

```
Running 2 tests using 1 worker
  ok 1 ... /login is axe-clean (2.6s)
  ok 2 ... / (the feed) is axe-clean (2.9s)
  2 passed (23.4s)
```

Zero violations on both `/login` and `/` (feed, with cards, facets/manual
sources buttons, HIDDEN stat button all rendered).

**Configured levels:** `axe.spec.ts` calls `new AxeBuilder({ page }).analyze()`
with no `.withTags(...)` call — unchanged by this order. That means axe-core's
**default enabled rule set** runs, which is not scoped to a single named
WCAG level (it spans WCAG 2.0/2.1 A and AA rules plus axe's best-practice
rules that are enabled by default). This order did not add a `.withTags()`
call, so "axe clean" here means "clean against axe-core's default rule set",
not a claim about a specific single level (e.g. AA alone).

## C3.6 — facet spec (`tests/e2e/facets.spec.ts`, "one include and one exclude...")

Exercises the `track` facet: sets one value to `exclude` through the facet
panel's per-value `<select>`, confirms the exclusion chip and the
"Show N excluded by track" button, then clicks that button and confirms the
chip disappears and the facet's `exclude` array is empty again (the API
response is asserted directly, not just the UI). Passes.

## C3.7 — saved-view spec

Create (via the panel's name field + "Save view"), select (apply), set
default (star toggle, asserted `is_default: true` in the PUT response and
the control becoming disabled), then close-and-reopen the panel and
independently re-fetch `GET /api/saved-views` — the view and its default
flag both survive. See the spec's own comment for why this does not use a
literal `page.reload()` against the mock (named as an assumption below).
Passes.

## C3.8 — hidden-reasons spec

HIDDEN stat (`stat-hidden_by_filters`) is now a `<button>`; clicking it
opens the audit table (`GET /api/hidden-reasons`). Clicking "Unhide all" on
the `filter: min_fit_score` row calls `POST /api/hidden-reasons/unhide` and
the subsequent `GET /api/opportunities` response's `hidden_count` is
strictly less than before. Passes.

Also in this file: the >10% over-hiding warning (Master's addition #1) —
constructs the condition by enabling `min_fit_score` at 100 through the
Filters drawer, asserts the fraction genuinely exceeds 10% via a live API
read, and asserts the banner (`data-testid="over-hiding-warning"`) is
visible with the same hidden/total numbers. Passes.

And the `language` facet (Master's addition #2): asserted to render with
`data-facet-effect="unavailable"`, containing "Unavailable", and with **no**
`<select>` control at all. Passes.

## C3.9 — screenshots

```
reports/evidence/FR-006/screenshots/
  d7-login-360.png    9.7K
  d7-login-1280.png   12.9K
  d7-feed-360.png     110.5K
  d7-feed-1280.png    103.1K
```

`screenshots.spec.ts`'s `EVIDENCE_DIR` repointed from `FR-005` to
`FR-006/screenshots` (this order's required rename).
