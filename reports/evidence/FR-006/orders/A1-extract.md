# Work order A1 — Work mode, location, employment type, seniority, compensation extraction

**Brief:** BRIEF-FR-006 §2 Track A. **Wave:** 1. **Depends on:** nothing.
**Worktree/branch:** `wt/fr006-a1` **Test DB:** `opportunityos_test_a1`
(create it with `py -3.12 scripts/dev_env.py testdb a1`; if `dev_env.py` is not on your base
yet, create the database with `psql -h 127.0.0.1 -U opportunityos -d postgres -c "CREATE
DATABASE opportunityos_test_a1"` and export
`OPPORTUNITYOS_DB_URL=postgresql+psycopg2://opportunityos@127.0.0.1:5432/opportunityos_test_a1`.)

You are on the critical path: three later work orders wait on your migration. Land the schema
early even if the inference table is still growing.

## Deliverable text (verbatim from the brief)

> **A1 — Work mode, location, employment type, seniority, compensation extraction.**
> - `Opportunity` gains: `work_mode` (remote | hybrid | onsite | unspecified, with
>   `work_mode_source` field provenance), `location_country` (ISO-2), `location_city`,
>   `location_region`, `remote_scope` (worldwide | region-restricted with the region list |
>   unspecified), `employment_type` populated (full_time | part_time | contract | freelance |
>   internship | unspecified), `seniority_level` populated from title *and* description,
>   `compensation_min/max/currency/period` when stated.
> - Every adapter maps its native fields first (Lever `workplaceType` + `categories.location`;
>   Greenhouse `location.name` + `offices`; Himalayas `locationRestrictions`; Remotive
>   `candidate_required_location`; RemoteOK `location`; WWR region; UNGM/World Bank/TED duty
>   station / buyer country). Only then does text inference run, and inference is recorded as
>   such in provenance.
> - Text inference rules are a committed, tested table (`opportunity/inference_rules.yaml`):
>   e.g. "Remote (US only)" -> remote, region-restricted [US]; "Hybrid — Cairo" -> hybrid,
>   EG/Cairo; "Egypt, Saudi Arabia, or UAE" -> onsite, multi-country.
> - Migration `0004`: new columns; backfill job `reextract_all` re-parses every stored
>   `raw_payload_json` so the founder's existing 11k rows get the new fields without re-polling.
> - Qualifier: geographic eligibility now resolves for any row with a country or a remote
>   scope; `UNKNOWN` only when both are absent. Per-country eligibility uses the founder's work
>   authorizations and service regions; region-restricted remote roles that exclude EG are
>   *labelled* "remote but region-restricted", never hidden.
> - **Acceptance:** on the founder-shaped synthetic corpus (>= 200 real raw payloads captured
>   from the nine live sources and committed as fixtures with employer names intact — these are
>   public postings), >= 90% of rows have a non-unspecified `work_mode`, >= 85% a country or
>   remote scope; the *Uncertain* share of qualification decisions drops below 25%. Numbers
>   reported from the actual run.

## Master's decisions — do not re-litigate these

These are recorded in the claim ledger and the report. Implement them as written.

1. **`work_mode` is a new canonical field.** `Opportunity.remote_policy` (the existing
   `RemotePolicy` enum, `opportunity/models.py`) stays as a **read-only derived alias property**
   so BRIEF-003 call sites keep working. Do not delete it and do not have two writable sources
   of truth. Add a test asserting the alias agrees with `work_mode` for every enum value.
2. **`work_mode_source`** is one of exactly `"adapter"`, `"inference"`, `"none"`, and is *also*
   recorded as a `FieldProvenance` entry for the `work_mode` field. Both. The percentage split
   between adapter and inference is an acceptance number.
3. **`remote_scope`** is `"worldwide"` | `"region_restricted"` | `"unspecified"`, with
   `remote_scope_regions` a tuple of ISO-3166-1 alpha-2 codes (or recognised region codes such
   as `EU`, `LATAM`, `EMEA`) — empty unless `region_restricted`.
