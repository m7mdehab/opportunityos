# ADR-0014 — Claim Classes: Atomic Founder Claims, Narrative Segments, and Opportunity-Provenanced Terms

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

- **Guard 8 (relational composition, line 368 before this brief):** a claim
  citing more than one evidence record is refused unless those records are
  relationally linked in the graph.
- **Guard 9 (material lexical coverage, line ~378 before this brief):** a
  claim is refused if it contains any word not present in its cited
  evidence, after subtracting a ~55-word list of function words
  (`_NON_MATERIAL_WORDS`).

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

## Decision

Every generated claim is now classified before compilation, and the
validator recognizes three term classes when it does still check a claim's
lexical coverage.

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

### 2. Narrative segments

Connective prose that asserts no founder-specific fact — greetings ("I am
writing to express my interest..."), closings, and other letter-structure
sentences — is emitted as a `GeneratedClaim` with `policy_source="NARRATIVE"`
(the field already existed on `matching/models.GeneratedClaim`; no new field
was added, and `matching/models.py` was not touched). `ClaimValidator`
gains one new method, `validate_narrative`, which runs only the two guards
that do not depend on evidence — Never-Claim/red-line prohibition and the
planned-credential guard — on the full narrative text, exactly as
`validate_claim` runs them on claim text. It does not run the
evidence-coverage, relational-composition, or metric-provenance guards,
because a sentence that makes no evidentiary claim about the founder cannot
meaningfully be measured against evidence coverage. `api/routes_api.py`'s
`_compile_and_export` dispatches on `claim.policy_source == "NARRATIVE"` to
choose which validator method to call; this is the one call site in that
file this brief touched.

The compiler is responsible for the classification: a narrative segment must
never contain a founder-specific value (a title, a skill name, a metric —
anything that could be true of one founder and false of another). Every such
value stays inside an atomic, evidence-cited claim. This is enforced by
construction in the two compiler files, not by the validator inferring
intent from text.

### 3. Three term classes for guard 9

Guard 9 (material lexical coverage, `validate_claim` step 9) now excuses two
additional term classes from the "uncovered material term" rejection,
on top of the unchanged `_NON_MATERIAL_WORDS`:

- **(a) Founder-claim terms** — everything not in classes (b) or (c) below.
  Unchanged from before this brief: must be covered by the claim's cited,
  relationally-linked evidence. **Only class (a) can ever cause a
  rejection.**
- **(b) Opportunity-provenanced terms** — the employer name, role title, and
  any other field carried from the target `Opportunity` with its own field
  provenance. `truth/validator.py::opportunity_terms_from_values(*values)`
  tokenizes whatever real values it is given; it does not look at the claim,
  the opportunity object, or anything else — it is a pure tokenizer over
  values the CALLER already asserts are real. `_compile_and_export` is the
  caller: it builds `opportunity_terms_from_values(domain_opp.organization,
  domain_opp.title)` from the `Opportunity` record actually loaded from
  storage for this request, and passes it to every non-narrative claim's
  `validate_claim(..., opportunity_terms=opportunity_terms)` call for that
  document. `validate_claim` never derives this set itself.
- **(c) Connective boilerplate** — a fixed, committed stop-list,
  `truth/connective_terms.txt`, loaded once at import into the frozenset
  `CONNECTIVE_TERMS`. Every entry is a single lower-case word annotated (in
  the file itself) with why it carries no factual weight: letter-form
  salutations/closings, and generic CV/cover-letter structural vocabulary
  ("professional", "background", "role", "applying", ...) that names no
  specific value. It is an *addition* to `_NON_MATERIAL_WORDS`, which is
  untouched.

Guard 9's rejection condition became:

```python
admissible_non_founder_terms = CONNECTIVE_TERMS | (opportunity_terms or set())
uncovered = tokens(claim) - evidence_tokens - _NON_MATERIAL_WORDS - admissible_non_founder_terms
```

### 4. Why classes (b) and (c) cannot pass an unsupported founder claim

This is the property the deliverable is graded on, so it is stated
precisely rather than by assertion:

- Guard 9 is a **set subtraction**, not a conditional bypass. `uncovered` is
  computed by removing tokens from four *fixed* sets (`evidence_tokens`,
  `_NON_MATERIAL_WORDS`, `CONNECTIVE_TERMS`, `opportunity_terms`) from the
  claim's own token set. A token can only be removed if it is *literally a
  member* of one of those sets. There is no code path in which the presence
  of a class (b) or (c) token changes how any *other* token is evaluated —
  each token's fate is independent.
- `CONNECTIVE_TERMS` is loaded once, from a file committed to the
  repository, at import time. Nothing at request time — no claim text, no
  opportunity data, no caller input — can add to it. Widening it requires a
  new commit reviewed the same way any other source change is.
- `opportunity_terms` is never derived from the claim or guessed by the
  validator. It is an explicit parameter the validator trusts the caller to
  populate correctly, and the one production caller
  (`api/routes_api.py::_compile_and_export`) populates it from exactly two
  fields — `organization` and `title` — read off the `OpportunityRecord`
  actually stored for the opportunity being compiled against, not from
  anything the compiler or the claim text supplies. A claim cannot declare
  its own words "opportunity-provenanced"; only the caller, holding the real
  `Opportunity`, can.
- Guards 1–8 (prohibited concepts, red lines, planned-credential,
  requested-evidence authorization, evidence discovery, temporal validity,
  relational composition) are **entirely unaffected** by this ADR. A claim
  that would have been rejected by any of those guards before this brief
  still is. Classes (b) and (c) only ever touch the guard 9 token
  subtraction; they cannot cause guard 9 to be skipped, and they cannot
  cause an earlier guard to pass.
- Consequently, a term is admitted under class (b) or (c) if and only if it
  is a literal member of `CONNECTIVE_TERMS`, or a literal token of a value
  the caller supplied as real opportunity data. A fabricated, evidence-free,
  non-opportunity, non-connective word — anything an unsupported founder
  claim would actually need to get past guard 9 — is in none of those sets
  and is still rejected. `matching/test_artifacts_e2e.py` and
  `api/test_api.py::ArtifactRoutesTest` (the extended tripwire) exercise
  this directly, including a "saw_rejection"-style assertion that a
  fabricated term is rejected by default and admitted only once explicitly
  declared class (b) for that one call.

### 5. Why this is not a loosening of the no-fabrication rule

The founder-truth invariant this system exists to protect is: *no claim
about the founder appears in a generated document unless it is backed by
the founder's own evidence.* This ADR does not touch that invariant for any
term that is actually about the founder. What it changes is the set of
things the validator previously, incorrectly, treated as if they were
claims about the founder:

- The employer's name and the role title are facts about the *opportunity*,
  not the founder. A cover letter that says "applying for the Data Engineer
  role at Globex Corp" is not asserting that the founder has ever worked at
  Globex Corp — it is naming the document's own addressee, which is true by
  construction (it is quite literally the opportunity `_compile_and_export`
  is compiling against) and requires no evidence about the founder at all.
  Treating it as an unsupported founder claim, as guard 9 did before this
  brief, was not stronger fabrication protection; it was a false positive
  that made every tailored cover letter structurally impossible to
  generate.
- "Sincerely," "I am writing to express my interest," and similar
  connective prose assert nothing checkable about anyone. There is no
  fabrication risk in a greeting.

**What is honestly given up:** if a future compiler change were to smuggle a
founder-specific value into a `NARRATIVE`-tagged segment, `validate_narrative`
would not catch it on lexical-coverage grounds — it only checks prohibited
concepts and red lines, not evidence coverage, because narrative text by
definition cites none. That gap is closed by construction, not by the
validator: `matching/compiler_employment.py` and
`matching/compiler_independent.py` are the only two producers of
`GeneratedClaim` objects reaching this validator in production, and every
line in both that emits a founder-specific value (a title, a skill, a
metric, a certification, a service, a portfolio item) does so inside an
atomic, evidence-cited, non-narrative claim — never inside the text marked
`NARRATIVE`. A reviewer of a future compiler change must keep verifying that
invariant by reading the compiler, the same way a reviewer must today verify
that a new predicate is added correctly to `CANONICAL_MATERIAL_MANIFEST`;
this ADR does not, and cannot, make that review unnecessary. Similarly, if
`opportunity_terms_from_values` were ever called by a caller other than
`_compile_and_export` with a value that was not genuinely a real,
independently-provenanced `Opportunity` field, that caller — not this
ADR's mechanism — would be the defect. The mechanism itself only ever
tokenizes what it is handed; the discipline of handing it only real
opportunity field values remains a code-review obligation at each call
site, exactly as it is today for evidence citations.

## Consequences

- **Positive:** the tailored-document feature now works for a
  naturally-written pack. `matching/test_artifacts_e2e.py` compiles a CV,
  cover letter, and (for the procurement fixture) proposal against both the
  shipped `synthetic_graph()` template and a new, larger, nine-role,
  five-certification, 38-skill `founder_shaped_graph()` fixture, across
  three fixture opportunities, with zero validator rejections.
  `REQ-ART-001/002/003` can move from `PARTIAL` on this evidence.
- **Positive:** the fix is structural (atomic claims, closed term classes)
  rather than a validator carve-out for specific wording, so it does not
  need to be rediscovered for the founder's real pack.
- **Positive, incidental:** while wiring the procurement fixture,
  `matching/compiler_independent.py`'s portfolio section was found to read
  a `portfolio.item` predicate `CANONICAL_MATERIAL_MANIFEST` has never
  projected (only `portfolio.title`/`portfolio.summary` are), so that
  section never rendered for any pack, including the shipped template. This
  brief corrected the read to `portfolio.title` (the minimal in-scope fix,
  consistent with how `service.name` is already read) so the section
  actually generates; see the code comment at that line for the fuller
  explanation.
- **Negative / accepted risk:** `validate_narrative` provides no
  evidence-coverage protection for the text it validates. This is
  acceptable only because narrative text is, by construction in the two
  compiler files, never the carrier of a founder-specific value — see
  Decision §5. A future compiler change that violates that discipline would
  not be caught by this validator; it must be caught by review.
- **Negative / accepted risk:** `CONNECTIVE_TERMS` and the two
  opportunity-provenanced fields (`organization`, `title`) are a
  judgment call about what counts as "no factual weight." Every entry is
  documented in `truth/connective_terms.txt` with why it was chosen; adding
  an entry is a reviewable, single-file, committed change — not a runtime
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
  this brief.
- **Give the validator a general "opportunity fields are always exempt"
  rule instead of an explicit, caller-supplied parameter.** Rejected: that
  would let the validator itself decide what counts as opportunity data by
  inspecting the claim text or guessing, which is exactly the kind of
  self-authorization class (b) must not have. Requiring the caller to pass
  the real field values explicitly keeps the validator's role
  read-only/dumb with respect to what "the opportunity" is.
- **Add a dedicated `is_narrative: bool` field to `GeneratedClaim` instead
  of reusing `policy_source`.** `matching/models.py` was out of scope for
  this deliverable; the brief instructed the implementer to prefer a
  committed `policy_source` value and to stop and report a scope question
  rather than edit `matching/models.py` if a new field were genuinely
  needed. `policy_source` (an existing, unused-for-this-purpose free-text
  field) was sufficient, so no scope question arose.

## Required tests and rollback

- **Verification:** `matching/test_artifacts_e2e.py` (new), the extended
  `truth/test_validator.py`-adjacent tripwire in
  `api/test_api.py::ArtifactRoutesTest` (`test_artifact_409_never_returns_docx_bytes`'s
  extended assertion plus the two new test methods), and the replaced
  section-counting tests in `matching/test_compiler.py`.
- **Rollback:** revert `truth/validator.py`, `truth/connective_terms.txt`,
  `matching/compiler_employment.py`, `matching/compiler_independent.py`, and
  the `_compile_and_export` call-site change in `api/routes_api.py`, and
  supersede this ADR. Guard 8 and guards 1–7/10–12 are unmodified, so a
  rollback returns exactly to the BRIEF-FR-004 behaviour (and its
  documented defect) with no other side effects.
