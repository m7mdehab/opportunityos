-- Supabase Storage bootstrap contract. Execute only after migration.
-- No object bodies or credentials are present. Both buckets must remain private.
BEGIN;
INSERT INTO storage.buckets (id, name, public)
VALUES ('founder-truth-pack', 'founder-truth-pack', false),
       ('opportunity-artifacts', 'opportunity-artifacts', false)
ON CONFLICT (id) DO UPDATE SET public = false, name = EXCLUDED.name;
COMMIT;
SELECT id, name, public FROM storage.buckets
 WHERE id IN ('founder-truth-pack', 'opportunity-artifacts') ORDER BY id;
