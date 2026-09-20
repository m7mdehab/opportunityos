# W23.1 — CODEX FOUNDER SURFACE ACCEPTANCE CORRECTION PACKET

## ROLE

Continue the W23 Founder-surface lane on the same branch.

The Overseer independently reviewed the remote branch, migration, hosted route, UI, tests, and live Supabase state. W23 contains substantial correct work, but **W23 is not accepted yet** because several Founder requirements are only partially implemented and one UI file contains real mojibake.

Do not redesign the lane. Preserve the accepted W23 work and correct only the gaps below.

## REPOSITORY / BRANCH

- Repository: `m7mdehab/opportunityos`
- Branch: `work/fr007-codex-founder-surface-corrections`
- Reviewed W23 head: `eae8b966e4da9fda148e82485dd8d529f9ae182d`
- Do not merge.
- Do not force-push.
- Read `AGENTS.md`, W23 packet, and W23 evidence first.

## ACCEPTED W23 WORK — PRESERVE

Preserve unless a deterministic test proves a correctness defect:

1. migration head `0015_hosted_founder_surface`;
2. founder_feed deduplication concept;
3. `priority_score.desc.nullslast` hosted ordering;
4. persisted evaluation JSON parsing into hosted detail;
5. centered Radix Dialog conversion;
6. hosted dashboard RPC concept;
7. direct `source_family` / `source_id` query filtering;
8. truthful Poll Now queued/skipped result concept;
9. exact Greenhouse inactive-board semantic marker helper;
10. provider bundle 0015 generation and disposable PostgreSQL proof.

## OVERSEER FINDINGS REQUIRING CORRECTION

### F1 — Header contains real mojibake

`web/components/feed/header-strip.tsx` currently contains literal strings such as:

- `â€”`

instead of the intended em dash `—`.

This is present in the actual GitHub file, not just console rendering.

Required:
- replace all mojibake with valid UTF-8;
- scan all W23-modified web files for `â€`, `Ã`, replacement characters, or similar encoding corruption;
- add a deterministic test or repository check that catches these exact W23 regressions.

### F2 — Source overview does not satisfy the Founder's source-count requirement

Current `founder_source_overview` is built **from founder_feed inward**. Consequences:

- only sources that already have at least one persisted feed row appear;
- scheduled sources with zero current rows are absent;
- the Founder cannot see that Lever/Remote OK/etc exist but currently contribute 0;
- Reddit/manual-only sources never appear at all;
- the `manual_only: source_family === "reddit"` mapping is effectively dead code because no Reddit row can be returned from the SQL view;
- family-level counts are not displayed; only individual board counts are available after selecting a family.

The Founder explicitly asked:
- where jobs are coming from **across all sources**;
- how much each source is bringing;
- ability to filter Greenhouse, Reddit, etc.

Required automated-source design:
- rebuild `founder_source_overview` from `source_schedules` LEFT JOIN canonical current founder_feed, not founder_feed LEFT JOIN schedules;
- every scheduled automated source must appear even when opportunity_count = 0;
- count only current default-feed rows: `is_stale=false` and `visible=true`;
- preserve last status/success/next due from schedule;
- source family from `split_part(source_id, ':', 1)`.

Required manual-source design:
- expose manual-only source families in the Founder source control with count 0;
- use the existing manual-source catalogue rather than inventing automated data;
- Reddit must visibly appear as `Manual only · 0 automated jobs`;
- selecting a manual-only family may legitimately yield 0 feed rows but should expose/open the existing `Check manually` path instead of pretending an automated source exists;
- never enable Reddit automated reads.

Required UI:
- source family options show **aggregated family counts**, e.g. `Greenhouse (2,299)`, `Lever (0)`, `Reddit (Manual only · 0 automated)`;
- family count is the sum of its concrete automated source rows;
- selecting a family can reveal concrete boards and their counts;
- all-source total remains clear;
- health/status should be visible in the expanded/detail source list where practical.

Add tests proving:
- a scheduled source with zero feed rows is returned;
- Greenhouse family total sums multiple boards;
- Reddit appears manual-only with 0 automated;
- selecting Reddit does not trigger or imply automated ingestion.

### F3 — Greenhouse tombstone handling is still too late and too granular

Current W23 implementation only extends `reverify_url()`.

But the existing stale sweep still:
- waits until opportunity age > 14 days;
- verifies individual opportunity URLs;
- therefore does **not** remove a fresh inactive Greenhouse board from the Founder feed promptly;
- does not implement the board/source-level efficiency contract from W23.

