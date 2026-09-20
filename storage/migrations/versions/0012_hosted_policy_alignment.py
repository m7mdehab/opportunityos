"""0012_hosted_policy_alignment

Idempotent repair of the hosted Founder read policies introduced by 0011.

The first live staging application of 0011 pre-dated the final policy loop in
the repository copy, so the database could report Alembic head 0011 while
opportunities/match_evaluations/founder_cv_selections still retained the
authenticated deny policy. This revision makes the intended Founder-only
security-invoker view contract explicit and repeatable.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0012_hosted_policy_alignment"
down_revision: Union[str, None] = "0011_hosted_api_surface"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# This drift-repair revision does not change canonical Founder filter defaults.
_D3_FILTER_SEED_OVERRIDES: dict[str, dict[str, object]] = {}


_FOUNDER_READ_TABLES = (
    "source_poll_runs",
    "opportunities",
    "match_evaluations",
    "founder_cv_selections",
    "founder_filter_settings",
    "founder_facets",
    "founder_saved_views",
)

_FOUNDER_READ_VIEWS = (
    "founder_opportunity_detail",
    "founder_cv_selection",
    "founder_filters",
    "founder_facet_settings_view",
    "founder_saved_view_records",
)


def upgrade() -> None:
    for table in _FOUNDER_READ_TABLES:
        op.execute(
            f"""DO $$ BEGIN
              IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='authenticated') THEN
                EXECUTE 'DROP POLICY IF EXISTS {table}_browser_deny_authenticated ON public.{table}';
                EXECUTE 'DROP POLICY IF EXISTS {table}_founder_authenticated_read ON public.{table}';
                EXECUTE 'CREATE POLICY {table}_founder_authenticated_read ON public.{table} '
                     || 'FOR SELECT TO authenticated USING (public.opos_is_founder())';
                EXECUTE 'GRANT SELECT ON public.{table} TO authenticated';
              END IF;
            END $$"""
        )

    for view in _FOUNDER_READ_VIEWS:
        op.execute(f"REVOKE ALL ON public.{view} FROM PUBLIC")
        op.execute(
            f"""DO $$ BEGIN
              IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='anon') THEN
                EXECUTE 'REVOKE ALL ON public.{view} FROM anon';
              END IF;
              IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='authenticated') THEN
                EXECUTE 'REVOKE ALL ON public.{view} FROM authenticated';
                EXECUTE 'GRANT SELECT ON public.{view} TO authenticated';
              END IF;
            END $$"""
        )


def downgrade() -> None:
    # 0011's canonical contract already specifies these exact Founder-only
    # read policies and view grants. This revision repairs live drift rather
    # than introducing a different 0012 security model, so downgrade is
    # intentionally data-plane neutral.
    pass
