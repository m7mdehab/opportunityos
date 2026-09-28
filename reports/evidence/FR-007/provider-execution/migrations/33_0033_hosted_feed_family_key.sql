BEGIN;

-- Running upgrade 0032_source_catalog_fastpath -> 0033_hosted_feed_family_key

CREATE VIEW public.founder_feed_fr008_diversity
      WITH (security_invoker = true)
      AS
      SELECT feed.*, opportunity.family_key
        FROM public.founder_feed_fr008 AS feed
        JOIN public.opportunities AS opportunity
          ON opportunity.id::text = feed.opportunity_id::text;

REVOKE ALL ON public.founder_feed_fr008_diversity FROM PUBLIC;

DO $$ BEGIN
        IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='anon') THEN
          REVOKE ALL ON public.founder_feed_fr008_diversity FROM anon;
        END IF;
        IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='authenticated') THEN
          REVOKE ALL ON public.founder_feed_fr008_diversity FROM authenticated;
          GRANT SELECT ON public.founder_feed_fr008_diversity TO authenticated;
        END IF;
      END $$;

NOTIFY pgrst, 'reload schema';

UPDATE alembic_version SET version_num='0033_hosted_feed_family_key' WHERE alembic_version.version_num = '0032_source_catalog_fastpath';

COMMIT;

