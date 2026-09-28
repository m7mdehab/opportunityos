"""expose family keys for composed hosted recommendations

Revision ID: 0033_hosted_feed_family_key
Revises: 0032_source_catalog_fastpath
Create Date: 2026-09-29 02:26:25.497868

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '0033_hosted_feed_family_key'
down_revision: Union[str, None] = '0032_source_catalog_fastpath'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
      CREATE VIEW public.founder_feed_fr008_diversity
      WITH (security_invoker = true)
      AS
      SELECT feed.*, opportunity.family_key
        FROM public.founder_feed_fr008 AS feed
        JOIN public.opportunities AS opportunity
          ON opportunity.id::text = feed.opportunity_id::text
    """)
    op.execute("REVOKE ALL ON public.founder_feed_fr008_diversity FROM PUBLIC")
    op.execute("""
      DO $$ BEGIN
        IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='anon') THEN
          REVOKE ALL ON public.founder_feed_fr008_diversity FROM anon;
        END IF;
        IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='authenticated') THEN
          REVOKE ALL ON public.founder_feed_fr008_diversity FROM authenticated;
          GRANT SELECT ON public.founder_feed_fr008_diversity TO authenticated;
        END IF;
      END $$
    """)
    op.execute("NOTIFY pgrst, 'reload schema'")


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS public.founder_feed_fr008_diversity")
