# FR-007 Owner Work Order W1.1/W1.2 — Persisted Feed Projection and SQL Query Path

## Purpose

Replace request-time corpus-wide Python filtering/cache dependence with an indexed persisted feed projection while preserving current OpportunityOS qualification/truth/provenance semantics.

This is the architecture-sensitive owner track. It is intentionally disjoint from W0.3 runtime configuration work.

## Scope

1. Inspect the current opportunity/evaluation/founder-view schema and exact feed/filter implementation on the FR-007 branch.
2. Define the minimum durable `feed_projection` schema required to serve the current Founder Alpha feed, search, facets, decision filters, score ranges, hidden visibility, saved views, pagination, and ranking without hydrating the full corpus in Python.
3. Add an Alembic migration and ORM/repository model for the projection, with indexes justified by the current query surface.
4. Add deterministic projection construction/update logic bound to opportunity content hash + truth/profile hash/version + evaluator/projection version.
5. Backfill current canonical opportunity/evaluation state into the projection without repolling sources.
6. Route the normal feed/query path through indexed SQL against the projection.
7. Keep any process cache optional only; a cold process must return the same logical result and must not require warming the corpus.
8. Add regression/query-shape tests proving default feed, decision/min-score filters, search/facets, and pagination do not perform full-corpus Python hydration.

## Invariants

- `UNKNOWN != FALSE` and existing qualification/truth semantics remain unchanged.
- No source permissions, source identities, truth-lock, artifact validation, or outbound action authority change.
- No private founder data enters Git.
- No weakening of current filters/tests to obtain speed.
- Existing canonical opportunity/evaluation tables remain authoritative inputs; `feed_projection` is derived/read-optimized state.
- Projection rebuild/update must be deterministic and restart-safe.
- This work does not provision Supabase or any external provider.

## Initial acceptance focus

- first cold feed request does not require corpus cache warm-up;
- default feed/common filters use SQL projection access;
- repeated projection rebuild is idempotent;
- projection rows are invalidated/rebuilt when opportunity content hash or active truth/profile hash changes;
- pagination is stable and deterministic;
- full existing backend tests remain green after focused projection tests.

Exact commands/evidence will be finalized after schema/query inspection before implementation.