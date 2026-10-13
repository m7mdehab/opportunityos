# CI execution policy — 2026-10-13 owner override

**Required testing is authorized. Credits are meant to be used.** The owner's latest instruction supersedes any blanket no-hosted-CI policy used to preserve credits. Do not delay engineering, omit acceptance gates, or falsely mark unexecuted tests passed just to keep a Free account balance untouched.

1. Use meaningful CI for acceptance, security, regression, privacy, integration and browser validation when relevant, and for diagnosing blocked merges. The goal is fast, trustworthy completion.
2. Be **conservative, not stingy**: consolidate runs, use efficient jobs and caches, prevent duplicate unchanged runs and unnecessary background schedules, and run real checks at meaningful checkpoints.
3. Confirm this repository's *own* CI provider, remaining included/free credits and configured triggers; NEVER assume Tutor's 30,000-credit budget also belongs to this project. Presaira and every other CI organization have independent allocations.
4. Necessary compute within a project's confirmed existing included/free allowance is approved; upgrades, new payment methods, overages and paid plans are **not** approved. When access/configuration is missing, proactively specify the exact fixable permission/connector/setting and ask the owner once, then continue independent work.
5. Do not weaken branch protections, review gates, private source policy, production/database authorization, or minors'/personal-data safeguards.
6. Document SHA-matched execution links, full pass/fail results and any known credit use. CI configuration or a queued pipeline is not a passing test.
7. Do not turn on cost-incurring all-push CI for unrelated repositories as part of this doc update. Each repository should keep its existing architecture and trigger policy unless independently verified and intentionally changed.

Applies to all agents and cross-chat handoffs, regardless of provider. Latest explicit owner instruction overrides contradictory historical 'never run CI' rhetoric.
