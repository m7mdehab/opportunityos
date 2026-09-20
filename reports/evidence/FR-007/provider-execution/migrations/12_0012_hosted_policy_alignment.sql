BEGIN;

-- Running upgrade 0011_hosted_api_surface -> 0012_hosted_policy_alignment

DO $$ BEGIN
              IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='authenticated') THEN
                EXECUTE 'DROP POLICY IF EXISTS source_poll_runs_browser_deny_authenticated ON public.source_poll_runs';
                EXECUTE 'DROP POLICY IF EXISTS source_poll_runs_founder_authenticated_read ON public.source_poll_runs';
                EXECUTE 'CREATE POLICY source_poll_runs_founder_authenticated_read ON public.source_poll_runs '
                     || 'FOR SELECT TO authenticated USING (public.opos_is_founder())';
                EXECUTE 'GRANT SELECT ON public.source_poll_runs TO authenticated';
              END IF;
            END $$;

DO $$ BEGIN
              IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='authenticated') THEN
                EXECUTE 'DROP POLICY IF EXISTS opportunities_browser_deny_authenticated ON public.opportunities';
                EXECUTE 'DROP POLICY IF EXISTS opportunities_founder_authenticated_read ON public.opportunities';
                EXECUTE 'CREATE POLICY opportunities_founder_authenticated_read ON public.opportunities '
                     || 'FOR SELECT TO authenticated USING (public.opos_is_founder())';
                EXECUTE 'GRANT SELECT ON public.opportunities TO authenticated';
              END IF;
            END $$;

DO $$ BEGIN
              IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='authenticated') THEN
                EXECUTE 'DROP POLICY IF EXISTS match_evaluations_browser_deny_authenticated ON public.match_evaluations';
                EXECUTE 'DROP POLICY IF EXISTS match_evaluations_founder_authenticated_read ON public.match_evaluations';
                EXECUTE 'CREATE POLICY match_evaluations_founder_authenticated_read ON public.match_evaluations '
                     || 'FOR SELECT TO authenticated USING (public.opos_is_founder())';
                EXECUTE 'GRANT SELECT ON public.match_evaluations TO authenticated';
              END IF;
            END $$;

DO $$ BEGIN
              IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='authenticated') THEN
                EXECUTE 'DROP POLICY IF EXISTS founder_cv_selections_browser_deny_authenticated ON public.founder_cv_selections';
                EXECUTE 'DROP POLICY IF EXISTS founder_cv_selections_founder_authenticated_read ON public.founder_cv_selections';
                EXECUTE 'CREATE POLICY founder_cv_selections_founder_authenticated_read ON public.founder_cv_selections '
                     || 'FOR SELECT TO authenticated USING (public.opos_is_founder())';
                EXECUTE 'GRANT SELECT ON public.founder_cv_selections TO authenticated';
              END IF;
            END $$;

DO $$ BEGIN
              IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='authenticated') THEN
                EXECUTE 'DROP POLICY IF EXISTS founder_filter_settings_browser_deny_authenticated ON public.founder_filter_settings';
                EXECUTE 'DROP POLICY IF EXISTS founder_filter_settings_founder_authenticated_read ON public.founder_filter_settings';
                EXECUTE 'CREATE POLICY founder_filter_settings_founder_authenticated_read ON public.founder_filter_settings '
                     || 'FOR SELECT TO authenticated USING (public.opos_is_founder())';
                EXECUTE 'GRANT SELECT ON public.founder_filter_settings TO authenticated';
              END IF;
            END $$;

DO $$ BEGIN
              IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='authenticated') THEN
                EXECUTE 'DROP POLICY IF EXISTS founder_facets_browser_deny_authenticated ON public.founder_facets';
                EXECUTE 'DROP POLICY IF EXISTS founder_facets_founder_authenticated_read ON public.founder_facets';
                EXECUTE 'CREATE POLICY founder_facets_founder_authenticated_read ON public.founder_facets '
                     || 'FOR SELECT TO authenticated USING (public.opos_is_founder())';
                EXECUTE 'GRANT SELECT ON public.founder_facets TO authenticated';
              END IF;
            END $$;

DO $$ BEGIN
              IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='authenticated') THEN
                EXECUTE 'DROP POLICY IF EXISTS founder_saved_views_browser_deny_authenticated ON public.founder_saved_views';
                EXECUTE 'DROP POLICY IF EXISTS founder_saved_views_founder_authenticated_read ON public.founder_saved_views';
                EXECUTE 'CREATE POLICY founder_saved_views_founder_authenticated_read ON public.founder_saved_views '
                     || 'FOR SELECT TO authenticated USING (public.opos_is_founder())';
                EXECUTE 'GRANT SELECT ON public.founder_saved_views TO authenticated';
              END IF;
            END $$;

REVOKE ALL ON public.founder_opportunity_detail FROM PUBLIC;

DO $$ BEGIN
              IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='anon') THEN
                EXECUTE 'REVOKE ALL ON public.founder_opportunity_detail FROM anon';
              END IF;
              IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='authenticated') THEN
                EXECUTE 'REVOKE ALL ON public.founder_opportunity_detail FROM authenticated';
                EXECUTE 'GRANT SELECT ON public.founder_opportunity_detail TO authenticated';
              END IF;
            END $$;

REVOKE ALL ON public.founder_cv_selection FROM PUBLIC;

DO $$ BEGIN
              IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='anon') THEN
                EXECUTE 'REVOKE ALL ON public.founder_cv_selection FROM anon';
              END IF;
              IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='authenticated') THEN
                EXECUTE 'REVOKE ALL ON public.founder_cv_selection FROM authenticated';
                EXECUTE 'GRANT SELECT ON public.founder_cv_selection TO authenticated';
              END IF;
            END $$;

REVOKE ALL ON public.founder_filters FROM PUBLIC;

DO $$ BEGIN
              IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='anon') THEN
                EXECUTE 'REVOKE ALL ON public.founder_filters FROM anon';
              END IF;
              IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='authenticated') THEN
                EXECUTE 'REVOKE ALL ON public.founder_filters FROM authenticated';
                EXECUTE 'GRANT SELECT ON public.founder_filters TO authenticated';
              END IF;
            END $$;

REVOKE ALL ON public.founder_facet_settings_view FROM PUBLIC;

DO $$ BEGIN
              IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='anon') THEN
                EXECUTE 'REVOKE ALL ON public.founder_facet_settings_view FROM anon';
              END IF;
              IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='authenticated') THEN
                EXECUTE 'REVOKE ALL ON public.founder_facet_settings_view FROM authenticated';
                EXECUTE 'GRANT SELECT ON public.founder_facet_settings_view TO authenticated';
              END IF;
            END $$;

REVOKE ALL ON public.founder_saved_view_records FROM PUBLIC;

DO $$ BEGIN
              IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='anon') THEN
                EXECUTE 'REVOKE ALL ON public.founder_saved_view_records FROM anon';
              END IF;
              IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='authenticated') THEN
                EXECUTE 'REVOKE ALL ON public.founder_saved_view_records FROM authenticated';
                EXECUTE 'GRANT SELECT ON public.founder_saved_view_records TO authenticated';
              END IF;
            END $$;

UPDATE alembic_version SET version_num='0012_hosted_policy_alignment' WHERE alembic_version.version_num = '0011_hosted_api_surface';

COMMIT;

