-- Explicit cleanup contract; execute only after confirming no objects remain.
BEGIN;
DO $$ BEGIN
  IF EXISTS (SELECT 1 FROM storage.objects WHERE bucket_id IN ('founder-truth-pack','opportunity-artifacts'))
  THEN RAISE EXCEPTION 'refusing bucket cleanup while objects remain'; END IF;
END $$;
DELETE FROM storage.buckets WHERE id IN ('founder-truth-pack','opportunity-artifacts');
COMMIT;
