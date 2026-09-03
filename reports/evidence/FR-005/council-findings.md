# Council reviews — BRIEF-FR-005

Two independent reviews, as §2 requires: D1 (validator semantics) and D3+D5 (migration `0003`
and the filter engine). Neither reviewer implemented what it reviewed. Both were given the
requirement text and told to attack it, and both produced live probes rather than opinions.

Neither returned a BLOCKER. Both returned findings that materially changed the shipped code.

---

## Council 1 — D1, validator semantics

**Verdict: the 409 → 200 change is LEGITIMATE.** Guard 8 (relational composition) is intact
and still reachable; no evidence record, template or fixture was edited; no §9 violation.

The reviewer also supplied the argument that settles *why* it is legitimate, which the
implementer had not articulated: through the production path, every founder value the
compiler interpolates is already verified against its evidence by
`TruthGraph._is_value_supported_by_evidence` at ingest, before the validator runs. So guard 9
was, in practice, only ever rejecting the *compiler's own vocabulary*. FR-004's 409s were
false positives, not protection being lost.

| # | Severity | Finding |
|---|---|---|
| 1 | MAJOR | `opportunity_terms` applied to **every** claim, not just the one embedding opportunity fields — and sourced from scraped third-party text |
| 2 | MAJOR | `truth/connective_terms.txt` listed `professional`, `position`, `team`, `hiring`, `manager`, `time` — all title-bearing |
| 3 | MAJOR | The requirement's "admissible **when the claim cites that provenance**" was asserted in the ADR but never implemented |
| 4 | MAJOR | The 16 e2e tests are positive-only, stay green under a neutralised guard 9, and their claim-coverage assertion is tautological |
| 5 | MINOR | `validate_narrative` has no structural tripwire: a NARRATIVE claim carrying evidence ids is silently accepted |
| 6 | MINOR | A metric whose `context` ends in a full stop 409s the CV — the founder's own pack is exposed |
| 7 | MINOR | ADR-0014 oversells the residual protection |
| 8 | NIT | The HTTP tripwire rejects at guard 5, not guard 9, so its docstring overstates what it proves |

Findings 1 and 2 were **reproduced by the Master independently** before any repair was
ordered — see `council-d1-probe.txt`. All seven were routed back to the D1 implementer.

---

## Council 2 — D3 + D5

**Verdict: D5 accept. D3 accept with repairs.**

On D5 the reviewer confirmed by probe across all nine adapter fixtures that the chosen tuple
is unique, that the dedup keeps exactly the lowest id per tuple, that `downgrade()` leaves a
working schema, and that re-upgrade re-seeds correctly. It also verified the concurrency and
failure behaviour the Master had only reasoned about: a failed merge rolls the DELETE back in
the same transaction, and two concurrent writers resolve last-writer-wins with no
accumulation.

On D3 it confirmed the governing invariant holds on every path — `decision` and `fit_score`
pass straight through, and `rank_only` is a pure sort-key prefix that never touches the score.

| # | Severity | Finding |
|---|---|---|
| 1 | MAJOR | A malformed `params` value is **committed** and then 500s every feed and filter request until fixed by raw HTTP — the drawer cannot load to repair itself |
| 2 | MAJOR | `stale_postings` is a guaranteed silent no-op: nothing outside tests ever writes `is_stale=True` |
| 3 | MAJOR | Three default-on `rank_only` filters are inert on any pack lacking the matching assertion, with no way for the founder to tell "0 matches" from "no data source" |
| 4 | MAJOR | `target_roles` substring matching demotes a fit-95 posting below a fit-30 one on a string-containment accident |
| 5 | MINOR | `record_checksum` hashes the whole raw record, so the constraint is effectively `(opportunity_id, field_name)`; the repository DELETE is the load-bearing part |
| 6 | MINOR | `synchronize_session=False` can leave stale identity-map objects (observed `SAWarning`) |
| 7 | MINOR | `compensation_floor` compares amounts across different intervals |
| 8 | MINOR | `premium_fulltime_onsite` couples to the scorer's prose wording |
| 9 | MINOR | `excluded_industries` substring match hides "Pharmaceuticals" for an excluded "Arms" — and it hides by default |
| 10 | MINOR | The backup round-trip test asserts nothing about the new table |
| 11 | MINOR | Nothing warns a developer whose database was stamped at the earlier `0003` |
| 12–15 | NIT | Dedup verified correct; `total` semantics hold generally; per-row query counts; red lines as a hide default |

Findings 2 and 3 are the ones that matter most, and they are the same defect wearing two
faces: **a control that silently does nothing while telling the founder it is protecting
them.** The founder's stated requirement was that nothing filters opportunities out of view
without a visible, switchable control. A control that is visible, switchable, and inert
breaks that requirement more quietly than a missing one would. The repair adds an
`unavailable_reason` to the API and surfaces it in the drawer rather than letting a zero
count speak for itself.

---

## Dispositions

Routed for repair: council 1 findings 1–7; council 2 findings 1–4, 5 (documentation), 7–11.

Recorded, not fixed, with reasons in the report:
- **`is_stale` is never computed in production.** The reverifier exists and returns results
  that no worker persists. Wiring it up is a new deliverable, not a repair; the filter is
  marked unavailable instead of being made to look functional.
- **`record_checksum` does no discriminating work.** Harmless today because no adapter emits
  a `field_name` twice, but an adapter that ever emits per-item provenance rows would hit an
  `IntegrityError`. The contract is documented rather than the schema changed.
- Council 2 findings 13–15 (performance and defaults) are alpha-scale acceptable.

---

## Master's independent verification of council 2, finding 2

The claim that `stale_postings` can never match was strong enough to act on only after
checking it directly:

```
$ grep -rn "is_stale" --include=*.py . | grep -v test
api/routes_api.py:313          "is_stale": bool(opp.is_stale),        # read
api/routes_api.py:450          "is_stale": bool(opp.is_stale),        # read
opportunity/persistence.py:192 opp_data = _build_opp_data(opp, is_stale=False)   # write: always False
opportunity/persistence.py:206 opp_data = _build_opp_data(opp, is_stale=False)   # write: always False
opportunity/reverification.py:18,25  "is_stale": status_code in (404, 410)       # COMPUTED, never persisted
scripts/backup_restore.py:209  "is_stale": opp.is_stale,              # dump/restore
```

`opportunity/reverification.py` computes staleness correctly and returns it. Nothing in
`worker/`, `api/` or `scripts/` ever calls it — a grep for `reverif` across those trees
returns only a filter description string, a serialization field, and backup/restore. So every
production write sets `is_stale=False` and the column never becomes true.

Two consequences worth stating plainly:
- The `stale_postings` filter is inert in production, exactly as the council found.
- The FR-004 web UI already renders a "Stale" badge, and the MSW fixtures exercise it. The
  mock therefore displays a state the real system cannot currently produce. The screenshot in
  `d7-feed-1280.png` shows that badge; it is honest about being synthetic data, but it is not
  a preview of anything the founder will see until a worker persists reverification results.

Recorded, not fixed. Wiring the reverifier into a worker job is a new deliverable, not a
repair, and inventing a staleness signal to make the filter look alive would be the same
class of dishonesty this brief exists to remove.
