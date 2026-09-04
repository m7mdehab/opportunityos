# OpportunityOS Current Roadmap

This is the compact execution map. `docs/MASTER_PLAN.md` remains the full long-horizon plan and requirement source.

## Portfolio Priority

OPOS is a high-leverage founder system because it can improve employment, remote-job, freelance/consulting, and procurement opportunity throughput while reducing repetitive application work.

Within the overall project portfolio, OPOS receives first claim on unconstrained engineering capacity unless another project has a real external deadline, production incident, or time-sensitive launch that temporarily preempts it.

## Current Phase

Current verified `main` snapshot on 2026-09-05:

`7e90eed48f1308d9cbeaa03f111e3dc206c6d26c`

Generated `docs/STATE.md` reports:

- last shipped: BRIEF-FR-005;
- active: BRIEF-FR-006;
- Phase status: in progress;
- BRIEF-007 / Multi-Tenant Family Alpha blocked until Founder Web Alpha is live and validated.

`reports/REPORT-FR-006.md` currently concludes `PASS_WITH_NOT_CLOSED`, so BRIEF-FR-006 is not treated as fully closed merely because many acceptance rows pass.

## Immediate Goal - Close BRIEF-FR-006 honestly

The current report says the engine, founder-control, document, search, card, and truth-lock work are substantially delivered, but source breadth remains the main founder-facing limitation.

Key current gaps from the report:

- 36 discovered boards against a 300-board target;
- zero new read-allowed sources currently producing rows in the product;
- work-mode extraction about 52.2 percent versus 90 percent target;
- country-or-remote-scope coverage about 72.2 percent versus 85 percent target;
- title-family mapping about 86.9 percent versus 95 percent target;
- several brief claims remain explicitly `NOT_CLOSED` or partial;
- two Playwright checks fail because the current spec mechanism does not exercise the service-worker path it claims to test;
- live poll did not run in the recorded host-exhaustion attempt;
- `stale_postings` writer exists but is not yet invoked;
- source breadth is still the dominant practical bottleneck.

Do not erase these gaps by editing targets or relabeling report rows.

## BRIEF-FR-006 Closure Work

The next Owner/Overseer review should operate from actual current code/evidence and decide whether the active brief should:

1. receive a narrowly bounded closure/correction pass against its remaining explicit acceptance criteria; or
2. close the genuinely delivered scope while moving clearly separable unmet breadth/quality targets into an explicit next brief with no false claim that they were met.

The choice must follow the brief's terminal contract and actual evidence, not convenience.

Specific report items reserved for Owner/Overseer attention include:

- resolve the report's invalid/undefined matrix labels by real `req_id` rather than inventing mappings;
- independently re-run or otherwise verify the truth-lock/guard-neutralisation property reserved for Overseer checking;
- reconcile generated `STATE.md` if it says zero open acceptance items while the active report remains `PASS_WITH_NOT_CLOSED`.

## Next Product Direction After Founder Web Alpha

Priority order is economic usefulness, not architectural novelty.

### 1. Better real opportunity yield

- expand compliant, productive source coverage;
- improve board/source discovery quality;
- improve extraction where real payload evidence supports it;
- prioritize sources that actually yield Egypt/MENA/remote-eligible opportunities rather than maximizing registry size;
- preserve source permission and provenance rules.

### 2. Founder daily workflow

The founder should be able to open OPOS and quickly answer:

- what opportunities are worth opening today;
- why each one fits or does not fit;
- what evidence supports the fit;
- what tailored material is ready;
- what is blocked by truth/policy rather than hidden behind generic uncertainty;
- which actions require founder judgment versus can be executed autonomously.

### 3. Application/outbound operational quality

Continue to harden real-world preparation/fill/controlled-submit paths only under existing action authority, idempotency, confirmation, and no-bypass rules.

### 4. Outcome monitoring and learning

Use recruiter/client/inbox signals and application outcomes to improve prioritization and operations without letting statistical learning overwrite deterministic founder truth or source/action policy.

### 5. Founder Web Alpha validation

Validate the product on real founder use, not only fixtures:

- useful opportunity yield;
- duplicate collapse;
- location/remote clarity;
- artifact quality;
- unsupported-sentence rate;
- time saved;
- false-negative/false-positive qualification behavior;
- outbound safety and duplicate prevention;
- end-to-end usability.

### 6. Multi-Tenant Family Alpha

Remain blocked until Founder Web Alpha is live and validated under the accepted tenancy decision.

Do not incur multi-tenant complexity early merely because the schema can support it later.

## Engineering Priority Rules

- truth/provenance and external side effects outrank cosmetic speed;
- zero-tolerance properties stay zero tolerance: duplicate submission, unsupported founder claims, unauthorized submission, Red-class auto-answering, cross-tenant leakage, prohibited-channel contact;
- independent review is targeted at high-consequence properties, not every deterministic edit;
- after two failures on the same criterion, change strategy rather than looping;
- respect measured host/concurrency limits;
- agents execute all solvable work and surface only genuine founder-only blockers.

## What Not To Optimize For

- registry/source count without productive compliant yield;
- automatic application volume at the expense of truth or duplicate safety;
- false certainty from missing founder data;
- premature multi-tenancy;
- councils for routine deterministic work;
- provider/model prestige rather than measured project outcomes.
