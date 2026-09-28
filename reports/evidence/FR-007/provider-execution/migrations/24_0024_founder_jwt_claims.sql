BEGIN;

-- Running upgrade 0023_alembic_access -> 0024_founder_jwt_claims

CREATE OR REPLACE FUNCTION public.opos_is_founder()
        RETURNS boolean
        LANGUAGE sql
        STABLE
        SECURITY DEFINER
        SET search_path = public
        AS $$
          SELECT EXISTS (
            SELECT 1
            FROM public.founder_identity AS founder
            WHERE founder.id = 'singleton'
              AND founder.supabase_user_id = COALESCE(
                NULLIF(current_setting('request.jwt.claim.sub', true), ''),
                NULLIF(current_setting('request.jwt.claims', true), '')::jsonb ->> 'sub'
              )
          )
        $$;

UPDATE alembic_version SET version_num='0024_founder_jwt_claims' WHERE alembic_version.version_num = '0023_alembic_access';

COMMIT;

