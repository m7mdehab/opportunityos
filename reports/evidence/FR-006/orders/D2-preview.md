# Work order D2 — In-browser document preview

**Brief:** BRIEF-FR-006 §2 Track D node D2. **Wave:** 4. **Depends on:** D1 (integrated), C3 (drawer).
**Worktree/branch:** `wt/fr006-d2` **Test DB:** `opportunityos_test_d2` **Ports:** web `3101`, api `8101`.
**Turn budget:** 90. **Spend at most 10 turns reading before you write your first file.**

**First action:** `git merge --no-edit feat/brief-fr-006-nothing-missed` from your worktree root.

## Deliverable text (verbatim from the brief)

> **D2 — In-browser preview.**
> - `GET /api/opportunities/{id}/artifacts/cv.pdf` streams inline
>   (`Content-Disposition: inline`); the drawer's artifacts panel shows the PDF in an embedded
>   viewer with template switcher and download buttons for PDF/DOCX; generation cached per
>   (opportunity, truth-pack hash, template) in `0004` so re-opening is instant.
> - **Acceptance:** Playwright opens a card, sees the PDF preview render, switches template,
>   downloads DOCX.

## Facts established by the Master — do not re-derive

- Existing artifact routes: `GET /opportunities/{id}/artifacts/cv.docx` and
  `/artifacts/cover-letter.docx` (`api/routes_api.py:606,611`), media type
  `application/vnd.openxmlformats-officedocument.wordprocessingml.document`,
  `Content-Disposition: attachment; filename="..."`.
- **Migration `0004_founder_control` already exists** (work order A1) with the `artifact_cache`
  table: `cache_key` PK, `opportunity_id`, `truth_pack_hash`, `template_id`, `artifact_kind`,
  `content_type`, `payload`, `created_at`. **Do not write a migration.**
- Work order D1 built the document model, the three templates (*Classic*, *Compact*, *Modern*),
  and the reportlab PDF path in `matching/binary_export.py`. **You do not change how a document
  is produced** — you add routes, a cache, and a viewer.
- The truth-lock applies to every byte you serve. Artifact generation validates claims through
  `matching/artifact_validation.py`; a rejected claim is a **409 with the claim and the reason**,
  and that is correct behaviour, not an error to smooth over. A cache must never serve a document
  whose claims were not validated.
- `web/lib/api/client.ts` is the single fetch wrapper. Routes stay `/` and `/login`.

## Required behaviour

1. **PDF routes**: `cv.pdf` and `cover-letter.pdf`, `Content-Type: application/pdf`,
   **`Content-Disposition: inline`** for preview and a download variant for saving. DOCX routes
   keep `attachment`.
2. **A `template` parameter** on every artifact route, defaulting to *Classic*, validated against
   the three committed templates — an unknown template is a 422, never a fallback that silently
   serves a different document than the founder asked for.
3. **The cache**, keyed on **(opportunity_id, truth_pack_hash, template_id, artifact_kind)**:
   - a hit returns the stored bytes;
   - **a changed truth-pack hash invalidates**, asserted by a test that changes the hash and
     shows a regeneration;
   - a 409 (validation rejection) is **never cached** — assert this, because caching a rejection
     would make the truth-lock's answer stale the moment the founder fixes their pack;
   - eviction or size bounds are stated, whatever you choose.
4. **The artifacts panel** in the drawer: embedded PDF viewer, template switcher, download buttons
   for PDF and DOCX, and a visible rendering of D1's **"what was left out and why"** panel. When
   the API returns 409, the panel shows the claim and the reason in plain language — the founder
   must be able to see *which sentence* could not be supported.
5. Playwright: open a card, see the preview render, switch template and see it change, download
   DOCX. Assert the rendered result, not just the absence of an error.

## Allowed files

`api/routes_api.py` (artifact routes only) · `api/artifact_cache.py` (new) · `api/settings.py` ·
`api/test_api.py` and new tests · `storage/repository.py`,
`storage/test_postgres_integration.py` (the cache table only) · `web/**` ·
`reports/evidence/FR-006/d2-run.md`.

## Frozen — touching any of these is a FAIL

Any migration · `storage/models.py` · `matching/**` (D1 owns document production; if a document
is wrong, report it — do not fix it here) · **`truth/**`**, and `truth/validator.py` most of all ·
`api/facets.py`, `api/search.py`, `api/filters.py`, `api/saved_views.py` · `opportunity/**` ·
`worker/**` · `private/`.

## Acceptance rows — paste raw output for each

| # | Command | Expected |
|---|---|---|
| D2.1 | `py -3.12 -m unittest discover -s api -p "test_*.py" and py -3.12 -m unittest discover -s storage -p "test_*.py" -v` | `OK`, counts stated |
| D2.2 | `curl -i` on `cv.pdf` | `200`, `Content-Type: application/pdf`, **`Content-Disposition: inline`**, body starts `%PDF` |
| D2.3 | the template-parameter tests | each of the three templates returns a **different** document; an unknown template returns **422**, not a fallback |
| D2.4 | the cache tests | miss → hit; a changed truth-pack hash → regeneration; the cache key printed for each case |
| D2.5 | the 409-not-cached test | a rejected claim returns 409, is not stored, and a later fixed pack regenerates |
| D2.6 | `npx playwright test` in `web/` | all specs pass, count **> 0**; the preview spec asserts the PDF rendered, the template switch changed it, and the DOCX downloaded |
| D2.7 | `npm run build` and `npm run lint` in `web/` | exit 0; route list still **`/` and `/login` only**; lint clean after a Playwright run |

Paste raw output. Never make a document generate by changing what validates.
