# A-6 — scope diff, observed against the set written in advance

`git diff --name-only main...HEAD` → **83 paths, as of the final source commit**.
(The Master first wrote 82; the verifier read 83. The number moves with every commit, which is
exactly why it is now stated against a fixed head rather than left bare in prose.)
Expected set: `reports/evidence/FR-005/a6-expected-scope.md`, committed at `dc8badc`, before
any implementer had reported.

## Verdict: NOT_CLOSED

**8 of the 83 paths lie outside the expected set.** The rule this row exists to enforce is
that a larger observed set is `NOT_CLOSED` and is never retro-fitted, so the expected set has
not been edited to admit them. FR-004 failed exactly this row, marked it PASS, and the
verifier's objection — that doing so "retro-fits the expected result to the observation,
which is the one thing a claim ledger exists to prevent" — is the reason this row is written
the way it is.

Every one of the eight has a traceable authorisation. None is an undisclosed widening. But
"authorised" and "expected" are different claims, and only the second is what A-6 tests.

| path | authorised by | why the Master's expected set missed it |
|---|---|---|
| `docs/templates/alpha.env.template` | the **superseded draft** brief's D2, which v1.1's header maps onto v1.1's D4 — **not** v1.1's own text | The Master originally cited this as "the brief itself, §2 D4". The independent verifier checked and that string does not appear in `briefs/BRIEF-FR-005.md` at all; it is in the draft at `5efedf7`. The authorisation is substantively real — v1.1 D4 requires the `_test` refusal that the template documents — but the citation as written was **false about the governing document**, and is corrected here rather than quietly dropped. |
| `api/filters.py` | the Master's own D3 prompt — "a new module for the filter engine, e.g. `matching/filters.py` or `api/filters.py` — you choose" | The expected set was written before the D3 prompt, and was not revisited when the prompt authorised a file the set did not name. |
| `matching/artifact_validation.py` | the Master, explicitly, in the council-repair instruction for D1 defect 4b | Created mid-brief on Master instruction; the set predates the council review. |
| `matching/mapping.py` | the Master, explicitly — recorded as deviation 8 | Scope extension decided after the set was written. |
| `matching/models.py` | D3-API, declared in its report — one optional field, `signal_tags: tuple[str, ...] = ()` | The set named this file in its "must not appear" section, but scoped to D1's narrative-segment question. D1 did **not** touch it; D3-API did, for an unrelated reason, and declared it. The set's prohibition was more specific than its wording. |
| `matching/evaluate_persist.py` | D3-API, declared — serialises the new `signal_tags` field | Consequence of the above; not anticipated. |
| `scripts/backup_restore.py` | D3-API, declared — recorded as deviation 12 | Adding a table to `Base.metadata` trips the BRIEF-FR-003 backup-completeness invariant. A genuine cascade the Master did not foresee. |
| `scripts/test_backup_restore.py` | same cascade, plus council 2 finding 10 | As above. |

## The half that is clean, and matters more

The expected set's §6 lists paths whose appearance would itself be a finding. **None of them
appears:**

- `truth/graph.py`, `truth/models.py` — BRIEF-002 semantics, frozen. D2's fix direction was
  one-way and stayed that way: `matching/` was changed to read what the graph emits, not the
  reverse.
- `truth/ingest.py` — the relation-ordering defect is real and was left alone.
- `0001_baseline_schema.py`, `0002_match_evaluations.py` — released revisions, untouched.
- No `0004_*` migration exists; D3 and D5 share one `0003` as required.
- `docs/MASTER_PLAN.md`, `docs/PRODUCT_CONSTITUTION.md` — §0 non-goal, untouched.
- `AGENTS.md`, `CLAUDE.md` — untouched. A branch under review did not widen its own authority,
  which is the specific thing the FR-004 review flagged about that brief's Addendum.
- **Zero paths under `private/`.**

## What the Master would do differently

The expected set should be re-derived whenever a deliverable prompt authorises a file the set
does not name — three of the eight (`api/filters.py`, `matching/artifact_validation.py`,
`matching/mapping.py`) were authorised by the Master's own later instructions and could have
been added to the set at that moment, in advance of the observation, without weakening the
claim at all. Amending an expected set *before* the work is honest; amending it after is the
thing being guarded against. This brief did neither, and so records NOT_CLOSED.
