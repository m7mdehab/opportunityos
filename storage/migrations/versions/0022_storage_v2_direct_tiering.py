"""Storage V2 direct tiering and one-current-read-model contract.

Fresh ingestion classifies in memory before persistence. Cold bodies and
provenance live in private object storage; PostgreSQL keeps only compact
identity/current-decision metadata. Feed and match state are current-only.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0022_storage_v2_direct_tiering"
down_revision: Union[str, None] = "0021_storage_v2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_D3_FILTER_SEED_OVERRIDES: dict[str, dict[str, object]] = {}


def upgrade() -> None:
    op.add_column(
        "opportunities",
        sa.Column("lifecycle_tier", sa.String(length=16), nullable=False, server_default="hot"),
    )
    op.create_check_constraint(
        "ck_opportunities_lifecycle_tier",
        "opportunities",
        "lifecycle_tier IN ('hot', 'cold', 'protected')",
    )
    op.create_index("ix_opportunities_lifecycle_tier", "opportunities", ["lifecycle_tier"])
    op.alter_column("opportunities", "lifecycle_tier", server_default=None)
    op.alter_column("opportunities", "description", existing_type=sa.Text(), nullable=True)
    op.alter_column("opportunity_cold_archive", "storage_backend", server_default="supabase_storage")
    op.alter_column("opportunity_cold_archive", "storage_backend", server_default=None)

    # Projections are reconstructable. Removing all prior copies prevents
    # synthetic 'active' rows and historical-pack duplicates surviving a
    # schema upgrade; the normal current-pack evaluator rebuilds one lean row.
    op.execute("TRUNCATE TABLE feed_projection")
    op.drop_constraint(
        "uq_feed_projection_opportunity_truth_pack", "feed_projection", type_="unique"
    )
    op.drop_column("feed_projection", "search_text")
    op.drop_column("feed_projection", "search_tsv")
    op.create_unique_constraint(
        "uq_feed_projection_current_opportunity", "feed_projection", ["opportunity_id"]
    )

    # Retain only the most recent evaluation per opportunity, then make the
    # current evaluation mutable in place as truth packs change.
    op.execute(
        """DELETE FROM match_evaluations m USING (
             SELECT id, row_number() OVER (
               PARTITION BY opportunity_id
               ORDER BY evaluated_at DESC, created_at DESC, id DESC
             ) AS rn
             FROM match_evaluations
           ) ranked
           WHERE m.id = ranked.id AND ranked.rn > 1"""
    )
    op.add_column("match_evaluations", sa.Column("content_hash", sa.String(length=64), nullable=True))
    op.execute(
        """UPDATE match_evaluations m
           SET content_hash = o.content_hash
           FROM opportunities o
           WHERE o.id = m.opportunity_id AND m.content_hash IS NULL"""
    )
    op.alter_column("match_evaluations", "content_hash", nullable=False)
    op.add_column("match_evaluations", sa.Column("hard_failure_code", sa.String(length=64), nullable=True))
    op.alter_column("match_evaluations", "dimension_scores_json", existing_type=sa.Text(), nullable=True)
    op.drop_constraint(
        "uq_match_evaluations_opportunity_truth_pack", "match_evaluations", type_="unique"
    )
    op.create_unique_constraint(
        "uq_match_evaluations_current_opportunity", "match_evaluations", ["opportunity_id"]
    )

    op.create_table(
        "opportunity_archive_orphans",
        sa.Column("object_key", sa.String(length=255), nullable=False),
        sa.Column("payload_sha256", sa.String(length=64), nullable=False),
        sa.Column("compressed_size_bytes", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("object_key"),
    )

    # The 0017 policy was created while table-level RLS remained disabled.
    # Enabling it makes that Founder-only read policy effective on clean DBs.
    op.execute("ALTER TABLE public.founder_activity_events ENABLE ROW LEVEL SECURITY")
    from storage.rls_policy import apply_postgres_deny_policy_for_table
    if op.get_bind().dialect.name == "postgresql":
        apply_postgres_deny_policy_for_table(op, "opportunity_archive_orphans")


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS opportunity_archive_orphans_browser_deny_anon ON opportunity_archive_orphans")
    op.execute("DROP POLICY IF EXISTS opportunity_archive_orphans_browser_deny_authenticated ON opportunity_archive_orphans")
    op.execute("ALTER TABLE opportunity_archive_orphans DISABLE ROW LEVEL SECURITY")
    op.drop_table("opportunity_archive_orphans")
    op.drop_constraint("uq_match_evaluations_current_opportunity", "match_evaluations", type_="unique")
    op.create_unique_constraint(
        "uq_match_evaluations_opportunity_truth_pack",
        "match_evaluations",
        ["opportunity_id", "truth_pack_hash"],
    )
    op.alter_column("match_evaluations", "dimension_scores_json", existing_type=sa.Text(), nullable=False)
    op.drop_column("match_evaluations", "hard_failure_code")
    op.drop_column("match_evaluations", "content_hash")
    op.drop_constraint("uq_feed_projection_current_opportunity", "feed_projection", type_="unique")
    op.add_column("feed_projection", sa.Column("search_tsv", postgresql.TSVECTOR(), nullable=True))
    op.add_column("feed_projection", sa.Column("search_text", sa.Text(), nullable=False, server_default=""))
    op.create_unique_constraint(
        "uq_feed_projection_opportunity_truth_pack",
        "feed_projection",
        ["opportunity_id", "truth_pack_hash"],
    )
    op.alter_column("opportunities", "description", existing_type=sa.Text(), nullable=False)
    op.drop_index("ix_opportunities_lifecycle_tier", table_name="opportunities")
    op.drop_constraint("ck_opportunities_lifecycle_tier", "opportunities", type_="check")
    op.drop_column("opportunities", "lifecycle_tier")
    # RLS intentionally remains enabled; disabling it would reinstate the
    # known table-level Founder activity exposure.
