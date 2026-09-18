# Overseer Execution Lock v1.0

Status: **Standing project operating rule**

This document exists to prevent repeated executor ping-pong and to make the OpportunityOS engineering loop deterministic.

## Locked operating loop

For each substantial engineering wave:

1. **Sol/Overseer pre-solves the task.**
   - Inspect the actual repository.
   - Resolve architecture, ownership, invariants, edge cases, interfaces, acceptance criteria, and test strategy.
   - Dispatch a bounded implementation packet to the appropriate executor.

2. **Executor performs one substantial implementation wave.**
   - Default models: Codex/Luna Medium and Antigravity/Gemini 3.8 Flash Medium.
   - The executor is expected to diagnose and repair normal implementation failures before returning.
   - Executor reports are evidence input, never acceptance authority.

3. **Sol independently verifies repository truth.**
   - Inspect the actual branch/SHA, complete diff, tests, migrations, CI, evidence, and state.
   - Do not accept PASS solely because an executor claims PASS.

4. **At most one focused executor remediation wave.**
   - Use only when the first implementation contains substantive implementation defects that materially benefit from executor work.
   - The remediation packet must be surgical and evidence-derived, not a redesign.

5. **After the single remediation wave, Sol owns ordinary closure.**
   Sol must personally close small/localized/well-understood residuals, including:
   - test-fixture corrections;
   - small code defects;
   - missing assertions;
   - state/evidence freshness;
   - documentation mismatches;
   - PR creation;
   - CI triggering and inspection;
   - branch/integration friction;
   - minor configuration corrections;
   - simple merge/conflict cleanup;
   - other last-mile issues where another executor round would cost more than it adds.

6. **A third executor round is exceptional.**
   It is allowed only when independent verification discovers work that is:
   - broad;
   - architecture-sensitive;
   - security-sensitive;
   - concurrency/data-integrity-sensitive;
   - or genuinely difficult enough that another specialist implementation round has positive engineering value.

   Ordinary failures, stale state, missing GitHub authentication, PR creation, CI reruns, small test failures, or routine integration issues do **not** qualify.

7. **Keep both executor pools productively occupied when independent work exists.**
   - Do not leave Codex or Antigravity idle merely because another lane is still under review.
   - Re-read the active brief/checklist after each checkpoint and dispatch the next non-overlapping lane when useful.
   - Never create parallel write overlap unless explicitly justified.

## Executor budget rule

The target lifecycle is:

**Sol pre-solves -> executor implements -> Sol verifies -> maximum one executor remediation -> Sol closes/integrates -> next wave.**

Repeated back-and-forth with the same executor for ordinary defects is a process failure and must be corrected by the Overseer, not normalized.

## Checkpoint rule

After each wave, the Overseer maintains an authoritative checklist with:

- Completed
- In verification
- Pending
- Blocked by external/provider/human dependency
- Newly discovered defects/debt
- Current branch/PR/SHA state
- Next parallel wave assignments

The checklist is derived from repository evidence, not agent self-report.

## Founder interruption rule

Do not involve the Founder for routine engineering judgment or ordinary tool friction.

Founder input is reserved for genuine dependencies such as:
- credentials or interactive provider authentication;
- paid-resource approval;
- irreversible/external actions;
- materially different product outcomes;
- legal/compliance decisions;
- subjective product acceptance.

## Enforcement

If an executor returns and the Overseer notices this rule would otherwise cause another ordinary remediation loop, the Overseer must stop the loop, finish the bounded residual work directly, and move the executor to the next useful non-overlapping task.
