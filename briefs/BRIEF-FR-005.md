# BRIEF-FR-005 — Truthful Artifacts and the First Real Measurement

**Version:** 1.0
**Date:** 2026-09-02
**Overseer:** external independent auditor (author of the FR-003 and FR-004 reviews)
**Master:** Claude Code main session, model `opus`
**Status:** ACTIVE. Starting main = `b563102` plus the FR-004 erratum commit; record the exact head in pre-flight.
**Named agents:** `implementer`, `evidence-runner`, `verifier`, `council-reviewer`, `Explore` load from `.claude/agents/`.
**Source of scope:** §5 of the Overseer's post-merge review of BRIEF-FR-004, reproduced faithfully below.

---

## 0. Why this brief exists

FR-004 built the slice and did not produce the number. Two things stand between the
founder and it, and the FR-004 review named both.

**The artifacts do not compile.** Tailored CV and cover-letter generation returns 409 for
every realistic truth pack. FR-004 documented this rather than forcing it green, which was
right, and the erratum downgraded `REQ-ART-001/002/003` to PARTIAL because
`matching/test_compiler.py` counts sections and never runs the validator. The capability
was never end-to-end tested and the first real pack broke it.

**Nothing real has been polled through the new seam.** The FR-004 A-9 feed of 138
opportunities was test-database residue, not polled data — `alpha.py` attached to
`opportunityos_test`. Every D3 and D8 test injects a fixture transport, which is correct
for a test and is not proof the seam runs live.

So this brief does exactly two engineering jobs and then hands the founder a run that can
actually produce the measurement.

**Already discharged before this brief opened:** item 4 of the Overseer's §5, the
REPORT-FR-004 erratum, is committed (`reports/REPORT-FR-004.md` Erratum 1, the appended
correction in `reports/evidence/FR-004/a9-alpha-transcript.txt`, and the matrix downgrade).
Do not redo it; verify it in pre-flight and move on.

**Hard non-goals:** hosting, HTTPS, Caddy, Docker, multi-tenancy, any new source adapter,
any outbound action beyond founder-attested "I applied", any second web page, Phase 6, any
change to `docs/MASTER_PLAN.md`, and any weakening of `truth/validator.py`'s refusal
behaviour to make a test pass.

---

## 1. Frozen and unfrozen

- **Frozen:** BRIEF-002…006 semantics; the FR-002 fail-closed persistence invariant (A-0 must stay green); all FR-004 deliverables except where a deliverable below names them.
- **Unfrozen for named deliverables only:** `matching/compiler_employment.py`, `matching/compiler_independent.py`, `truth/validator.py` (D1); `scripts/alpha.py` (D2); `storage/models.py` and `storage/migrations/` (D3 only, via new revision `0003` — never by editing `0001` or `0002`).

**Standing constraint on D1.** The validator's refusals are a safety property, not an
obstacle. FR-004 stopped an agent mid-task for approaching this by writing the compiler's
vocabulary into the founder's evidence, which fabricates provenance. Any change that makes
a claim pass by making the evidence say what the compiler wanted is an automatic FAIL of
this brief, whoever makes it. The characterisation test's `saw_rejection` tripwire stays,
and must still fail when the validator is neutralised.

---

## 2. Deliverables

### D1 — The artifact path, properly (ADR-0014)
- Compilers emit **atomic, evidence-bound claims**: no composite claim spanning two evidence records without a declared relation between them.
- `truth/validator.py` distinguishes three kinds of term: founder-claim content (must be evidence-backed, unchanged), connective boilerplate (not a factual assertion), and **opportunity-provenanced** terms — employer name, role title and the like — which carry the opportunity's own field provenance rather than the founder's. A cover letter naming the target employer must be able to pass without that employer appearing in the founder's evidence, and must still fail if it asserts anything about the founder that the founder's evidence does not support.
- End-to-end `compiler × validator` tests over **the shipped founder template** and **a second, structurally different realistic pack**. Both produce a CV and a cover letter with zero rejected claims and a 200 from both artifact routes.
- The FR-004 characterisation test and its tripwire are retained and still pass.
- ADR-0014 records the three-way term classification and why it is not a loosening of the no-fabrication rule.

**Acceptance:** both packs produce both artifacts at HTTP 200 with zero rejected claims; the tripwire test still fails when the validator is neutralised; `REQ-ART-001/002/003` flip PARTIAL → DONE **only** on this evidence. Owner: implementer. **Council: YES (safety-critical validator semantics).**

