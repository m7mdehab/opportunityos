# OpportunityOS Current Roadmap

This is the compact execution map. `docs/MASTER_PLAN.md` remains the full long-horizon plan and requirement source.

## Portfolio Priority

OPOS is a high-leverage founder system because it can improve employment, remote-job, freelance/consulting, and procurement opportunity throughput while reducing repetitive application work.

Within the overall project portfolio, OPOS receives first claim on unconstrained engineering capacity unless another project has a real external deadline, production incident, or time-sensitive launch that temporarily preempts it.

## Current Phase

PR #78 is the authoritative FR-006 recovery checkpoint until merged. Run `34724239556` is green with 1095 Linux/PostgreSQL tests and zero skips, Playwright 22/22, and passing governance. Companion Guard, State, Mirror, and bounded live-evidence checks are green.

`reports/REPORT-FR-006.md` concludes `PASS_WITH_NOT_CLOSED`. The bounded technical recovery is complete; frozen exceptions stay visible: A-12 work-mode coverage 77.6% versus 90%, A-23 persisted source yield 0/8 despite 334/300 live boards, A-20's absent exact frozen-corpus subset, and A-6's accepted historical deviation.

## Immediate Goal - Founder Web Alpha validation

Merge the green reconciled PR, verify `main`, then validate the founder experience with the private Truth Pack outside Git. Do not restart closed recovery work without a concrete regression, invent missing signals, or relabel frozen exceptions as ordinary PASS.

BRIEF-007 / Multi-Tenant Family Alpha remains blocked until Founder Web Alpha is live and personally validated.

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