This directly misses the Founder complaint because the inactive postings observed were recently posted/current-feed items.

Required conservative board-level behavior:

Implement a Greenhouse **board-level availability sweep** that runs independent of opportunity age.

Safe scope:
- group current Greenhouse opportunities by `source_id`;
- for standard Greenhouse hosts (`job-boards.greenhouse.io` / `boards.greenhouse.io`), derive the board root safely from a stored source URL;
- one request per board, not one request per opportunity;
- if board root returns HTTP 404/410 -> mark that source's current opportunities stale;
- if HTTP 200 contains the exact normalized marker:
  `Page not found. The job board you were viewing is no longer active.`
  -> mark that source's current opportunities stale;
- timeout, DNS/network failure, 403, 429, 5xx, redirect ambiguity, near-match text, generic 200 -> **do not mark stale**;
- custom Greenhouse employer domains that cannot be safely reduced to a Greenhouse board root -> preserve rows unless another definitive per-opportunity signal exists;
- never delete rows;
- set `reverified_at` when a definitive board result is applied;
- a later definitive successful/current board check may un-stale rows only when the board itself is confirmed active; do not erase an independent per-job 404/410 without clear evidence.

Wire the board sweep into the existing `reverify_stale` maintenance handler or another existing bounded maintenance path. Do **not** add one HTTP request per opportunity on every poll.

Required tests:
- fresh (<14d) Greenhouse source + exact board marker -> stale immediately;
- fresh board + 404 -> stale;
- fresh board + 410 -> stale;
- fresh board + 403 -> preserved;
- fresh board + 429 -> preserved;
- fresh board + timeout/URLError -> preserved;
- fresh board + 500 -> preserved;
- fresh board + near-miss marker -> preserved;
- active 200 -> preserved;
- custom Greenhouse-domain source -> conservative preserve unless definitive;
- one request per source, not per opportunity.

### F4 — Dashboard Hidden value is currently semantically wrong

Current 0015 RPC computes `hidden_by_filters` only from:
- `opportunities.is_stale = true`
- and a hypothetical enabled `stale_postings` hide filter.

Live Founder settings currently have enabled hide filters such as:
- `red_lines`
- `excluded_industries`

So the current hosted Hidden number would incorrectly return 0 for real hidden rows.

Use the canonical feed projection instead.

Required definition:
- `hidden_by_filters` = count of current canonical Founder feed rows for that day's new opportunities whose persisted `visibility_reason` contains at least one **policy filter** reason;
- facet-only hiding must not be counted as `hidden_by_filters`;
- `visibility_reason` is generated as JSON text: policy filter IDs are plain values; facets are prefixed `facet:`;
- count an opportunity once even if multiple policy filters hide it;
- use the one-row-per-opportunity canonical W23 founder_feed view so historical projections do not double count.

Also correct hosted list semantics while touching this surface:
- default list must require `visible=true` and `is_stale=false`;
- `include_hidden=true` may include `visible=false` non-stale rows;
- `hidden_count` must be a real count rather than hard-coded 0;
- map `visibility_reason` into `hidden_by` for included hidden rows;
- stale rows remain excluded from the normal Founder feed even when include_hidden is used unless a future explicit stale-audit control is added.

Add tests for:
- red-line-hidden row contributes to Hidden;
- excluded-industry-hidden row contributes;
- row hidden by two policy filters counted once;
- facet-only hidden row does not contribute to `hidden_by_filters`;
- default hosted feed excludes `visible=false`;
- include_hidden exposes it with populated hidden_by;
- hidden_count is accurate.

### F5 — Source overview counts should align with the visible feed

Current `founder_source_overview` counts every non-stale founder_feed row, including `visible=false` rows.

The Founder asked how much each source is bringing **into the current jobs surface**.

Use current default feed semantics:
- non-stale;
- visible;
- canonical one-row-per-opportunity.

If useful, a separate `hidden_count` per source may be returned, but do not inflate opportunity_count with rows the Founder cannot currently see.

### F6 — Dialog layout is technically two-column but structurally not the requested layout

Current implementation turns the entire pre-existing vertical sequence into a CSS grid. As a result:
- separators become individual grid cells;
- sections alternate left/right mechanically rather than forming intentional primary/supporting columns;
- the job description is not a stable main reading column with a coherent support sidebar.

