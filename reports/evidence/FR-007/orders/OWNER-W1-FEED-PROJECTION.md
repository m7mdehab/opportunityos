# Owner Work Order — W1 Feed Projection

## Scope

Owner/Overseer implements the first Wave 1 slice in parallel with CODEX-W0-CONFIG:

- persisted founder feed projection schema/model contract;
- backfill/update service for projection rows;
- SQL-native feed read path foundation;
- tests proving cold-cache correctness does not depend on process-local hidden/red-line caches.

## Frozen

Truth-lock, provenance, source-policy, action-authority, canonical opportunity identity, and existing Founder state semantics.

## Acceptance intent

- feed correctness survives process restart with empty in-memory caches;
- projection rows bind to opportunity content hash and current truth/profile hash;
- common decision/score/visibility filters can be expressed in SQL over persisted fields;
- no request-path source polling or evaluation is introduced;
- existing mandatory suites remain green before integration.

Implementation evidence will be added under `reports/evidence/FR-007/` before the work is called complete.