# D3 — Filters contract (Master's specification, binding on both implementers)

Written by the Master **before** dispatching D3, and checked line-by-line against the real
code rather than assumed. FR-004's worst self-inflicted defect was handing an implementer a
response shape the Master had not verified; the D6 and D7 agents then built to different
contracts. Every field below was read out of the source.

Both D3 implementers (API and web) build to **this** document. Where it disagrees with
either implementer's intuition, this document wins; where it is wrong, the implementer stops
and tells the Master rather than diverging.

---

## 1. Verified facts about the existing code

`GET /api/opportunities` is `api/routes_api.py:137-202`. It:
- accepts `track`, `decision`, `min_score`, `since`, `q`, `page`, `page_size`
- materialises **every** opportunity into Python (`query.all()`, line 160), then filters
  `decision` and `min_score` in the loop, then sorts in Python at line 195
- returns `{"page", "page_size", "total", "items"}`

Existing item fields, exactly (lines 174-191):
```
id, title, organization, source_id, source_url, track, decision, fit_score,
top_reasons, deadline, posted_date, is_stale, action_state, feedback_label
```

Because selection is already Python-side, filter evaluation goes in the same loop. No SQL
change is required for filtering, and none should be attempted.

`decision` values are lowercase (`qualified` / `ineligible` / `uncertain`). `fit_score` is
**0–100**. The web contract types live in `web/lib/contract/types.ts` and are the single
source of truth for the front end.

---

## 2. The invariant that outranks everything else in D3

> **A toggle changes whether a row is hidden, ranked, or merely labelled. It never changes
> `decision`, and it never changes `fit_score`.**

This is Appendix rule 2 of the brief and the founder's own stated requirement. Concretely:
- `decision` in the response is always the truth-derived value from the evaluation record.
- `fit_score` in the response is always the real score. A `rank_only` filter must **not**
  subtract from it. Ranking is adjusted through a separate sort key, never by writing a
  number the founder would read as the score.

If an implementer finds themselves mutating either field, the design is wrong — stop.

---

## 3. Schema — `founder_filter_settings`, in the shared revision `0003`

D5 owns `storage/migrations/versions/0003_provenance_identity.py` and has left a marked
block for this table. **Do not create `0004`.**

| column | type | notes |
|---|---|---|
| `filter_id` | `String(64)` | primary key |
| `enabled` | `Boolean` | not null |
| `mode` | `String(16)` | not null; `hide` \| `rank_only` \| `label_only` |
| `params_json` | `Text` | nullable |
| `updated_at` | `DateTime` | not null |

**Timezone hazard — read this.** FR-004 recorded that aware `datetime` objects written to
naive `TIMESTAMP` columns are silently shifted by the session timezone GUC. Follow whatever
`storage/models.py` already does for `MatchEvaluationRecord.evaluated_at` and be consistent
with it; do not introduce a third convention.

Defaults are **seeded by the migration**, so a fresh database behaves correctly with no
API call. The ten filters and their defaults:

| filter_id | source | enabled | mode |
|---|---|---|---|
| `geo_eligibility` | qualifier hard constraint | on | `label_only` |
| `work_mode_onsite` | qualifier hard constraint | on | `label_only` |
| `red_lines` | truth pack red lines | on | `hide` |
| `excluded_industries` | truth pack | on | `hide` |
| `track_preference` | `preference.track` order | on | `rank_only` |
| `target_roles` | `career.target_role` | on | `label_only` ¹ |
| `premium_fulltime_onsite` | D2 rule | on | `rank_only` |
| `stale_postings` | `is_stale` | on | `label_only` |
| `min_fit_score` | founder param | **off** | `hide` |
| `compensation_floor` | founder param | **off** | `rank_only` |

Only `red_lines` and `excluded_industries` hide by default. Everything else labels or ranks.

¹ **Amended after council review, and after this contract was first committed.** `target_roles`
was specified `rank_only` here and in the brief's §2 D3 table. Council 2 finding 4 showed that
with substring matching it demoted a fit-95 posting below a fit-30 one, because the rank
penalty is the leading sort key. The matcher was changed to token-set matching and the seeded
default moved to `label_only` until the predicate is proven against live data. `label_only` is
strictly more conservative than `rank_only` — it cannot reorder anything — so this narrows
behaviour rather than widening it. The change was ordered by the Master and is recorded in
`council-findings.md`; this table and the report were **not** updated at the time, which the
independent verifier caught as documentation-versus-behaviour drift in the very artefact meant
to pin behaviour. Corrected here. The brief's own table still reads `rank_only` and is an
Overseer-embedded decision (Appendix 1), so the Overseer should confirm or reverse this.

