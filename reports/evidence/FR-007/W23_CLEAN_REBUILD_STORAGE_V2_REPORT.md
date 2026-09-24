# W23 Clean Rebuild — Storage V2 Terminal Evidence

## Outcome and scope

W23 completed on branch `work/fr007-clean-rebuild-storage-v2` without merging. The deleted Supabase project was not recovered or reused. OpportunityOS now runs on the replacement Supabase Free project `sunjfepvdzfknglrjwhm` in `eu-central-1`, with private Supabase Storage and a direct-tier ingestion path. No paid infrastructure was introduced.

The replacement project was already provisioned at $0/month by the Overseer. The live database is a writable primary at Alembic head `0025_current_feed_fast_path`. The credential itself was not read, changed, or included in this report. **Required post-completion Founder action:** rotate the replacement project's database password and update the protected `fr007-staging` URLs. This security follow-up did not block the authorized execution.

Seven-day soak is **not claimed**.

## Architecture delivered

- `0022_storage_v2_direct_tiering`: classifies normalized and evaluated source records in worker memory before persistence. HOT records retain compact operational/search/feed state; eligible terminal cold records persist compact identity/current-decision metadata in PostgreSQL and lossless source truth in compressed private object storage.
- `0023_alembic_access`: hardens the internal Alembic control table against browser-role access while preserving migration operation.
- `0024_founder_jwt_claims`: supports the current Founder JWT claim contract.
- `0025_current_feed_fast_path`: uses the single-current-projection invariant for the security-invoker Founder feed and removes the obsolete full-ranking path.
- One current feed projection per interactive opportunity; one current evaluation per opportunity. No synthetic `truth_pack_hash='active'` feed population and no full-description/search-text copy per projection.
- Cold source truth, provenance, and required archived detail are compressed into immutable content-version objects in private `opportunity-artifacts`. Cold PostgreSQL rows have no description, raw payload, row-per-field provenance, or verbose evaluation detail. Archive identity and SHA-256 integrity were checked; corrupt/missing archives fail closed. Truth-pack/content-change re-evaluation hydrates verified archives in memory and does not persist placeholder text as scored input.
- Compact search remains on the canonical opportunity representation; the feed fast path removed unnecessary ranking over historical projection versions.
- Canonical CV portfolio remained private in `founder-cv-portfolio`; all 31 canonical objects were verified against their manifest hashes.

## Recovery and deployment path

The replacement clean project was used instead of attempting to rehabilitate or restore the deleted, oversized physical database. The current project is healthy and writable. PostgreSQL CI proved fresh migration and upgrade paths, and the replacement project's migration chain was applied through revision `0025_current_feed_fast_path`.

Key hosted evidence:

| Evidence | Run | Result |
|---|---:|---|
| PostgreSQL 16/17 Storage V2 + migration acceptance, including final migration repair | `36062643183` | PASS |
| OCI container + PostgreSQL queue durability | `35799462891` | PASS |
| Canonical 31-object private CV hash verification | `35799588764` | PASS |
| Representative Himalayas direct-tier gate | `35835117460` | PASS |
| Final whole-corpus archive checksum and physical capacity proof | `36048920767` | PASS; single approved whole-corpus pass |
| Founder staging smoke on replacement project | `36062166122` | PASS |
| Final exact five-shard runtime acceptance and FULL monitor | `36067068955` | PASS |

Bounded bootstrap slices `35993735392` (offset 125/max 125) and `36014460330` (offset 250/max 93) completed successfully. The final successful-source corpus contains 343 read-allowed source identities. The full-corpus proof used bounded archive pages and verified checksums/identity/size; it did not write to the live database or read live source payload text. Ingestion ran at no more than five concurrent source workers. Successful sources were not restarted. Source-specific failures were classified by the bounded runner; no unresolved queue/dead-letter failures remained at acceptance.

## Footprint and economics

