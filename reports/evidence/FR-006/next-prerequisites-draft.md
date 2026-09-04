# §10 draft — next-phase prerequisites

Ordered by what most limits the founder, not by effort.

## 1. Nothing new reaches the feed yet

Source breadth is the brief's largest miss and it has three separable causes, all fixable:

- **36 registered Greenhouse/Lever boards have no adapter bound**, so the scheduler enqueues polls
  that record `Unregistered adapter` and fetch nothing. Derive the adapter bindings from the
  read-allowed registry entries instead of a hard-coded list and the 36 become live in one change.
  (Council #4, finding 12.)
- **Hacker News needs one wiring step.** Its fetch path is now correctly policed, but the bound
  adapter's `feed_url` points at the `whoishiring` user object rather than the thread, so it yields
  0 rows.
- **The board sweep stopped on a time budget, not on seeds** — 1,057 of 1,759 candidates remain and
  resume from a progress file. 651 of 702 probes were 404s because the seed directory supplies
  company names and an ATS board token is usually not the company slug. A better seed source is
  worth more than a longer sweep.

## 2. Extraction is the ceiling on qualification quality

Work-mode coverage is **52.2%** against a 90% target, and **47.8% of postings carry no signal at
all** — not a parsing failure, an absence. The remaining headroom is in the adapters that do have
native fields, not in more inference rules. Inference already supplies 30.6% and every additional
rule trades precision for coverage on text that genuinely does not say.

## 3. The title taxonomy needs a different kind of input

**86.9%** of corpus titles map to a family, up from 20.6%. The residual is trades, cross-functional
executive titles, and genuinely ambiguous ones. Reaching 95% by hand-adding patterns will start
producing confident wrong answers; this is the point to stop growing the YAML.

## 4. Two artifact validators

`truth/validator.py` is the production authority; `matching/validator.py` is a legacy shim with a
static predicate whitelist, and it is **the only gate on the outbound path**
(`outbound/authority.py`, `outbound/artifact_selector.py`). This brief hit it twice: once when new
predicates broke it, once when a cover letter cited an entity id it could not resolve. It has real
callers so it cannot simply be deleted. Unify or retire it deliberately, with an ADR.

## 5. `stale_postings` has a writer that nothing calls

`StaleOpportunityReverifier.reverify_stale_opportunities` exists and is tested — the first code in
the project's history to set `is_stale = True`. No entrypoint or scheduler hook invokes it, so the
filter is still inert in the running product.

## 6. The `identity.phone` false positive

`truth/validator.py` parses a leading `+20` as a "20 count" metric and demands a `MetricAssertion`,
so the phone is dropped from every document. The fix belongs in
`_parse_structured_metrics_with_context` — excuse digit runs that are part of a phone-shaped token
— behind its own ADR and a regression test. It is a small change to a file that must never be
changed casually.

Related: `matching/document_model.py` keeps two "defensive mirror" copies of the validator's
regexes. A test now asserts they agree, but the duplication itself should go.

## 7. The gold set under-specifies every honest dimension

It regressed twice in this brief for the same reason: the shared `create_test_graph()` fixture
lacked the evidence each newly-honest dimension needed — first employment dates, then skill
proficiency. Its remaining flat assertions (`work_authorization.jurisdiction`, `language.language`,
`service.name`, the responsibility strings) have the same shape. Rebuild it against the real
corpus rather than patching it a third time.

## 8. Process, for the next brief

- **The concurrency cap of four is a hardware constraint, not a guideline.** Exceeding it made the
  host unusable: `psql` timing out at two minutes, `git merge` at seven, a stale `index.lock`
  blocking every operation, and one agent's database dropped underneath it by another's cleanup.
- **Work orders must be sized to the harness's real 60-turn cap**, not the protocol's 90. Every
  implementer in this brief exhausted its budget; several landed nothing on the first pass.
- **Route every scope change through a committed work order file.** Three agents treated
  harness `system-reminder` blocks as injection attempts and two refused legitimate instructions.
  The order file was never once refused.
- **Partition orders by seam, not by layer.** Five orders each did their layer correctly and left
  `api/serialization.py` in nobody's allowed list, which is why the founder's original complaint
  survived until the web work order tripped over it.
- The readiness matrix's F4 targets (`1B/1H/2A/2B/2C/3C/3E/1G`) resolve to nothing in the
  repository. Name them by `req_id`.

## 9. The `api` suite cannot be run in isolation

`py -3.12 -m unittest discover -s api -t . -p "test_*.py"` hangs indefinitely. `pg_stat_activity`
shows a session **idle in transaction** holding `SELECT ... FROM match_evaluations` while other
backends block on `TRUNCATE TABLE "match_evaluations" CASCADE` with `wait_event_type = Lock`. The
full suite passes 1039 with zero failures because its ordering differs, so this is latent rather
than breaking — but a suite that cannot be run alone cannot be bisected, and bisection is what you
need on the day something breaks. Find the test that leaves the transaction open and close it.
