# REPORT-FR-005 — Truthful Documents, Honest Scores, Founder-Controlled Filters

**Date:** 2026-09-03
**Brief:** `briefs/BRIEF-FR-005.md` v1.1
**Master:** Claude Code main session, model `opus`
**Branch:** `feat/brief-fr-005-truthful-documents`
**Starting `main`:** `b563102`

---

## 1. What this brief was for

FR-004 built the product surface and, in building it, exposed three defects that fixtures had
been hiding. This brief fixed them and added one thing the founder asked for after seeing the
product.

The single sentence that matters: **tailored documents now generate.** Under FR-004 the CV
and cover-letter routes returned HTTP 409 for every realistic truth pack — "always, by
construction", as that report put it. Both now return a real DOCX, for both test packs, and
the guard that was refusing them is still refusing the things it should.

---

## 2. Status

*(completed at the gate — see §4 and the Decision)*

---

## 3. Deliverables

### D1 — Documents that generate (ADR-0014)
Compilers emit atomic, evidence-bound claims; prose that joins two facts becomes two claims,
and connective text becomes a `NARRATIVE` segment rather than a claim. The validator
classifies claim text into three term classes before material-term extraction, and only
founder-claim terms can reject.

The mechanism matters more than the description. Guard 9 is a **set subtraction**, not a
bypass:

```python
uncovered = tokens(claim) - evidence_tokens - _NON_MATERIAL_WORDS - admissible_non_founder_terms
```

A token is excused only if it is literally a member of the committed connective list or
literally a token of the opportunity's own organization/title. Guard 8 — the relational
composition guard — was **not** relaxed; atomic claims are what stop tripping it.

`docs/adr/ADR-0014-claim-classes.md` records the classification and what protection is given
up. Owner: implementer. Council: reviewed, four MAJOR findings, all repaired.

### D2 — Scores that see the founder (ADR-0015)
`truth/predicates.py` is a committed registry of all **72** predicates the engine knows: 62
PROJECTED from a profile field, 10 ASSERTION_ONLY from the pack's `assertions:` section.
`matching/` imports every name from it and spells none itself, and a contract test globs
every non-test file in `matching/` so a new file cannot silently reintroduce an orphan.

Eighteen orphan spellings were removed. The one that mattered:
`responsibility_scope` read `responsibility.item`, `employment.role_description`,
`experience.summary` and `achievement.description` against a graph that emits
`employment.responsibility` and `achievement.statement`. For an employment-only founder the
only non-orphan in that list was `service.name`, which belongs to the independent track — so
the dimension returned a flat **0.500 with zero evidence references for every founder**, and
had done since BRIEF-004. It now returns **0.800 with two references** on the corrected
fixture. At weight 0.15 that is roughly 4.5 points of overall fit score that were unreachable
no matter what a founder's history contained.

The full predicate table is in `reports/evidence/FR-005/predicate-contract-table.md`.

### D3 — Founder-controlled filters
Ten named filters, seeded by migration `0003` so a fresh database behaves correctly before
any API call. `GET /api/filters`, `PUT /api/filters/{id}`, `include_hidden` on the feed,
`hidden_by`/`flagged_by` on every item, `hidden_by_filters` on the daily series, and a
Filters drawer grouped by live effect — hiding, ranking, labelling, off, unavailable.

**Only two filters hide by default**: the founder's own red lines and excluded industries.
Everything else labels or ranks. And the governing rule, which the council verified on every
path: *a toggle changes whether a row is hidden, ranked, or merely labelled; it never changes
`decision` and it never changes `fit_score`.* `rank_only` demotes by prepending an integer to
the sort key, leaving the score the founder reads untouched — a demoted score displayed as
the real score would be a lie.

The council found four of the ten could be permanently inert while the drawer displayed them
as protecting the founder. They now carry an `unavailable_reason`, render in their own
section with the reason shown, and have their affected-count suppressed rather than displayed
as a misleading `0`.

### D4 — `alpha.py` gets a database of its own
Targets `opportunityos_alpha`, creates it when absent, prints which database it is using on
every run, and **refuses any URL whose database name ends in `_test`** — before PostgreSQL
detection, before migrations, before any server starts. The refusal lives in
`load_alpha_env`, so no caller can forget it; `down` and `logs` are deliberately exempt
because neither resolves the URL, and that exemption is asserted with `inspect.signature`
rather than left as a comment.

The implementer proved the ordering by mocking the only function that opens a connection and
asserting it is never called — stronger than a log check, and stronger than what was asked
for.

### D5 — `field_provenances` natural identity
Unique constraint on `(opportunity_id, field_name, record_checksum)` in migration `0003`.
The brief named `source_locator`; no such column exists, and the analogous `raw_pointer` is
nullable, which makes it useless in a PostgreSQL unique constraint because NULLs never
collide. The substitute is all-`NOT NULL` and was verified unique against a real
`persist_batch` run before being built on.

A unique constraint alone would only turn a duplicate into an `IntegrityError`, which is a
crash rather than idempotency, so `storage/repository.py` deletes an opportunity's existing
provenance rows in the same transaction before merging the fresh set. Case U now asserts the
row count is unchanged after run 2 **and** after run 3, where run 3 is a changed posting
under the same identity. FR-004 asserted only that the count exceeded zero after run 1, which
is why the duplication was never caught.