---

## 4. Mode semantics — exact

For each enabled filter, evaluate a predicate per opportunity. Then:

- **`hide`** — matching items get `filter_id` appended to `hidden_by`. They are **omitted**
  from `items` unless `include_hidden=true`. They are always counted in `hidden_count`.
- **`rank_only`** — matching items get `filter_id` appended to `flagged_by` and are demoted
  in sort order via a rank adjustment. `fit_score` is untouched.
- **`label_only`** — matching items get `filter_id` appended to `flagged_by`. No effect on
  visibility or order.
- **disabled** — the filter is not evaluated at all. It contributes to neither `hidden_by`
  nor `flagged_by`, and its `affected_count` is still reported (see §5) so the founder can
  see what turning it on would do.

**Sorting.** Keep the existing key (`fit_score` desc nulls last, `posted_date` desc, `id`)
and prepend a rank-adjustment term so demoted items sort after non-demoted ones at equal
score. Do not reorder within a demotion tier.

---

## 5. API

### `GET /api/filters`
```json
{
  "filters": [
    {
      "filter_id": "red_lines",
      "enabled": true,
      "mode": "hide",
      "params": {},
      "affected_count": 3,
      "description": "Opportunities matching a red line in your truth pack."
    }
  ]
}
```
`affected_count` is the number of opportunities the filter **currently matches**, computed
regardless of `enabled`, so the drawer can show what enabling it would do.

### `PUT /api/filters/{filter_id}`
Body: `{"enabled": bool, "mode": "hide"|"rank_only"|"label_only", "params": {...}}`
All three optional; absent keys are unchanged. Returns the single updated filter object.
An unknown `filter_id` is **404**. An invalid `mode` is **422**.

### `GET /api/opportunities`
New query param `include_hidden` (default `false`). Every item gains exactly two fields:
```
"hidden_by":  ["red_lines"],
"flagged_by": ["stale_postings", "target_roles"]
```
Both are always present, `[]` when empty — never `null`, never absent. The response object
gains `"hidden_count": <int>` alongside `total`.

**`total` semantics, stated because it is the A-13 assertion:** `total` is the number of
items **returned under the current visibility**. With `include_hidden=true`, `total` counts
everything. With all filters disabled and `include_hidden=true`, `total` **equals the
`opportunities` table row count**. That equality is the claim; make it true.

### `GET /api/dashboard/daily`
Each series entry gains `"hidden_by_filters": <int>`.

---

## 6. Web

A **Filters drawer** on the feed (`web/app/page.tsx`), not a new route — A-7 asserts the
route list stays `/` and `/login`.

Per filter row: an on/off switch, a mode selector, params where applicable, and the live
`affected_count`. Changing a toggle re-queries; **no page reload**.

Hidden items reachable through a **"Show N hidden"** control at the bottom of the feed,
where N is `hidden_count`. Each card shows chips for `flagged_by`.

Add the new types to `web/lib/contract/types.ts` first; the client in `web/lib/api/client.ts`
is the only place that touches the network and must stay that way.

**Mock phase and the switch back.** The web implementer may start against MSW. FR-004
recorded that the Master permitted a mock start and then never commissioned the switch, so
the smoke proved only that the UI agreed with fixtures it also controlled. **The switch to
the real API is part of this deliverable, not a follow-up**, and the Playwright filter-toggle
spec (A-8) must pass against the real stack before D3 is reported closed.

**No untracked env files.** FR-004 recorded a green that reproduced only on the Master's
machine because it needed a gitignored `web/.env.local`. Anything the tests need goes in
`playwright.config.ts` `webServer.env` or a tracked file.

---

## 7. Tests required

- Migration round-trip through `0003` (shared with D5).
- API: each filter's three modes, plus disabled.
- **The named A-13 test:** a red-line hit with `red_lines` toggled **off** is shown, still
  carries `red_lines` in `flagged_by`... — no. Read carefully: with the filter **off** it is
  not evaluated, so `flagged_by` is empty and the item is simply visible. What the test must
  assert is that its **`decision` is unchanged** from the toggled-on case. Assert all three:
  shown, `decision` identical, `fit_score` identical.
- All-filters-off + `include_hidden=true` → `total == SELECT count(*) FROM opportunities`.
- Defaults → hidden set is exactly the red-line and excluded-industry hits.
- Playwright: toggle one filter, assert the affected-count changes and the feed re-queries.
