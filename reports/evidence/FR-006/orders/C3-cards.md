# Work order C3 — Cards that answer the founder's first three questions

**Brief:** BRIEF-FR-006 §2 Track C node C3, plus the UI halves of C1, C4 and E23.
**Wave:** 3. **Depends on:** C1 (facets API), B2 (specific reasons), A2 (families), E23 (manual sources).
**Worktree/branch:** `wt/fr006-c3` **Test DB:** `opportunityos_test_c3` **Ports:** web `3100`, api `8100`.
**Turn budget:** 90. **Spend at most 12 turns reading before you write your first file.**

**First action:** `git merge --no-edit feat/brief-fr-006-nothing-missed` from your worktree root.

## Why this exists

The founder opened the feed over real data and **no card said whether the job was remote, hybrid
or on-site, or where it was**. Every card said *Uncertain*. Twenty of them were the same job.
The data to answer all three now exists — work orders A1, A2, B1, B2 and B3 put it there. Your job
is to put it on the screen.

## Deliverable text (verbatim from the brief)

> **C3 — Cards that answer the founder's first three questions.**
> - Card shows: title (family badge), employer, **work mode + location + remote scope**,
>   employment type, seniority, compensation if stated, posted age, source, decision, score, the
>   top three *specific* reasons (B2), family size if clustered, action state, feedback state.
>   Employer logo/domain when available. Keyboard navigation between cards; `j/k`, `o` open,
>   `a` mark applied, `x` dismiss.
> - Drawer: full description (sanitised HTML), requirements split required/nice-to-have with your
>   match against each, geography reasoning, every field's provenance, artifacts panel (D),
>   tracker panel (mark applied / dismiss / snooze / notes), feedback panel.
> - **Acceptance:** axe clean; Playwright covers keyboard flow; screenshots at 360/1280 in evidence.

You also build the UI halves of three other nodes:

- **C1**: the facet panel — include / exclude / off per facet with counts, exclusion chips, and
  "Show N excluded by <facet>"; saved views with a default.
- **C4**: the dashboard HIDDEN number links to a reason → count table with one-click
  "unhide all by this reason", and the >10% warning is visible.
- **E23**: a **"Check manually"** panel listing every `manual_only` source with the founder's
  search prefilled as a deep link.

## Facts established by the Master — do not re-derive

- Next.js 16.3.4, React 19.2.8. Pages: `web/app/page.tsx` (feed), `web/app/login/page.tsx`,
  `web/app/layout.tsx`. Components: `web/components/feed/opportunity-card.tsx` (133 lines),
  `web/components/feed/filters-drawer.tsx` (468 lines). API wrapper: `web/lib/api/client.ts`,
  a single `request()`, same-origin `/api/*`.
- Existing specs: `web/tests/e2e/{axe,filters,filters-unavailable,screenshots,smoke}.spec.ts`.
- `web/eslint.config.mjs` must keep ignoring `playwright-report/**`, `playwright-report-real/**`
  and `test-results/**` — FR-005 found lint clean on a fresh checkout and 514 errors after a
  Playwright run. If you add an artifact directory, add it to the ignore list.
- **Routes stay `/` and `/login` only.** The facet panel, the drawer, the audit table and the
  "Check manually" panel are components on `/`, not new pages. Claim A-7 asserts the route list.
- The feed item JSON already carries `hidden_by` and `flagged_by`; work order C1 adds the facet
  fields, the family fields and the specific reasons. If a field you need is missing from the API,
  **stop and report it as a scope question** — do not add an API route from the web worktree.

## Required behaviour

1. **The card answers the three questions above the fold**: what is it, where is it / can I do it
   remotely, and why is it here. Work mode, location and remote scope are **never** absent from a
   card that has the data, and where the data is genuinely absent the card says so explicitly
   rather than showing nothing.
2. **Family cards**: "Senior Customer Engineer — 14 locations", carrying the best member's score,
   expandable in the drawer, with "show separately" wired to the API.
3. **Top three reasons are the specific ones from B2** — the required-skills sentence, the
   seniority sentence with months and gap, the family match. Never a generic label.
