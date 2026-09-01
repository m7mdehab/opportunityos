# ADR-0012 — Single-Founder Tenancy Through Phase 5

- **Status:** Accepted
- **Date:** 2026-09-02
- **Phase:** BRIEF-FR-003
- **Supersedes:** none
- **Superseded by:** none

## Context

OpportunityOS Phase 0 through Phase 5 (Founder Alpha 0 through Founder Alpha 4)
serve exactly one founder against one PostgreSQL persistence backbone
(`storage/models.py`, migrated with Alembic). The relational schema was built
for that single-workspace reality: most tables carry no tenant identifier at
all, and the two tables that do carry a `workspace` column use it as an
opaque grouping key inside one founder's data, not as an enforced isolation
boundary — no repository, query, or index in `storage/` currently scopes a
read or write by `workspace`.

A mechanical inspection of `storage/models.py` (`Base.metadata.sorted_tables`
and each table's column set) confirms the current state precisely:

- **11** model tables exist in total.
- **2** carry a `workspace` column: `idempotency_reservations`,
  `outbound_actions`.
- **9** carry no tenant key of any kind: `opportunities`,
  `field_provenances`, `inbound_evidence`, `pipeline_events`,
  `founder_notifications`, `inbox_checkpoints`, `reconciliation_records`,
  `worker_jobs`, `founder_feedback`.

Even where a `workspace` column exists, no query path filters by it, so the
column today records provenance rather than enforcing isolation. Treating
this schema as already multi-tenant would be a false claim: any second
workspace's rows would sit in the same tables, addressable through the same
unscoped queries, with no boundary preventing one workspace's data from being
read or mutated through another workspace's session.

`docs/MASTER_PLAN.md` places Phase 6 (Multi-Tenant Family Alpha) strictly
after Founder Web Alpha is live and validated (`docs/STATE.md`, Blocked
Items). This ADR makes the persistence-layer half of that blocker explicit
and mechanically checkable, so it cannot be silently assumed away by a
future brief.

## Decision

1. Phase 0 through Phase 5 persistence is **single-workspace by
   construction**. The schema, the repository layer, and every query path in
   `storage/` are authorized to serve one founder's data only; they carry no
   tenant-isolation guarantee.
2. The 9 tables enumerated above have no workspace key and cannot be
   scoped to a tenant without a schema migration. The 2 tables that do carry
   a `workspace` column (`idempotency_reservations`, `outbound_actions`) are
   not to be read as evidence of multi-tenant readiness: the column is
   unenforced by any query path today.
3. Entry to Phase 6 (Multi-Tenant Family Alpha) **requires a dedicated
   tenancy migration brief** before any multi-tenant data is stored. That
   brief must, at minimum: add a tenant key to all 9 unscoped tables, enforce
   tenant scoping at every read and write path (not by convention but by
   construction — e.g., a repository that cannot construct a query without a
   tenant identifier), migrate and backfill existing single-founder data into
   its own tenant record, and add adversarial tests proving one tenant's
   session cannot read or mutate another tenant's rows.
4. Until that migration brief lands and passes its own gate, no code path
   may store a second workspace's data in this schema, and no report may
   describe the persistence layer as multi-tenant.

## Consequences

- **Positive:** the single-founder scope of Phase 0–5 persistence is now a
  recorded, mechanically-derived decision rather than an implicit assumption;
  the exact remediation surface (9 tables) is enumerated for the future
  tenancy brief to scope against.
- **Positive:** `reports/FOUNDER_READINESS_MATRIX.json` can carry an accurate
  note against the persistence requirement instead of implying tenancy work
  is further along than it is.
- **Negative:** Phase 6 cannot begin as a thin feature layer on the existing
  schema; it requires a migration brief with its own acceptance gate,
  extending the critical path to Family Alpha.
- **Security:** explicitly naming the absence of tenant isolation prevents a
  future contributor from assuming the existing `workspace` columns are a
  safe isolation boundary and building multi-tenant features on top of them
  before the migration lands.
- **Privacy:** no founder or family-member personal data may be stored under
  a second tenant identity in this schema until isolation is enforced by
  construction, not convention.
- **Cost / operational:** none beyond the deferred migration effort already
  implied by the Phase 6 gate in `docs/MASTER_PLAN.md`.

## Alternatives considered

- **Treat the existing `workspace` column as sufficient and proceed to
  Phase 6 directly.** Rejected: the column is present on only 2 of 11
  tables and enforced by no query path, so this would silently store
  multi-tenant data in a schema that cannot isolate it.
- **Add a `workspace` column to all 11 tables now, ahead of Phase 6.**
  Rejected as out of scope for this brief: `storage/`, `worker/`, and
  `scripts/backup_restore.py` are frozen except where a named deliverable
  requires a change, and schema migration is exactly the kind of change a
  dedicated tenancy brief — with its own council review, migration
  round-trip proof, and adversarial isolation tests — should own rather than
  absorbing it as a side effect of a reconciliation brief.
- **Say nothing and let Phase 6 discover the gap when it starts.** Rejected:
  the independent audit that produced this brief flagged the readiness
  matrix's persistence claims as overstated; recording the gap explicitly is
  the fix.

## Required tests and rollback

- **Verification:** the 2-of-11 / 9-table split in this ADR is derived
  mechanically from `storage/models.py` via `Base.metadata.sorted_tables`
  and each table's column names; any future change to that split must update
  this ADR or supersede it. `python scripts/check_repository.py` verifies
  this ADR carries a valid `Status` field.
- **Rollback:** this ADR records a decision about the current schema; it
  makes no code change and has nothing to revert. If a future tenancy
  migration brief changes the underlying facts, it must supersede this ADR
  rather than editing it in place.
