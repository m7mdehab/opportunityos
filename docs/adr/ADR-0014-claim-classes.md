# ADR-0014 — Claim Classes: Atomic Founder Claims and Narrative Segments

- **Status:** Accepted
- **Date:** 2026-09-03
- **Phase:** BRIEF-FR-005 D1
- **Supersedes:** none
- **Superseded by:** none

## Context

STATE.md recorded, at the close of BRIEF-FR-004, that the tailored-document
feature did not work for a naturally-written truth pack. Two guards in
`truth/validator.py::ClaimValidator.validate_claim` stacked against every
realistic pack:

- **Guard 8 (relational composition):** a claim citing more than one
  evidence record is refused unless those records are relationally linked
  in the graph.
- **Guard 9 (material lexical coverage):** a claim is refused if it
  contains any word not present in its cited evidence, after subtracting a
  ~55-word list of function words (`_NON_MATERIAL_WORDS`).

Against the shipped synthetic template, the CV rejected 1 of 3 claim shapes
and the cover letter rejected 2 of 2, and the cover letter was structurally
unsatisfiable: it names the target role and employer, which by definition
cannot appear in the founder's own evidence. A prior attempt at this fix was
stopped mid-brief because it edited the founder's evidence to contain
compiler vocabulary — see the "wrong resolution" note this ADR's Decision
explicitly does not repeat.

The defect had two independent causes, and both needed fixing:

1. **The compiler emitted composite prose.** `matching/compiler_employment.py`'s
   professional-summary claim joined the founder's title (one evidence
   record) with up to three skill names (each its own, unrelated evidence
   record) into one sentence and one `GeneratedClaim`. The cover letter's
   introduction and body claims did the same with title evidence plus
   connective prose plus the literal target role/employer name. None of
   that combination was ever relationally linked in the graph, and none of
   it should have needed to be: a CV/cover letter is naturally made of
   several distinct statements, not one fused sentence.
2. **The validator had no notion of a term that is true without being a
   founder fact.** A greeting, a closing, or a sentence naming the
   employer the document is addressed to are not claims about the founder
   that require evidentiary backing at all; there was no way to tell the
   validator that.

**This ADR was revised once, after independent council review, before D1
closed.** The first shipped revision introduced a second admissibility
class — "opportunity-provenanced terms" — that an independent review found
applied too broadly and was driven by uncontrolled, scraped input. That
class has been **removed entirely**, not narrowed. The record of that
finding and why the fix is a removal rather than a patch is in "Residual
exposure and review history" below; the Decision, Consequences, and
Alternatives sections describe only the mechanism actually shipped.

## Decision

Every generated claim is classified before compilation, and the validator
recognizes two term classes when it checks a claim's lexical coverage.

### 1. Atomic claims, one founder fact each

`matching/compiler_employment.py` and `matching/compiler_independent.py` no
longer emit a claim that combines evidence from more than one unrelated
subject. Where the previous version joined title + skills into one
composite sentence, the compiler now emits one atomic claim for the title
and lets the (already-separate) per-skill claims in the Technical Skills /
Alignment sections carry the skills — each citing only its own evidence.
Where a claim genuinely needs to combine evidence from the same underlying
fact (e.g. an employment record's title, organization, and dates, which
share one `EmploymentRecord` entity and are therefore relationally linked in
the graph via `TruthGraph.are_relationally_linked`), it stays one claim,
because guard 8 is unchanged and a real relation is cited. **No claim is
ever emitted without a relation to cite for a composite; the fix is that the
compiler stopped generating composites that had none, not that the guard
was relaxed.**

A founder-specific claim's own wording is now deliberately minimal — e.g.
the CV summary claim is `"Background: {title}."`, not `"Professional
background: {title}."` — specifically so it needs as little help from any
admissibility list as possible; see §3 below for why.

### 2. Narrative segments

