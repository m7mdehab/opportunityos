-- Read-only parity/integrity query plan. Capture JSON output from
-- scripts/migration_baseline.py for source and target, then compare it with:
-- python scripts/migration_baseline.py compare source.json target.json
SELECT version_num AS alembic_revision FROM public.alembic_version;
SELECT 'opportunities' AS relation, count(*) FROM public.opportunities
UNION ALL SELECT 'field_provenances', count(*) FROM public.field_provenances
UNION ALL SELECT 'match_evaluations', count(*) FROM public.match_evaluations
UNION ALL SELECT 'feed_projection', count(*) FROM public.feed_projection
UNION ALL SELECT 'artifact_cache', count(*) FROM public.artifact_cache;
SELECT opportunity_id, truth_pack_hash, qualification_decision
  FROM public.match_evaluations ORDER BY opportunity_id, truth_pack_hash;