4. **`seniority_level`**: populate the existing `Opportunity.seniority` field. Do not add a
   second field with a different name; if the brief's name and the code's name differ, the
   code's name wins and you say so in your return.
5. **Compensation** stays in the existing `Compensation` object; `0004` persists
   `compensation_min`, `compensation_max`, `compensation_currency`, `compensation_period` as
   columns derived from it.
6. **You own migration `0004` and you are the only work order that creates one.** It must be a
   single revision file named `storage/migrations/versions/0004_founder_control.py`,
   `down_revision = "0003_provenance_identity"`. It must be fully reversible. Its **complete
   contents are specified below** — including columns and tables that later work orders (A2,
   C1, C2, D2, E4) will use but you will not populate. Create all of them now so that no other
   implementer has to touch this file.

### Migration `0004` — complete required contents

On table `opportunities`, add:

| Column | Type | Null | Default |
|---|---|---|---|
| `work_mode` | String(16) | not null | `'unspecified'` |
| `work_mode_source` | String(16) | null | |
| `location_country` | String(2) | null | |
| `location_city` | String(128) | null | |
| `location_region` | String(64) | null | |
| `remote_scope` | String(24) | not null | `'unspecified'` |
| `remote_scope_regions` | Text (JSON array) | null | |
| `employment_type` | String(24) | not null | `'unspecified'` |
| `seniority_level` | String(24) | not null | `'unspecified'` |
| `compensation_min` | Integer | null | |
| `compensation_max` | Integer | null | |
| `compensation_currency` | String(8) | null | |
| `compensation_period` | String(16) | null | |
| `title_family` | String(64) | null | (B3 populates) |
| `title_level` | String(24) | null | (B3 populates) |
| `family_key` | String(64) | null | (A2 populates) |
| `search_tsv` | TSVECTOR | null | (C2 populates) |

Indexes: btree on `work_mode`, `location_country`, `title_family`, `family_key`; **GIN on
`search_tsv`** named `ix_opportunities_search_tsv`.

New tables (create them empty; other orders fill them):

- `opportunity_families` — `family_key` PK String(64), `employer` String(256),
  `normalized_title` String(256), `member_count` Integer, `best_member_id` String(64),
  `split_out` Boolean not null default false, `updated_at` DateTime.
- `founder_facets` — `facet_id` PK String(64), `mode` String(16) not null default `'off'`
  (`off` | `include` | `exclude`), `values_json` Text, `updated_at` DateTime.
- `founder_saved_views` — `id` PK String(64), `name` String(128) unique, `facets_json` Text,
  `search_query` Text, `is_default` Boolean not null default false, `created_at`, `updated_at`.
- `artifact_cache` — `cache_key` PK String(128), `opportunity_id` String(64),
  `truth_pack_hash` String(64), `template_id` String(32), `artifact_kind` String(32),
  `content_type` String(128), `payload` LargeBinary, `created_at` DateTime.
- `founder_opportunity_views` — `opportunity_id` PK String(64), `viewed_at` DateTime not null.

**Do not drop or alter `founder_filter_settings`.** The brief says `0004` replaces it with
`founder_facets`; the Master has ruled otherwise and recorded the deviation: the ten policy
filters carry a hide / rank_only / label_only mode vocabulary that facet include/exclude cannot
express, and claim A-18 requires that vocabulary to keep working. Both tables exist.

**Backup completeness:** adding tables to `Base.metadata` trips the BRIEF-FR-003
backup-completeness invariant. `scripts/backup_restore.py` will need the new tables registered.
That file is in your allowed list for that purpose only.

## Required behaviour

1. Model and ORM changes above, with `storage/repository.py` persisting every new column.
2. **Adapter-native mapping first, in every adapter**, exactly as the brief lists. Each adapter
   sets `work_mode_source="adapter"` when it mapped a native field.
3. **`opportunity/inference_rules.yaml`** — a committed, ordered, tested rule table. Each rule:
   an id, a pattern, and the fields it sets. Text inference runs **only** where the adapter left
   a field unset, and sets `work_mode_source="inference"`. At minimum the three worked examples
   in the brief must be rules with tests. Rules are data, not code: a new rule must be addable
   without editing Python.