Connective prose that asserts no founder-specific fact, and no
opportunity-specific fact that depends on a founder value either — a
greeting ("I am writing to express my interest in the following
opportunity."), or a sentence that names only the target role/employer
("Applying for the {opportunity title} role at {opportunity organization}.")
— is emitted as a `GeneratedClaim` with `policy_source="NARRATIVE"` (the
field already existed on `matching/models.GeneratedClaim`; no new field was
added, and `matching/models.py` was not touched for this purpose — see
"Alternatives considered"). `ClaimValidator` gains one new method,
`validate_narrative`, which:

1. **Rejects the claim outright if it carries `assertion_ids`,
   `evidence_ids`, or a non-empty `authorized_value`.** Those fields mark a
   `GeneratedClaim` as an evidence-backed founder fact; a claim tagged
   `NARRATIVE` must not also claim to be one. This is a structural
   tripwire, not a convention: `matching.artifact_validation.validate_artifact_claims`
   (the shared dispatcher — see §4) always passes a narrative claim's own
   `assertion_ids`/`evidence_ids`/`authorized_value` into this check, so a
   compiler bug that tags a real founder-fact claim `NARRATIVE` is caught
   here, not silently accepted.
2. **Rejects the claim outright if its text contains a parseable metric**
   (reusing the same numeric-token parser guard 11 uses). A real number
   reads as a quantified fact; it belongs in an evidence-checked,
   metric-provenance-verified claim, never in text this method does not
   check evidence for.
3. Otherwise runs only the two guards that do not depend on evidence —
   Never-Claim/red-line prohibition and the planned-credential guard — on
   the full narrative text, exactly as `validate_claim` runs them on claim
   text.

It does not run the evidence-coverage, relational-composition, or
metric-provenance guards, because a sentence that makes no evidentiary claim
about the founder cannot meaningfully be measured against evidence coverage.
`api/routes_api.py`'s `_compile_and_export`, `matching/test_artifacts_e2e.py`,
and `matching/test_compiler.py` all dispatch through the single shared
function `matching.artifact_validation.validate_artifact_claims` (see §4),
which chooses `validate_narrative` vs. `validate_claim` based on
`claim.policy_source == "NARRATIVE"`.

The compiler is still responsible for the primary classification — routing
a genuinely fact-free sentence through `NARRATIVE` in the first place — but
`validate_narrative`'s two structural checks above mean a classification
mistake (tagging a real founder-fact claim `NARRATIVE`) is now caught by
the validator itself, not only by code review of the compiler.

### 3. Two term classes for guard 9

Guard 9 (material lexical coverage, `validate_claim` step 9) excuses one
additional term class from the "uncovered material term" rejection, on top
of the unchanged `_NON_MATERIAL_WORDS`:

- **(a) Founder-claim terms** — everything not in class (c) below.
  Unchanged from before this brief: must be covered by the claim's cited,
  relationally-linked evidence. **Only class (a) can ever cause a
  rejection.**
- **(c) Connective boilerplate** — a fixed, committed stop-list,
  `truth/connective_terms.txt`, loaded once at import into the frozenset
  `CONNECTIVE_TERMS`. Every entry is a single lower-case word annotated (in
  the file itself) with why it carries no factual weight, and — after
  council review, see below — re-audited against a second, explicit test:
  *could this word ever be part of a real job title or skill name?* An
  entry that fails that test does not go on the list, however
  letter-form it otherwise reads. The list is now deliberately small: pure
  salutations (zero plausible title/skill overlap) and the single label word
  the compiler's own claim wording still needs ("background").

There is no class (b). An earlier revision of this ADR had one
("opportunity-provenanced terms," the target role/employer name); it has
been removed entirely — see "Residual exposure and review history."

Guard 9's rejection condition is:

```python
uncovered = tokens(claim) - evidence_tokens - _NON_MATERIAL_WORDS - CONNECTIVE_TERMS
```

### 4. One shared validation dispatcher

`matching/artifact_validation.py::validate_artifact_claims(artifact,
validator)` is the single implementation of "for each generated claim,
route to `validate_narrative` or `validate_claim` and collect the
findings." `api/routes_api.py::_compile_and_export`,
`matching/test_artifacts_e2e.py`, and `matching/test_compiler.py` all call
it. Before council review these were three independently hand-copied
mirrors of the same ~10 lines, which meant the tests could (and, per the
council's defect 4, did) drift from what production actually runs. This is
a new file; it was not in the original file-scope list for this
deliverable, and was added on the coordinator's explicit direction during
remediation for exactly this reason.

### 5. Why class (c) cannot pass an unsupported founder claim

This is the property the deliverable is graded on, so it is stated
precisely rather than by assertion:

- Guard 9 is a **set subtraction**, not a conditional bypass. `uncovered` is
  computed by removing tokens from three *fixed* sets (`evidence_tokens`,
  `_NON_MATERIAL_WORDS`, `CONNECTIVE_TERMS`) from the claim's own token set.
  A token can only be removed if it is *literally a member* of one of those
  sets. There is no code path in which the presence of a class (c) token
  changes how any *other* token is evaluated — each token's fate is
  independent.
- `CONNECTIVE_TERMS` is loaded once, from a file committed to the
  repository, at import time. Nothing at request time — no claim text, no
  opportunity data, no caller input — can add to it. Widening it requires a
  new commit reviewed the same way any other source change is, and every
  entry must pass the "could this be part of a real job title or skill"
  test recorded in the file itself.
- Guards 1–8 and 10–12 (prohibited concepts, red lines, planned-credential,
  requested-evidence authorization, evidence discovery, temporal validity,
  relational composition, verification-status resolution, metric
  provenance, assertion-type resolution) are **entirely unaffected** by
  this ADR. A claim that would have been rejected by any of those guards
  before this brief still is. Class (c) only ever touches the guard 9
  token subtraction; it cannot cause guard 9 to be skipped, and it cannot
  cause an earlier guard to pass.
- Consequently, a term is admitted under class (c) if and only if it is a
  literal member of `CONNECTIVE_TERMS`. A fabricated, evidence-free,
  non-connective word — anything an unsupported founder claim would
  actually need to get past guard 9 — is in none of those sets and is
  still rejected. `matching/test_artifacts_e2e.py` (the mutation-based
  negative tests) and `api/test_api.py::ArtifactRoutesTest` (the extended
  tripwire, using the council's own headline probe) exercise this directly.

### 6. Why this is not a loosening of the no-fabrication rule

The founder-truth invariant this system exists to protect is: *no claim
about the founder appears in a generated document unless it is backed by
the founder's own evidence.* This ADR does not touch that invariant for any
term that is actually about the founder. What it changes is the set of
things the validator previously, incorrectly, treated as if they were
claims about the founder:

- The employer's name and the role title are facts about the *opportunity*,
  not the founder. A cover letter sentence that says "Applying for the Data
  Engineer role at Globex Corp" is not asserting that the founder has ever
  worked at Globex Corp — it is naming the document's own addressee, which
  is true by construction (it is quite literally the opportunity
  `_compile_and_export` is compiling against) and requires no evidence
  about the founder at all. Treating it as an unsupported founder claim, as
  guard 9 did before this brief, was not stronger fabrication protection;
  it was a false positive that made every tailored cover letter
  structurally impossible to generate. This sentence now carries **no
  founder-specific value whatsoever** and is emitted as `NARRATIVE`, so it
  needs no admissibility rule at all — see "Residual exposure" for why the
  first fix (an admissibility class instead) was the wrong shape.
- "Sincerely," "I am writing to express my interest," and similar
  connective prose assert nothing checkable about anyone. There is no
  fabrication risk in a greeting.

**What is honestly given up:** `validate_narrative` provides no
evidence-coverage protection for narrative text — it checks only that the
claim is not disguising itself as a founder fact (§2, checks 1–2 above) and
that it contains no prohibited concept or red-line phrase. A narrative
sentence that is *itself* connective (no claimed value, no metric) but
happens to contain, say, a false implication in prose form without
tripping the red-line patterns would not be caught. This residual gap is
structurally bounded, not open-ended: `matching/compiler_employment.py`
and `matching/compiler_independent.py` are the only two producers of
`GeneratedClaim` objects reaching this validator in production, and every
line in both that emits a founder-specific value (a title, a skill, a
metric, a certification, a service, a portfolio item) does so inside an
atomic, evidence-cited, non-narrative claim — never inside text marked
`NARRATIVE`, and now checked structurally (§2, checks 1–2) rather than
purely by convention. A reviewer of a future compiler change must still
verify that discipline by reading the compiler, the same way a reviewer
must today verify that a new predicate is added correctly to
`CANONICAL_MATERIAL_MANIFEST`; this ADR narrows that review burden but does
not eliminate it.

## Residual exposure and review history

An independent council review of the first shipped revision of this ADR
returned four MAJOR and three MINOR findings (full text:
`reports/evidence/FR-005/council-findings.md` and
`reports/evidence/FR-005/council-d1-probe.txt`). **The council's verdict was
that the underlying 409→200 change is legitimate** — guard 8 stayed intact
and reachable, no evidence record or template was edited, and no §9
violation occurred — **with no BLOCKER.** The council also supplied the
argument for *why* it is legitimate, which the first revision of this ADR
had not articulated: through the production path, every founder value the
compiler interpolates into a claim is already checked against its evidence
by `TruthGraph._is_value_supported_by_evidence` at ingest, before the
validator ever runs. So guard 9 was, in the shipped v1, in practice only
ever rejecting the compiler's own added vocabulary — FR-004's 409s were
false positives, not real protection being removed. That argument is why
the change stands. It is not, the council was explicit, a reason to leave
the findings below unfixed, and this brief did not treat it as one.

What the first revision actually shipped, and is no longer true after this
revision:

1. **Class (b) was applied blanket-wide, not scoped to the one claim that
   embedded an opportunity field.** `opportunity_terms` was computed once
   per document and passed to `validate_claim` for *every* non-narrative
   claim — CV skill, employment, and metric claims that mention no
   opportunity field at all included. Council probe: against evidence
   containing only "Data Engineer," the claim "Senior Data Engineer,
   Kubernetes certified." was correctly rejected with no opportunity terms,
   and was **allowed** once the target posting happened to be titled
   "Senior Engineering Manager" at "Kubernetes Certified Systems Group" —
   because those words tokenize into exactly the ones the claim needed.
2. **It was populated from scraped, third-party text the founder does not
   control.** `opportunity_terms` came from `Opportunity.organization` /
   `.title`, sourced from job postings ingested by adapters under their own
   access policies — not from anything the founder authored. A job
   poster's choice of company name could enlarge the set of words
   admissible in a claim about the founder.
3. **The brief's own condition — admissible "when the claim cites that
   provenance" — was asserted in the ADR's prose but never implemented.**
   `opportunity_terms` was applied unconditionally to every claim in a
   document, with no per-claim check that the specific claim actually
   embedded the opportunity field being admitted.
4. (Related, MINOR) `truth/connective_terms.txt`'s first revision listed
   `professional`, `position`, `team`, `hiring`, `manager`, and `time` —
   all plausible components of real job titles ("Hiring Manager,"
   "Part-Time Engineer"). Council probe: "Professional background: Data
   Engineer Manager." against evidence "Data Engineer" was allowed.

**The fix was removal, not narrowing**, for a reason worth recording
honestly: scoping class (b) down to "only the one claim that embeds an
opportunity field, and only that opportunity's own words" was the
council's first-suggested repair and would have satisfied findings 1–3
above. It was not taken. Once the target role/employer name is moved
entirely into a `NARRATIVE` segment that carries no founder-specific value
(§2), there is no remaining claim that needs opportunity words admitted at
all — the founder's title claim (`"Background: {title}."`) never mentions
the opportunity, and the opportunity-naming sentence is narrative and
therefore never evidence-checked in the first place. Removing the class
entirely produces a strictly smaller, easier-to-audit mechanism than a
correctly-scoped class (b) would have, for the same document. `truth/connective_terms.txt`
was also re-audited word by word against "could this be part of a real job
title or skill" (finding 4), independent of the class-(b) removal.

**What is true of the mechanism actually shipped, after this revision:**
class (c) is the only admissibility class left; it is a fixed, committed,
re-audited word list with no runtime input at all (not even from the
opportunity); and `validate_claim` no longer accepts an `opportunity_terms`
parameter — calling it with one raises `TypeError`, not a silent no-op. The
one property the council's ingest-verification argument does NOT change:
`ClaimValidator` is still the last, independent check before a claim
reaches a document with the founder's name on it, and it is no longer
relying on any input this brief does not fully control.

Two further MINOR findings were fixed without changing the shape of the
mechanism: `validate_narrative` now structurally rejects a claim tagged
`NARRATIVE` that carries `assertion_ids`/`evidence_ids`/`authorized_value`
or a parseable metric (§2); and a `MetricAssertion.context` ending in a
full stop no longer 409s the CV (`matching/compiler_employment.py` strips
the trailing period before building `"{context}: {value}{unit}"`, since a
period immediately before that string's colon was read by the validator's
clause-context extraction as a sentence boundary, truncating the clause the
number is checked against — a real, YAML-verbatim founder pack is exposed
to this, not only a fixture).

## Consequences

- **Positive:** the tailored-document feature now works for a
  naturally-written pack. `matching/test_artifacts_e2e.py` compiles a CV,
  cover letter, and (for the procurement fixture) proposal against both the
  shipped `synthetic_graph()` template and a new, larger, nine-role,
  five-certification, 38-skill `founder_shaped_graph()` fixture, across
  three fixture opportunities, with zero validator rejections.
  `REQ-ART-001/002/003` can move from `PARTIAL` on this evidence.
- **Positive:** the fix is structural (atomic claims, a single closed term
  class, a single shared validation dispatcher) rather than a validator
  carve-out for specific wording, so it does not need to be rediscovered
  for the founder's real pack.
- **Positive:** the mechanism that shipped is strictly smaller than the one
  first proposed — no opportunity-derived admissibility at all — because
  council review found the narrower version still had a scoping defect
  worth removing rather than patching.
- **Positive, incidental:** while wiring the procurement fixture,
  `matching/compiler_independent.py`'s portfolio section was found to read
  a `portfolio.item` predicate `CANONICAL_MATERIAL_MANIFEST` has never
  projected (only `portfolio.title`/`portfolio.summary` are), so that
  section never rendered for any pack, including the shipped template. This
  brief corrected the *truth-graph-side* read to `portfolio.title` (the
  minimal in-scope fix, consistent with how `service.name` is already
  read); the compiler's own `GeneratedClaim.predicate="portfolio.item"`
  claim-type tag is a separate, unrelated string — consumed by
  `matching/validator.py::ArtifactClaimValidator`, a frozen file this
  deliverable does not own — and was deliberately left unchanged. See the
  code comments at both sites.
- **Negative / accepted risk:** `validate_narrative` still provides no
  evidence-coverage protection for text that is genuinely connective and
  contains no claimed value or metric — see Decision §6. Structural checks
  (§2) now catch a *misclassified* founder-fact claim; they do not, and
  cannot, catch a false statement made entirely in prose with no claimed
  value. This is bounded by the compiler discipline described in §6, which
  remains a review obligation.
- **Negative / accepted risk:** `CONNECTIVE_TERMS` is a judgment call about
  what counts as "no factual weight," re-audited once against the
  "job title or skill" test but not immune to a future entry that fails it.
  Every entry is documented in `truth/connective_terms.txt`; adding an
  entry is a reviewable, single-file, committed change — not a runtime
  decision — by design.
- **Cost / operational:** none. No schema, migration, or new dependency.

## Alternatives considered

- **Loosen guard 8 (relational composition) to allow unrelated evidence in
  one claim.** Rejected: that guard exists specifically to prevent
  "relationship laundering" — asserting a connection between two true facts
  that was never established in the graph. Loosening it would have been a
  real weakening of the no-fabrication rule, not a fix to a false positive.
  Guard 8 is completely unchanged by this brief.
- **Write the compiler's vocabulary into the founder's evidence records so
  the existing guard 9 would pass.** This is the failure mode STATE.md
  already recorded as attempted and stopped during BRIEF-FR-004, and it
  remains the wrong resolution for the same reason: it would make the
  validator decorative and put unsupported claims into a document carrying
  the founder's name. No evidence record, template, or fixture `content`
  field was edited to contain compiler-introduced vocabulary anywhere in
  this brief, in either revision.
- **Scope class (b) down to the one claim that embeds an opportunity field,
  instead of removing it.** This was the council's first-suggested repair
  and would have fixed findings 1–3 above. Not taken, once it became clear
  that moving the opportunity-naming sentence to `NARRATIVE` (already
  necessary, since it carries no founder value) removed the *need* for any
  opportunity-derived admissibility at all. A mechanism with no runtime
  input is easier to audit than a correctly-scoped one with runtime input,
  for the same resulting document.
- **Give the validator a general "opportunity fields are always exempt"
  rule instead of an explicit, caller-supplied parameter.** Rejected in the
  first revision, and moot in this one: there is no opportunity-derived
  admissibility left to guess at.
- **Add a dedicated `is_narrative: bool` field to `GeneratedClaim` instead
  of reusing `policy_source`.** `matching/models.py` was out of scope for
  this deliverable; the brief instructed the implementer to prefer a
  committed `policy_source` value and to stop and report a scope question
  rather than edit `matching/models.py` if a new field were genuinely
  needed. `policy_source` (an existing, unused-for-this-purpose free-text
  field) was sufficient, so no scope question arose — including after
  council review added a validate_narrative structural check that reads
  `assertion_ids`/`evidence_ids`/`authorized_value` directly off the
  existing `GeneratedClaim` fields.

## Required tests and rollback

- **Verification:** `matching/test_artifacts_e2e.py` (positive coverage
  across both packs and three fixture opportunities, plus per-pack mutation
  tests that a claim mutated to add an unsupported word is rejected — and
  only that claim — and that a NARRATIVE claim mutated to contain a
  red-line phrase is rejected); `matching/test_artifacts_e2e.py::PeriodTerminatedMetricContextTest`;
  the extended tripwire in `api/test_api.py::ArtifactRoutesTest`
  (`test_artifact_409_never_returns_docx_bytes`'s direct
  `ClaimValidator.validate_claim` assertion, using the council's own
  headline probe, plus dedicated 409/200 test methods); the replaced
  section-counting tests in `matching/test_compiler.py`; and
  `truth/test_validator.py` (frozen, unmodified, still green).
- **Rollback:** revert `truth/validator.py`, `truth/connective_terms.txt`,
  `matching/compiler_employment.py`, `matching/compiler_independent.py`,
  `matching/artifact_validation.py`, and the `_compile_and_export` call-site
  and import changes in `api/routes_api.py`, and supersede this ADR. Guard
  8 and guards 1–7/10–12 are unmodified, so a rollback returns exactly to
  the BRIEF-FR-004 behaviour (and its documented defect) with no other side
  effects.