The historical failed project measured approximately 1,503 MiB. Final physical `pg_database_size` on the replacement is `188,656,787` bytes = **179.92 MiB**, a reduction of approximately **88.03%** from that baseline. This is below the 200 MiB hard acceptance limit by `21,058,413` bytes (20.08 MiB). It is within the bounded capacity model but above the preferred 150 MiB target; the measured physical size, not a modeled smaller number, is reported.

Final aggregate counts:

| Measure | Final |
|---|---:|
| Opportunities | 27,525 |
| HOT / interactive | 2,765 |
| COLD | 24,760 |
| Protected in the bootstrap sample | 0 |
| Founder activity events after staging smoke | 9 events across 4 opportunities |
| Founder feedback / triage state / views / outbound actions | 0 / 3 / 0 / 0 |
| Current feed projections | 2,765 |
| Current evaluations | 27,525 |
| Synthetic active feed projections | 0 |
| Cold archive objects | 24,760 |
| Compressed cold object bytes | 179,555,835 (171.21 MiB) |
| Average compressed bytes per cold opportunity | 7,252 |
| Queue pending / retry / running / dead-letter / expired | 0 / 0 / 0 / 0 / 0 |
| Oldest due runnable | none |

The private CV bucket contained the 31 canonical verified portfolio objects (2,163,348 bytes); the live bucket metadata also retained one harmless zero-byte folder marker. It was not included in cold archive economics. No source-corpus download was used for routine monitoring. The final whole-corpus integrity pass was the only full archive/object payload verification.

### Final largest relations

The live relation sizes below are the terminal acceptance snapshot. Heap, index, and total are bytes.

| Relation | Heap | Index | Total |
|---|---:|---:|---:|
| `storage.objects` | 17,940,480 | 36,339,712 | 54,321,152 |
| `public.opportunities` | 25,763,840 | 12,640,256 | 50,446,336 |
| `public.match_evaluations` | 15,360,000 | 7,200,768 | 26,542,080 |
| `public.opportunity_cold_archive` | 9,101,312 | 9,846,784 | 18,989,056 |
| `public.field_provenances` | 9,175,040 | 7,512,064 | 16,867,328 |
| `public.feed_projection` | 4,587,520 | 1,515,520 | 6,144,000 |
| `public.founder_cv_selections` | 827,392 | 229,376 | 1,097,728 |
| `public.source_poll_runs` | 81,920 | 147,456 | 262,144 |
| `public.worker_jobs` | 73,728 | 106,496 | 221,184 |
| `public.source_schedules` | 57,344 | 65,536 | 163,840 |
| `public.founder_identity` | 8,192 | 49,152 | 57,344 |
| `public.founder_notifications` | 0 | 49,152 | 57,344 |
| `public.outbound_actions` | 0 | 49,152 | 57,344 |
| `public.pipeline_events` | 0 | 49,152 | 57,344 |
| `public.reconciliation_records` | 0 | 40,960 | 49,152 |
| `public.founder_activity_events` | 8,192 | 32,768 | 49,152 |
| `storage.buckets` | 8,192 | 32,768 | 49,152 |
| `public.founder_auth_events` | 0 | 40,960 | 40,960 |
| `public.founder_sessions` | 0 | 40,960 | 40,960 |
| `public.founder_triage_states` | 8,192 | 32,768 | 40,960 |

Current live top indexes (bytes) were measured from PostgreSQL catalogs after Founder smoke: `storage.objects.objects_bucket_id_name_version_key` 7,733,248; `public.field_provenances.uq_field_provenances_identity` 6,193,152; `storage.objects.idx_objects_bucket_id_name` 5,832,704; `storage.objects.idx_objects_bucket_id_name_lower` 5,816,320; `storage.objects.idx_objects_current_version` and `idx_objects_null_version` 5,488,640 each; `storage.objects.name_prefix_search` 4,751,360; `public.opportunity_cold_archive.ix_opportunity_cold_archive_object_key` 4,726,784; `public.opportunities.ix_opportunities_content_hash` 3,596,288; `public.opportunity_cold_archive.ix_opportunity_cold_archive_content_hash` 3,072,000; and `public.opportunities.ix_opportunities_search_tsv` 2,850,816. The live list is recorded separately from isolated benchmark index sizes.

