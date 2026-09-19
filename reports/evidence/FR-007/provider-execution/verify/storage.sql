-- Read-only Supabase Storage verification.
SELECT id, name, public FROM storage.buckets
 WHERE id IN ('founder-truth-pack', 'opportunity-artifacts') ORDER BY id;
SELECT policyname, roles, cmd, qual, with_check
  FROM pg_policies WHERE schemaname='storage' AND tablename='objects'
 ORDER BY policyname;
SELECT bucket_id, count(*) AS object_count
  FROM storage.objects
 WHERE bucket_id IN ('founder-truth-pack', 'opportunity-artifacts')
 GROUP BY bucket_id ORDER BY bucket_id;
-- From an unauthenticated browser client, GET the storage object endpoint and
-- expect denial. From the server-only client, fetch and verify SHA-256/size.
