# OpportunityOS

OpportunityOS is an opportunity-acquisition platform for MENA. This private repository is the authoritative source for product governance, implementation, phase briefs, decisions, evidence, and reports.

Start with `AGENTS.md`, then read the generated `docs/STATE.md` and the active brief.

## Repository Foundation

This phase contains governance and repository automation only. It intentionally contains no application framework, server, database, deployment stack, source adapter, personal Truth Graph, or LLM integration.

The allowlisted documentation is published to the public, read-only `opportunityos-docs` mirror after passing the content guard.

## Local Push Checks

Run `bash scripts/install_hooks.sh` once per clone. The idempotent installer adds a pre-push hook that regenerates state and runs the same repository and guard checks as CI. The hook is advisory because `git push --no-verify` bypasses local hooks; ADR-0002 records the residual risk and revisit triggers.