The accepted representative Himalayas gate received 20 raw / 20 unique records. It classified 7 HOT and 33 COLD after the gate, created 16 new archive objects / 74,802 compressed bytes, and verified all 33 source-scoped cold objects at 151,049 bytes. Live DB growth for that gate was 303,104 bytes. Its final-revision conservative 26k physical benchmark projected 197.26 MiB, under the hard limit; the later successful-corpus physical reforecast and final live measurement supersede that initial sample projection. Full bootstrap ended at 27,525 opportunities, with 24,760 cold objects totaling 179,555,835 compressed bytes.

## Data integrity, product, and security checks

- No cold description/raw payload, relational provenance, or verbose cold evaluation remained in PostgreSQL; cold reason representation was bounded to 94 bytes in the tested contract.
- Maximum current projections/opportunity = 1; maximum current evaluations/opportunity = 1; synthetic active projections = 0.
- Cold object content hash, archive identity, and object size were verified in the final bounded full-corpus proof. No corpus-wide Storage download was used outside that one final integrity pass; no placeholder `[archived]` content was scored.
- Founder-interacted/product-protected records are retained by lifecycle rules; the final aggregate reports 9 immutable activity events across 4 opportunities and 3 triage-state rows, with zero feedback, views, or outbound actions. `lifecycle_tier='protected'` count was 0; the UI smoke actions remained represented in Founder activity/triage state. No application/outbound or Founder activity row was manually edited. Founder staging smoke exercised authenticated login, feed/filter/search, detail, dismiss and clear-history activity, current CV selection, and private CV preview/download. The browser test performed no poll or source-work trigger.
- Canonical 31 CV object SHA-256 values passed hosted verification (`35799588764`). The archived earlier CV proof referencing the deleted project is historical evidence and was left unchanged.
- `public.alembic_version` access hardening was included narrowly in `0023_alembic_access`; migration operation and exactly-one-head migration CI remained intact.
- No manual worker-row edits, no silent source-truth deletion, no credential values in logs/reports, and no paid infrastructure.

## Queue, protected worker proof, monitor, and incident

Final acceptance run `36067068955` used exactly five shards, each with the normal 30-job / 480-second settings, within the existing 35-minute job envelope. All five shards succeeded. The queue was already naturally empty, so no artificial job was inserted and the observer correctly recorded:

| Observer metric | Result |
|---|---:|
| Maximum tagged worker DB connections | 0 (contract ceiling <=10) |
| Persistent idle-in-transaction | 0 |
| Unattributed PostgreSQL connections | 0 |
| Observer probe failures | 0 |

The aggregate proof reported status PASS and error deltas from proof start were all zero: `EMAXCONNSESSION`, `UniqueViolation`, and `ReadOnlySqlTransaction`. Queue/capacity snapshot: database `188,656,787` bytes, expired leases 0, due runnable 0 (therefore oldest due absent / below 900 seconds), dead letters 0. The final queue had no pending, retry, running, or expired jobs.

The same run executed the FULL monitor successfully. The monitor emitted normal `RESOLVE` (`synthetic=False`) and successfully resolved/closed Issue #137 through the incident processor. It was not manually closed.

## Final-state limitations and follow-up

- Database password rotation is a required Founder security action immediately after execution; no credential was touched in this sprint's final phase.
- There is no seven-day soak result and none is claimed.
- The organization egress budget was treated as scarce; verification was bounded and no routine full-corpus payload download was performed.
- No merge was made. The final repository commit is reserved for `docs/STATE.md` only, after the report/checkpoint are committed and all evidence is stable.
