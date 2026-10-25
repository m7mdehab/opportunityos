# FR-007 storage recovery: first rollout

## Production baseline, 2026-10-08

- Total database: 409,128,083 bytes (about 390.2 MiB).
- Opportunities: 135,012,352 bytes.
- Match evaluations: 88,727,552 bytes.
- Field provenances: 85,647,360 bytes.
- Provenance unique index: 27,893,760 bytes.
- Cold external archives: 16,972 opportunities; preserve all originals.
- HOT and protected descriptions: about 68.4 MB physically stored.
- All provenance checksums were observed as lowercase 64-hex; opportunity IDs are not canonical hex.
- The source catch-up remains paused on a 390 MiB ceiling.

## Step 1 — safe measurements

Run the manual-only GitHub Action named FR-007 guarded storage reclamation
with operation audit. This reports numeric sizes and candidate rebuild
headroom. It does not export opportunity text or scores.

The optional one-index rebuild requires explicit confirmation, a database
that is writable, zero active worker jobs, and spare capacity under both the
internal hard stop and the provider limit. Do not override a blocked result.

At the measured baseline, the 27.9 MB provenance identity index rebuild is
expected to be blocked: the temporary-space estimate exceeds the project's
425 MiB internal hard stop.

## Step 2 — evidence before schema changes

On an isolated PostgreSQL instance, benchmark a compact binary checksum
index representation and compare exact uniqueness semantics. Preserve
original opportunity IDs and protect against format drift.

Benchmark LZ4 versus existing PGLZ compression using synthetic data with
representative lengths and cardinalities. Column compression settings
affect future writes, not existing stored values. Do not bulk-rewrite
production text to force compression.

## Step 3 — measured release gates

Apply only proven, lossless schema improvements with tested rollback,
query-plan regressions, and bounded temporary disk use. Never alter the
capacity thresholds, remove founder activity, or discard original source
payloads and archived objects.

Resume scheduled ingestion only after physical database size is below
350 MiB and post-operation source/evaluation correctness checks pass.
Target 300 MiB for durable headroom. If that is not achievable on the
Free Plan, present a larger-capacity option rather than bypassing safeguards.
