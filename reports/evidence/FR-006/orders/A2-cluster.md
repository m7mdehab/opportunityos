# Work order A2 — Near-duplicate clustering into families

**Brief:** BRIEF-FR-006 §2 Track A. **Wave:** 2. **Depends on:** A1 (integrated).
**Worktree/branch:** `wt/fr006-a2` **Test DB:** `opportunityos_test_a2`

**First action, before anything else:** `git merge --no-edit feat/brief-fr-006-nothing-missed`
from your worktree root, so you have the work orders, the migration `0004`, and A1's corpus.

## Why this exists

The founder's first real run showed **twenty near-identical "Senior Customer Engineer" cards at
fit 73**, differing only by location. Twenty cards for one job is not twenty opportunities; it is
one opportunity and nineteen units of noise in a feed the founder has to read by hand.

## Deliverable text (verbatim from the brief)

> **A2 — Near-duplicate clustering.**
> - Postings with the same employer + normalized title and differing only in location/team suffix
>   collapse into one *family* card with a location list ("Senior Customer Engineer — 14
>   locations"); the family carries the best-fit member's score and expands in the drawer.
>   Clustering is deterministic (`family_key`), stored (`0004`), and reversible per family from
>   the UI ("show separately").
> - **Acceptance:** the Cloudflare "Senior Customer Engineer" set in the fixture corpus collapses
>   to one family; families never merge different employers or different normalized titles.

## Facts established by the Master — do not re-derive

- Migration `0004_founder_control` **already exists** (work order A1) and already contains the
  `family_key` column on `opportunities` and the `opportunity_families` table
  (`family_key` PK, `employer`, `normalized_title`, `member_count`, `best_member_id`,
  `split_out`, `updated_at`). **Do not write a migration.** If you need a column that is not
  there, stop and report it as a scope question — writing `0005` is a FAIL.
- A1 committed a raw-payload corpus under `opportunity/fixtures/corpus/` that includes the
  Cloudflare Greenhouse board. That is the set your acceptance measures.
- Work order B3 provides `matching/title_family.py::normalize_title`. If it is on your base, use
  it for the normalized title; if it is not, implement clustering against a title normalizer of
  your own **behind the same function signature** so the Master can swap it at integration, and
  say clearly in your return which one your numbers came from.
- `opportunity/dedupe.py` already does exact/fingerprint deduplication. Clustering is a **layer
  above** it: dedupe removes the same posting seen twice; clustering groups genuinely different
  postings for the same role. Do not conflate them and do not weaken dedupe.

## Required behaviour

1. **`opportunity/clustering.py`** — `family_key(opportunity) -> str`, deterministic and pure.
   Derived from the employer plus the normalized title, with location and team suffixes stripped.
   Same inputs must always yield the same key, independent of dict or set iteration order, and
   independent of the order rows were polled in. A test recomputes keys over the whole corpus
   twice and asserts identical output.
2. **Family membership rules, asserted over the whole corpus, not a sample:**
   - **zero** families span two different employers;
   - **zero** families span two different normalized titles;
   - a posting with no sibling is a family of one and behaves exactly like a plain card.
3. **The family card**: carries the **best-fit member's score** (not an average — the founder
   should see the best version of an opportunity), a location list, and the member count.
   The feed returns one row per family by default.
4. **`split_out` — "show separately"**: reversible per family and persisted. Setting it makes the
   family's members appear as individual cards; unsetting it re-collapses them. Round-trip tested
   through the repository layer.
5. **Never merge across decisions.** If two members of a family have different qualification
   decisions, the family card shows the best-fit member's decision **and** flags that members
   differ. A family must never hide an `ineligible` member's status behind a `qualified` sibling,
   and clustering must never change any member's `decision` or `fit_score`. Assert this.
6. **Backfill**: a batch that computes `family_key` for existing rows, idempotent on a second run.

## Allowed files

`opportunity/clustering.py` (new) · `opportunity/test_clustering.py` (new) ·
`opportunity/persistence.py` and `opportunity/test_persistence.py` (writing `family_key` only) ·
`storage/repository.py` and `storage/test_postgres_integration.py` (the families table only) ·
`worker/handlers.py` (a backfill handler only) ·
`reports/evidence/FR-006/a20-clustering-run.md`.

## Frozen — touching any of these is a FAIL

Any migration · `opportunity/models.py`, `opportunity/adapters/**`,
`opportunity/normalization.py`, `opportunity/fixtures/**` · `opportunity/dedupe.py` ·
`matching/**` · `truth/**` · `api/**` · `web/**` · `private/`.

## Acceptance rows — paste raw output for each

| # | Command | Expected |
|---|---|---|
| A2.1 | `py -3.12 -m unittest opportunity.test_clustering -v` | `OK`, >= 15 tests |
| A2.2 | `py -3.12 -m unittest discover -s opportunity -p "test_*.py" and py -3.12 -m unittest discover -s storage -p "test_*.py" -v` | `OK`, counts stated |
| A2.3 | a corpus run printing every family with its member count | the Cloudflare "Senior Customer Engineer" set is **one** family; its member count is printed |
| A2.4 | the whole-corpus invariant check | **zero** families spanning two employers; **zero** spanning two normalized titles — both printed as counts over the full corpus |
| A2.5 | the determinism check | keys recomputed over the corpus twice are identical; the comparison is printed |
| A2.6 | the `split_out` round-trip test | collapse → split → collapse, with the row counts at each step |
| A2.7 | the no-re-judgement test | no member's `decision` or `fit_score` differs before and after clustering |

Paste the `Ran N tests` and `OK`/`FAILED` lines verbatim. State which title normalizer produced
your numbers.