### D2 — Live-poll proof on a database of alpha's own
- `scripts/alpha.py` targets `opportunityos_alpha`, creates it when absent, runs migrations against it, and **refuses to start against any database whose name ends in `_test`** with a founder-readable error naming the database.
- `docs/templates/alpha.env.template` updated accordingly.
- One real `poll-now` across the read-allowed sources, through the worker seam, on a database that starts empty.

**Acceptance:** evidence records per-source fetched/persisted/evaluated counts and the resulting dashboard line, on a fresh `opportunityos_alpha`, with **no `example.com` and no `opp-uq-*` row anywhere** in the feed response. Source policy is unchanged: read-allowed endpoints only, rate limits respected, stop on 403/429/CAPTCHA. Owner: implementer. Council: no.

### D3 — `field_provenances` primary key (migration `0003`)
- Residual from FR-004 D3: the table carries a surrogate autoincrement `id`, so `merge()` cannot deduplicate provenance rows and re-ingesting an opportunity accumulates duplicates. Give it a natural key (`opportunity_id`, `field_name`, `record_checksum` — or a documented equivalent the council accepts) in revision `0003`, with de-duplication of existing rows in the upgrade.
- Round-trip: 3 up → 3 down → 3 up, exit 0. Test: ingest the same opportunity twice, assert provenance row count is stable.

**Acceptance:** tests pass; round-trip clean; `0003` reversible. Owner: implementer. **Council: YES (migration with data transformation).**

### D4 — Report, matrix, STATE, evidence, PR
- `reports/REPORT-FR-005.md` in the FR-004 format, with a `## Decision` line and a `**Date:**` line at column zero.
- Regenerate the readiness matrix from JSON; every flipped row carries a `status_history` entry.
- `python scripts/generate_state.py`, committed as the **final commit, touching `docs/STATE.md` alone**.

**Acceptance:** narrow checks then all repository checks green; four workflows green on the PR head. Owner: Master. Council: no.

### D5 — The founder acceptance run (terminal)
Gated on D1 and D2 both closed. The founder loads their real truth pack, runs
`python scripts/alpha.py up`, works the §9 acceptance packet, generates a CV and a cover
letter that open, and fills in the line the whole project is for.

---

## 3. Execution order

D3 and D2 are independent and may run in parallel worktrees. D1 is serial and is the long
pole; start it first. D4 follows all three. D5 follows the merge.

---

## 4. Roles and model routing

Unchanged from FR-004. Every deliverable is implemented by an agent that did not review it;
council reviews on D1 and D3 go to a reviewer that did not implement them; the verifier
re-executes the whole claim ledger in a fresh context. Escalations are recorded in the
report with their trigger.

---

## 5. Master loop

Unchanged from FR-004 §5: the claim ledger is written **before** any delegation; the Master
re-runs every acceptance command itself; defects go back to the same implementer as a
numbered list; the Master never patches an implementer's deliverable to make it pass; both
the Master and the verifier must PASS before a claim closes. A claim's expected result must
state every property the report will later assert about it — FR-004's Erratum 1.1 exists
because a claim named a transcript and the prose asserted the provenance of its rows.

---

## 6. Environment

Local only. PostgreSQL 16, Python 3.12, Node 24. No cloud tasks. Scratch databases are
dropped and worktrees pruned before the terminal gate.

---

## 7. Claim ledger — mandatory rows

Carry forward A-0 through A-9 from FR-004 unchanged, plus:

- **A-10** — both packs, both artifacts, HTTP 200, zero rejected claims, and the neutralised-validator tripwire still failing.
- **A-11** — a fresh `opportunityos_alpha`, one real poll, per-source counts, and a feed response containing no `example.com` or `opp-uq-*` row.
- **A-12** — `alpha.py` refuses a `_test` database by name.
- **A-13** — migration `0003` round-trip, and stable provenance row count across a double ingest.

---

## 8. Definition of done

PASS means the founder can load their real truth pack, run one command, see a feed built
from a real poll, and generate a CV and a cover letter that open — with the validator's
refusals still intact and provably so.

---

## 9. Hard stops

Any attempt to read `private/`; any request to store or log founder data; any outbound HTTP
other than the read-allowed sources' documented endpoints and package registries; any
external mutation outside the single ADR-0005 TED `READ_ONLY_QUERY` exception; **and any
change that makes a claim validate by putting words into the founder's evidence that the
founder's evidence did not already support.**

---

## 10. Terminal gate

The brief ends when `reports/REPORT-FR-005.md` carries a `## Decision` of `PASS`,
`PASS_WITH_NOT_CLOSED` or `FAIL`, the PR is merged, `main` is green on four workflows, and
the worktrees and scratch databases are cleaned up. Defects, failed tests and remediable
gate findings create repair tasks; they do not end the brief.