### D6 — The FR-004 erratum
Discharged, but not as the brief assumed. §2 D6 says the erratum "was merged before this
brief started" and told pre-flight to verify it. It was not on `main`: that branch was never
merged because `gh` lost its authentication. This branch therefore **carries** the erratum
rather than verifying it, and adds the sentence the brief asked for, recording the D2
scorer-vocabulary defect as a second latent BRIEF-004 finding.

### D7 — Founder acceptance packet
§9 below.

### D8 — Matrix, STATE, report, evidence, merge
This report, the regenerated matrix, and the evidence under `reports/evidence/FR-005/`.

---

## 4. Test evidence

*(completed at the gate)*

---

## 5. Claim ledger

*(completed at the gate)*

---

## 6. Council findings

Two independent reviews, neither by an agent that implemented what it reviewed. Neither
returned a BLOCKER; both changed the shipped code. Full detail in
`reports/evidence/FR-005/council-findings.md`.

**Council 1 — D1, validator semantics. Verdict: the 409 → 200 change is legitimate.**
Guard 8 intact, no evidence record or template edited, no §9 violation. The reviewer also
supplied the argument that settles *why* it is legitimate, which the implementer had not
articulated: through the production path, every founder value the compiler interpolates is
already verified against its evidence at ingest, before the validator runs. Guard 9 was, in
practice, only ever rejecting the compiler's own vocabulary — FR-004's 409s were false
positives, not protection being lost.

It then found that guard 9 had nonetheless stopped being an *independent* check, and proved
it with a probe the Master reproduced before ordering any repair:

> A claim asserting the founder is a "Senior Data Engineer, Kubernetes certified" against
> evidence saying only "Data Engineer" is correctly **rejected**. The same claim is
> **accepted** when the job posting happens to be titled "Senior Engineering Manager" at
> "Kubernetes Certified Systems Group".

Because `opportunity_terms` was built from the posting's organization and title — scraped
third-party text the founder does not control — and applied to *every* claim, including CV
skill and metric claims that embed no opportunity field at all. A second probe showed
`professional` and `manager` on the connective stop-list let "Professional background: Data
Engineer Manager." through.

**Council 2 — D3 and D5. Verdict: D5 accept; D3 accept with repairs.**
On D5 it verified by probe across all nine adapter fixtures that the chosen tuple is unique,
that the dedup keeps exactly the lowest id per tuple, that `downgrade()` leaves a working
schema, and — going beyond what was asked — that a failed merge rolls the DELETE back in the
same transaction and that two concurrent writers resolve last-writer-wins with no
accumulation.

Its two most important D3 findings are the same defect wearing two faces: **a control that
silently does nothing while telling the founder it is protecting them.** `stale_postings` can
never match, because nothing outside tests ever writes `is_stale=True` — the Master confirmed
this independently. Three more (`track_preference`, `target_roles`,
`premium_fulltime_onsite`) are inert on any pack lacking the matching assertion, and the
shipped template has `assertions: []`. The founder's stated requirement is that nothing
filters opportunities out of view without a visible, switchable control; a control that is
visible, switchable and inert breaks that requirement more quietly than a missing one would.

It also found a genuine availability bug: a malformed `params` value was **committed** and
then 500'd every feed and filter request, so the drawer could not load to repair itself.

---

## 7. Requirement delta and the predicate contract

*(matrix figures completed at the gate)*

The predicate contract table required by §10 is generated from the registry and lives at
`reports/evidence/FR-005/predicate-contract-table.md`: 72 predicates, 62 PROJECTED, 10
ASSERTION_ONLY. The ASSERTION_ONLY list is the interesting half — those are exactly the
predicates that return nothing when a founder's pack omits them, which is the root of the
council finding that three default-on filters can be permanently inert.

---

## 8. Deviations

Twenty recorded, maintained as they happened rather than reconstructed at the end, in
`reports/evidence/FR-005/deviations.md`. Four are the Master's own errors, and they are worth
naming here rather than leaving in an appendix:

- **The Master destroyed a live implementer's session.** While clearing a stale harness
  worktree it removed a branch belonging to the still-running D5 implementer, making it
  unresumable. D5's work was complete on disk but uncommitted; the Master re-ran its full
  acceptance against the unmodified working tree and committed it verbatim, changing nothing
  to make it pass. D5 is the one deliverable whose final verification was not run by its own
  implementer.
- **The dead agent's connections then blocked the Master's own migration round-trip** for ten
  minutes before the lock contention was diagnosed — a second instance of the FR-004 lesson
  about shared database state.
- **Two agents were run against one invariant with no reconciliation step planned.** D2
  recorded an orphan predicate in a file D1 was concurrently fixing; the allowlist assertion
  failed at integration. The mechanism worked exactly as designed — the deviation is that the
  Master did not plan for it.
- **The A-6 expected set did not anticipate the backup-completeness cascade.** Adding a table
  to `Base.metadata` trips an invariant from BRIEF-FR-003, so `scripts/backup_restore.py`
  necessarily changed. It is outside the set the Master wrote in advance, and the set was not
  edited to admit it.

One non-error worth surfacing: an implementer flagged a legitimate harness directive as
prompt injection, refused it, and said so in its report. It was wrong on the facts, but the
reasoning was sound and the cost was zero. That is the behaviour this project wants when an
agent cannot tell a real instruction from an injected one.

---

## 9. Founder acceptance packet

*(the packet, from `reports/evidence/FR-005/d7-founder-packet-draft.md`, is reproduced at the
gate)*

---

## 10. Next phase prerequisites

*(completed at the gate)*

---

## Decision

*(completed at the gate)*