4. **Keyboard**: `j`/`k` move, `o` opens, `a` marks applied, `x` dismisses. Focus is visible and
   managed; the shortcuts do not fire while a text input has focus. Every shortcut is covered by
   a spec that asserts **the resulting state change**, not merely that nothing threw.
5. **Facet panel**: include / exclude / off per facet with counts; exclusion chips; "Show N
   excluded by <facet>" restores them in one click. Saved views: create, pick, set default.
6. **Hidden-reasons table** reached from the dashboard HIDDEN number, with one-click unhide by
   reason, and the >10% warning rendered visibly.
7. **"Check manually" panel** listing every `manual_only` source with a prefilled deep link. These
   are links the founder clicks. The app never fetches them.
8. **Drawer**: sanitised description HTML (sanitised — treat every posting as untrusted data),
   requirements split required / nice-to-have with the founder's match against each, geography
   reasoning, per-field provenance, the artifacts panel seam (work order D2 fills it), tracker and
   feedback panels.
9. **Accessibility**: axe clean at the levels the existing `axe.spec.ts` configures. Print the
   configured levels in your return — "axe clean" without the levels is not a claim.
10. **Screenshots at 360 and 1280** committed under `reports/evidence/FR-006/screenshots/`.
    Repoint the screenshot spec's output directory from `FR-005` to `FR-006`.

## Allowed files

`web/**` · `reports/evidence/FR-006/screenshots/**` · `reports/evidence/FR-006/c3-run.md`.

## Frozen — touching any of these is a FAIL

Every Python file in the repository. If the API does not give you what the card needs, that is a
scope question you report; it is not something you fix from here.

## Acceptance rows — paste raw output for each

| # | Command | Expected |
|---|---|---|
| C3.1 | `npm run build` in `web/` | exit 0; the printed route list is **`/` and `/login` only** |
| C3.2 | `npm run lint` in `web/`, **after** a Playwright run has created its artifact directories | `eslint --max-warnings=0` clean |
| C3.3 | `npx playwright test` in `web/` | all specs pass and the count is **> 0**; a zero-test run is not a pass |
| C3.4 | the keyboard spec | `j`, `k`, `o`, `a`, `x` each asserted by the state change they cause |
| C3.5 | the axe run | **zero** violations; the configured levels printed |
| C3.6 | the facet spec | one include and one exclude exercised through the UI; "Show N excluded" restores the rows |
| C3.7 | the saved-view spec | create, select, set default, reload — the view survives |
| C3.8 | the hidden-reasons spec | HIDDEN links to the table; unhide-by-reason changes the visible count |
| C3.9 | screenshots | committed at 360 and 1280, under `reports/evidence/FR-006/screenshots/` |

Paste raw output. If a card field is unavailable because the API does not expose it, name the
field and the endpoint in your return — do not render a placeholder that looks like data.

## Additions from the Master (after C1 integrated)

1. **Wire the 10% over-hiding warning.** C1 implemented it as a pure function with tests
   (`2/10` warns, `9/100` does not) but did **not** wire it to an endpoint or the UI. The brief
   requires a **visible** warning. Surface it on the feed, and cover it with a Playwright spec
   that constructs the condition and asserts the warning is rendered.
2. **The `language` facet is permanently unavailable** — there is no persisted language data
   anywhere in the schema, and `GET /api/facets` returns it with a 422 / unavailable marker.
   Render it as visibly unavailable with its reason, exactly as the existing
   `filters-unavailable.spec.ts` does for an inert filter. Do not hide it, and do not render it as
   though it works.
3. **The facet surface is `/api/facets` (15 attributes) *plus* the surviving `/api/filters`
   (the ten policy filters).** Both must be reachable from the drawer. The ten keep their
   `hide` / `rank_only` / `label_only` semantics; the fifteen use `include` / `exclude` / `off`.
   Do not merge the two into one control set — they mean different things, and one of them
   carries an Overseer decision.
4. **Routes available to you:** `GET /api/facets`, `GET /api/saved-views`,
   `GET /api/hidden-reasons`, plus the facet parameters composed into `GET /api/opportunities`.
   If a card field you need is not in the feed item, report it as a scope question — do not add
   an API route from the web worktree.