Required desktop composition:
- Dialog header spans full width;
- below header, explicit two-column wrapper:
  - main column: job description + source link + provenance/history where appropriate;
  - side column: fit score summary, qualification, geography, dimension scores, strengths/gaps/unknowns, feedback/triage/actions;
- artifacts may span full width if needed for preview space;
- separators belong inside their column or span deliberately;
- do not let CSS auto-placement decide the information architecture.

Required mobile:
- single-column;
- near-viewport width with safe margin;
- bounded `dvh` height;
- internal scrolling;
- outside click and Escape still close;
- close affordance remains visible/easy.

The top of the modal must immediately show:
- title
- organization/source
- decision
- **numeric fit score when available**
- work mode/location
- posted/deadline/reverified

Add a Playwright assertion for numeric fit score in the dialog header/summary on a scored fixture.

### F7 — W23 test coverage overstates D7 and source-manual acceptance

`scripts/test_w23_founder_surface.py` currently mostly asserts that strings exist in source files. Example:
- it treats the presence of `=== "reddit"` as proof Reddit is surfaced, though the SQL view cannot produce a Reddit row.

Replace weak source-string assertions with behavioral tests where practical.

Required behavioral proof:
- actual API/route fixture for zero-count scheduled source;
- manual-only Reddit entry present;
- feed visible/hidden filtering;
- canonical dedup winner;
- dashboard aggregate Hidden semantics;
- board-level stale handling;
- modal source/filter behavior.

Do not delete useful static guard tests; add real behavior proof.

## MIGRATION / BUNDLE

Keep revision name `0015_hosted_founder_surface`.

Because 0015 has not been applied live yet, it is acceptable to amend the **unapplied** 0015 migration source rather than creating 0016 solely for these W23 corrections.

After amendments:
- regenerate provider execution bundle;
- final manifest revision remains `0015_hosted_founder_surface`;
- disposable PostgreSQL proof must execute the committed bundle;
- verify RLS and Founder-only grants are unchanged.

## UTF-8 / WEB QUALITY

Run:

```bash
grep -RInE 'â€|Ã.|�' web --exclude-dir=node_modules --exclude-dir=.next
```

Equivalent cross-platform check is acceptable; result must be empty for product source files.

Then:

```bash
cd web
npm ci
npm run lint
npm run build
npx playwright test
```

## REQUIRED BACKEND TESTS

At minimum:

```bash
python -m unittest   opportunity.test_reverification   storage.test_hosted_runtime_migration   scripts.test_fr007_supabase_execution_bundle   scripts.test_fr007_supabase_execution_postgres   scripts.test_w23_founder_surface   -v

python scripts/fr007_supabase_execution_bundle.py generate
python scripts/fr007_supabase_execution_bundle.py verify
python scripts/check_repository.py
python scripts/check_guard.py --allow-missing-patterns
git diff --check
```

Run real disposable PostgreSQL with `OPOS_LIVE_PROOF_TEST=1` and record the workflow run.

## ACCEPTANCE GATE

Do not return PASS unless all of the following are true:

1. no mojibake remains;
2. source family counts are visible and correct;
3. scheduled zero-result sources are visible;
4. Reddit/manual-only appears honestly with 0 automated;
5. fresh inactive Greenhouse boards can be conservatively hidden without waiting 14 days;
6. ambiguous Greenhouse conditions preserve jobs;
7. Hidden dashboard count represents current policy-filter hidden rows, not only stale rows;
8. default hosted feed excludes hidden/stale rows;
9. include_hidden and hidden_count are real;
10. detail modal has intentional primary/supporting layout with numeric fit score visible;
11. provider bundle still executes to 0015;
12. web/build/Playwright and backend/disposable PostgreSQL proof are green.

## FINAL REPORT

Return one **W23.1 MASTER COMPLETION REPORT** with:

- STATUS PASS/BLOCKED
- start SHA = reviewed W23 head
- final local SHA
- verified remote SHA
- acceptance matrix F1–F7
- exact files changed
- source overview example payload showing zero-count automated and manual-only entries
- family aggregate count proof
- stale-board test matrix
- dashboard Hidden proof
- visible/include_hidden API proof
- modal desktop/mobile Playwright proof
- UTF-8 scan result
- provider bundle final revision
- disposable PostgreSQL workflow run ID/result
- unresolved items
- READY FOR OVERSEER INTEGRATION YES/NO

Do not merge and do not declare FR-007 closed.
