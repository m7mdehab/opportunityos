# W16A-CODEX — Supabase Provider-Execution Bundle

Status: ACTIVE
Owner/closure authority: Overseer
Executor: Codex
Base integration SHA: `8557397d200651ba6d5988ed2699180d4404fbfb`

## Safe Hosted Target

- provider: Supabase
- project: `opportunityos-staging`
- project ref: `lrrcpwaapwynzdsxzwhy`
- region: `eu-central-1`
- safe API origin: `https://lrrcpwaapwynzdsxzwhy.supabase.co`
- database engine: PostgreSQL 17
- initial public tables: 0
- initial project migrations: 0
- project creation cost at provisioning: $0/month

No database password, service-role key, storage secret, Founder credential, session secret, or private Truth Pack content is available to or required from this work order.

## End Goal

Produce a deterministic, tested, provider-executable W16A bundle that the Overseer can apply to the real Supabase target through the authenticated Supabase connection without manually translating repository migrations or inventing validation queries.

This executor does NOT own live Supabase mutation. Provider mutation is intentionally routed to the Overseer because the Codex execution environment has no authenticated Supabase management surface.

The executor owns the repository package end-to-end and returns only when that package is complete.

## Required Bundle

1. deterministic current-head schema migration SQL generated from canonical Alembic authority, ordered by revision and suitable for Supabase/PostgreSQL 17 execution;
2. explicit migration manifest with revision, SHA-256 and expected post-state;
3. hosted RLS verification SQL proving policy state for application/auth tables and browser roles;
4. backend-owner verification SQL;
5. private Supabase Storage bootstrap SQL/contract for the Truth Pack and artifact buckets, with public access disabled and no object body or secret committed;
6. source export/import/parity tooling that accepts runtime source/target connections and preserves FR-007 canonical state without embedding credentials;
7. sanitized evidence templates/manifest contracts for the Overseer to populate from live execution;
8. deterministic tests proving the bundle on disposable PostgreSQL 17 and Supabase-like roles where applicable;
9. exact operator runbook mapping each generated SQL/evidence artifact to the authenticated Supabase operation the Overseer must execute.

## Hard Requirements

- Alembic remains schema authority; generated SQL must be mechanically derived, not hand-maintained as a second schema.
- no `psql` meta-commands or shell-only syntax in provider SQL artifacts;
- no secrets/private Founder data in Git, tests, logs, SQL, docs or evidence;
- no weakening RLS/auth/security to simplify hosted execution;
- no hosted PASS claims from repository tests;
- local Docker/psql/Supabase CLI absence is not a blocker; use repository CI/PR proof where required;
- generic PARTIAL is forbidden.

## Terminal Result

PASS only when the repository/provider-execution bundle is complete and all locally executable checks pass.

If the only remaining proof is the already-open PR CI, return:
`REPOSITORY_PASS / OVERSEER_CI_HANDOFF`
with exact head SHA and required checks.

Do not return HARD_BLOCKED for missing Supabase credentials: live provider mutation is explicitly outside this executor's task.
