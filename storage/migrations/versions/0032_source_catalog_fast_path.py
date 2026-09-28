"""Expose the scheduled/manual source catalog without opportunity counts."""
from typing import Sequence, Union

from alembic import op


revision: str = "0032_source_catalog_fastpath"
down_revision: Union[str, None] = "0031_source_overview_fastpath"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, None] = None


_SOURCE_CATALOG = """
CREATE VIEW public.founder_source_catalog
WITH (security_invoker = true)
AS
WITH scheduled AS (
  SELECT split_part(s.source_id::text, ':', 1) AS source_family,
         s.source_id,
         s.last_success_at,
         s.last_status::text AS last_status,
         s.next_due_at,
         false AS manual_only
    FROM public.source_schedules s
), manual AS (
  SELECT families.source_family,
         NULL::varchar(128) AS source_id,
         NULL::timestamp without time zone AS last_success_at,
         NULL::text AS last_status,
         NULL::timestamp without time zone AS next_due_at,
         true AS manual_only
    FROM (VALUES
      ('ai_jobs_net'), ('arc_dev'), ('bayt'), ('cambly'), ('chegg'),
      ('contra'), ('freelancer'), ('gulftalent'), ('indeed'), ('jobicy'),
      ('justremote'), ('khamsat'), ('linkedin'), ('mostaql'), ('naukrigulf'),
      ('otta'), ('peopleperhour'), ('preply'), ('reddit'), ('remote_co'),
      ('superprof'), ('toptal'), ('tutor'), ('upwork'), ('wellfound'),
      ('working_nomads'), ('wuzzuf'), ('wyzant'), ('ycombinator')
    ) AS families(source_family)
)
SELECT * FROM scheduled
UNION ALL
SELECT * FROM manual
"""


def upgrade() -> None:
    op.execute(_SOURCE_CATALOG)
    op.execute("REVOKE ALL ON public.founder_source_catalog FROM PUBLIC")
    op.execute("""
      DO $$ BEGIN
        IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='anon') THEN
          REVOKE ALL ON public.founder_source_catalog FROM anon;
        END IF;
        IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='authenticated') THEN
          REVOKE ALL ON public.founder_source_catalog FROM authenticated;
          GRANT SELECT ON public.founder_source_catalog TO authenticated;
        END IF;
      END $$
    """)


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS public.founder_source_catalog")
