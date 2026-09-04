# Work order B3 — Target-role families and title normalization

**Brief:** BRIEF-FR-006 §2 Track B. **Wave:** 1. **Depends on:** nothing.
**Worktree/branch:** `wt/fr006-b3` **Test DB:** `opportunityos_test_b3`
(`py -3.12 scripts/dev_env.py testdb b3`, or `CREATE DATABASE opportunityos_test_b3` and export
`OPPORTUNITYOS_DB_URL=postgresql+psycopg2://opportunityos@127.0.0.1:5432/opportunityos_test_b3`.)

## Deliverable text (verbatim from the brief)

> **B3 — Target-role families and title normalization.**
> - `matching/title_families.yaml`: committed families (data engineering, data science, ML/AI
>   engineering, analytics/BI, data migration, tutoring, web/frontend, ...) with alias lists and
>   regexes; every posting title normalizes to a family + level; the founder's
>   `career.target_role` assertions map onto families. Title-family match becomes a scored
>   dimension *and* a facet for filtering (C1).
> - `target_roles` filter default reverts to `rank_only` (Overseer decision, FR-005 review
>   §3.1) via data migration.
> - **Acceptance:** >= 95% of fixture-corpus titles map to a family (the rest to `other`,
>   listed in evidence); the family assignment for the top 50 fixture titles is committed and
>   reviewed by the council.

## Facts established by the Master — do not re-derive

- The predicate for the founder's target role is `CAREER_TARGET_ROLE` (`truth/predicates.py:197`).
- The `target_roles` filter lives in `api/filters.py` among ten filters whose modes are
  `hide` / `rank_only` / `label_only`. Its default shipped as `label_only` in FR-005 after a
  council finding; the Overseer has reversed that. **Your change is the default value only.**
- Migration `0004` is owned by work order A1 and already contains `title_family` and
  `title_level` columns on `opportunities`. **Do not create a migration.** The `target_roles`
  default is a data change: implement it as an idempotent settings-seed update in the
  application's existing filter-settings seed path, and if that is impossible without a
  migration, stop and report it as a scope question rather than writing `0005`.
- A1 is concurrently building a fixture corpus at `opportunity/fixtures/corpus/`. It may not
  exist when you start. Build your family mapper and its tests against a **committed list of
  titles you assemble yourself** (see below); the corpus-wide 95% measurement is a later,
  separate run that the Master will order once both have landed.

## Required behaviour

1. **`matching/title_families.yaml`** — committed data. Each family has: an id, a display name,
   an alias list, an ordered regex list, and optional negative patterns. Families must at
   minimum cover: data engineering, data science, ML/AI engineering, analytics/BI, data
   migration, tutoring, web/frontend, backend, devops/platform, customer/solutions engineering,
   product, project/program management, and `other`. **Customer/solutions engineering must be
   its own family** — the founder's 20 near-identical "Senior Customer Engineer" cards are the
   reason this brief exists, and they must be distinguishable from data engineering by family,
   not only by score.
2. **`matching/title_family.py`** — `normalize_title(title) -> (family_id, level, matched_rule)`.
   Deterministic, order-independent of dict iteration, and pure. Level is one of
   `intern` / `junior` / `mid` / `senior` / `staff` / `principal` / `unspecified`.
   The matched rule id is returned so evidence can name **why** a title mapped where it did.
3. **A scored dimension** `title_family_fit` in `matching/scorer.py`, comparing the posting's
   family against the families the founder's `CAREER_TARGET_ROLE` assertions map onto, with
   evidence refs. Weighting must not silently change the total-weight normalisation — if
   dimension weights must be rebalanced, say exactly what you changed and why.
4. **A committed title-assignment table** at
   `reports/evidence/FR-006/b3-title-assignments.md`: at least 60 real posting titles (take
   them from the existing `opportunity/fixtures/` payloads already in the repo, and from
   `SOURCE_EVIDENCE.md` if it lists titles), each with its assigned family, level, and matched
   rule id. This table is what council review #1 reads. Do not invent titles.
5. **`target_roles` default -> `rank_only`**, idempotently, with a test asserting the default.
6. Tests: every family has at least two positive and one negative case; titles that must **not**
   collide (e.g. "Data Engineer" vs "Customer Engineer", "ML Engineer" vs "Sales Engineer");
   case, punctuation, and suffix variants ("Senior Data Engineer, Platform (Remote — EU)").

## Allowed files

`matching/title_families.yaml` (new) · `matching/title_family.py` (new) ·
`matching/test_title_family.py` (new) · `matching/scorer.py` · `matching/test_scorer.py` ·
`api/filters.py` and `api/test_api.py` (the `target_roles` default only) ·
`reports/evidence/FR-006/b3-title-assignments.md` (new).

## Frozen — touching any of these is a FAIL

`truth/**` except adding a predicate constant to `truth/predicates.py` if genuinely required ·
`matching/seniority.py` (work order B1 owns it this wave) · `matching/qualification.py` ·
`opportunity/**` · `storage/**` · any migration · `web/**` · `private/`.

**Concurrency note:** work order B1 is editing `matching/scorer.py` in a different worktree at
the same time, in the `seniority_and_experience` dimension. Keep your edits confined to your new
dimension and the dimension registry so the Master's merge is a clean union. Do not reformat,
reorder, or "tidy" any part of `scorer.py` you are not adding to.

## Acceptance rows — paste raw output for each

| # | Command | Expected |
|---|---|---|
| B3.1 | `py -3.12 -m unittest matching.test_title_family -v` | `OK`, >= 25 tests |
| B3.2 | `py -3.12 -m unittest matching.test_scorer -v` | `OK` |
| B3.3 | `py -3.12 -m unittest api.test_api -v` | `OK`; a test asserts the `target_roles` default is `rank_only` |
| B3.4 | a run printing family + level + rule id for every title in `b3-title-assignments.md` | every row resolved; the count mapping to `other` is printed with the titles listed |
| B3.5 | `py -3.12 -m unittest truth.test_predicates -v` | `OK` |

Paste the `Ran N tests` and `OK`/`FAILED` lines verbatim.