4. **Backfill `reextract_all`** — a worker handler or script entry point that re-parses every
   stored `raw_payload_json` and updates the new columns in place, idempotent (running it twice
   changes nothing on the second run — assert this), batched, and safe to interrupt.
5. **Qualifier change** in `matching/qualification.py`: geographic eligibility resolves when the
   row has a country **or** a remote scope; `UNKNOWN` only when both are absent. Region-restricted
   remote roles that exclude EG are **labelled** `"remote but region-restricted"`, never hidden
   and never made `ineligible`. Per-country eligibility reads the founder's work authorizations
   and service regions from the truth graph.
6. **The corpus.** Capture **>= 200 real raw payloads** from the live read-allowed sources and
   commit them under `opportunity/fixtures/corpus/` with employer names intact (these are public
   postings). Rules:
   - Fetch only through the existing transport/registry preflight path, which enforces the
     source policy. **Never** call a source whose `policy_status` disallows reading.
   - **On any 403, 429, CAPTCHA, MFA or anti-bot response: stop that source, record the
     outcome, and never retry it.** Record it in your return.
   - The corpus must include the Cloudflare Greenhouse board (A2 needs the "Senior Customer
     Engineer" set) and payloads from at least six distinct sources.
   - Store the raw payload plus the source id, fetch timestamp, and the request URL. No
     personal data beyond what the public posting contains. `scripts/check_guard.py` must pass.
   - Add `opportunity/fixtures/corpus/` to the mirror **exclusion** if `.mirror-allowlist`
     works by allowlist, verify it is not mirrored, and say which in your return.
7. **A corpus-metrics script** printing, with denominators: corpus size; work-mode coverage %;
   country-or-remote-scope coverage %; the adapter/inference split; and the qualification
   decision distribution **before and after** (run the old qualifier path on the same corpus to
   get the before-figure — do not quote FR-005's number from memory).

## Allowed files

`opportunity/**` (models, adapters, normalization, persistence, pipeline, inference_rules.yaml,
fixtures/corpus, tests) · `matching/qualification.py` and `matching/test_qualification.py` ·
`storage/models.py`, `storage/repository.py`, `storage/migrations/versions/0004_founder_control.py`,
`storage/test_postgres_integration.py` · `worker/handlers.py` (the `reextract_all` handler only) ·
`scripts/backup_restore.py` (register the new tables only) · `scripts/corpus_metrics.py` (new) ·
`.gitignore` (only if the corpus needs an entry).

## Frozen — touching any of these is a FAIL

`truth/**` · `api/**` · `web/**` · `matching/` other than `qualification.py` ·
`storage/migrations/versions/0001|0002|0003` · any `0005+` revision · `AGENTS.md` · `docs/` ·
anything under `private/`.

## Acceptance rows — paste raw output for each

| # | Command | Expected |
|---|---|---|
| A1.1 | `py -3.12 -m unittest discover -s opportunity -p "test_*.py" -v` | `OK`, count stated |
| A1.2 | `py -3.12 -m unittest matching.test_qualification -v` | `OK` |
| A1.3 | `py -3.12 -m unittest storage.test_postgres_integration -v` | `OK` |
| A1.4 | `alembic upgrade head` then `alembic downgrade base` then `alembic upgrade head` on an empty scratch DB | 4 / 4 / 4 revisions, exit 0 each; head is `0004_founder_control` |
| A1.5 | `py -3.12 scripts/corpus_metrics.py` | prints corpus size >= 200, work-mode coverage with denominator, country-or-scope coverage, adapter/inference split, and the before/after decision distribution |
| A1.6 | `py -3.12 scripts/check_guard.py --allow-missing-patterns` and `py -3.12 scripts/check_repository.py` | both exit 0 |
| A1.7 | the `reextract_all` idempotency test | second run reports zero changes |

If a coverage percentage lands below the brief's threshold, **report the number you got**. Do
not adjust the corpus to reach a threshold — selecting fixtures to hit a number is the same
defect class as editing evidence, and is an automatic FAIL.
