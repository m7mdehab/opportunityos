"""0004_founder_control

Revision ID: 0004_founder_control
Revises: 0003_provenance_identity
Create Date: 2026-09-03 00:00:00.000000

A1M (BRIEF-FR-006 Track A schema half) -- founder-control columns on
``opportunities`` (work mode, location, remote scope, employment type,
seniority, compensation, title family/level, full-text search vector) plus
the supporting tables for opportunity families, founder facets, founder
saved views, and the artifact cache. Fully specified by
``reports/evidence/FR-006/orders/A1M-migration.md``; this revision does not
design anything beyond what that order enumerates.

**Deviation from the order, named here:** the order's "New tables" section
lists ``founder_opportunity_views`` (``opportunity_id`` PK, ``viewed_at``
DateTime not null). That table already exists -- it was created by
``0002_match_evaluations`` with a *different* shape (surrogate ``id`` PK,
``opportunity_id`` FK+index, ``viewed_at``+index) and already has a matching
ORM model (``storage/models.py::FounderOpportunityViewRecord``) and backup
registration (``scripts/backup_restore.py``). Creating it again here would
raise ``DuplicateTable``; redefining its primary key would be an unrelated,
undirected schema change outside this order's enumerated columns. This
revision therefore does **not** touch ``founder_opportunity_views`` at all --
treating the order's listing as already satisfied by ``0002``, analogous to
the ``founder_filter_settings`` amended-in-place hazard documented in
``0003_provenance_identity``.

Per the order, ``founder_filter_settings`` (D3, ``0003``) is untouched: two
tables coexist deliberately.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import TSVECTOR

revision: str = '0004_founder_control'
down_revision: Union[str, None] = '0003_provenance_identity'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- opportunities: founder-control columns -----------------------------
    op.add_column('opportunities', sa.Column('work_mode', sa.String(length=16), nullable=False, server_default='unspecified'))
    op.add_column('opportunities', sa.Column('work_mode_source', sa.String(length=16), nullable=True))
    op.add_column('opportunities', sa.Column('location_country', sa.String(length=2), nullable=True))
    op.add_column('opportunities', sa.Column('location_city', sa.String(length=128), nullable=True))
    op.add_column('opportunities', sa.Column('location_region', sa.String(length=64), nullable=True))
    op.add_column('opportunities', sa.Column('remote_scope', sa.String(length=24), nullable=False, server_default='unspecified'))
    op.add_column('opportunities', sa.Column('remote_scope_regions', sa.Text(), nullable=True))
    op.add_column('opportunities', sa.Column('employment_type', sa.String(length=24), nullable=False, server_default='unspecified'))
    op.add_column('opportunities', sa.Column('seniority_level', sa.String(length=24), nullable=False, server_default='unspecified'))
    op.add_column('opportunities', sa.Column('compensation_min', sa.Integer(), nullable=True))
    op.add_column('opportunities', sa.Column('compensation_max', sa.Integer(), nullable=True))
    op.add_column('opportunities', sa.Column('compensation_currency', sa.String(length=8), nullable=True))
    op.add_column('opportunities', sa.Column('compensation_period', sa.String(length=16), nullable=True))
    op.add_column('opportunities', sa.Column('title_family', sa.String(length=64), nullable=True))
    op.add_column('opportunities', sa.Column('title_level', sa.String(length=24), nullable=True))
    op.add_column('opportunities', sa.Column('family_key', sa.String(length=64), nullable=True))
    op.add_column('opportunities', sa.Column('search_tsv', TSVECTOR(), nullable=True))

    op.create_index('ix_opportunities_work_mode', 'opportunities', ['work_mode'], unique=False)
    op.create_index('ix_opportunities_location_country', 'opportunities', ['location_country'], unique=False)
    op.create_index('ix_opportunities_title_family', 'opportunities', ['title_family'], unique=False)
    op.create_index('ix_opportunities_family_key', 'opportunities', ['family_key'], unique=False)
    op.create_index(
        'ix_opportunities_search_tsv',
        'opportunities',
        ['search_tsv'],
        unique=False,
        postgresql_using='gin',
    )

    # --- opportunity_families -------------------------------------------------
    op.create_table(
        'opportunity_families',
        sa.Column('family_key', sa.String(length=64), nullable=False),
        sa.Column('employer', sa.String(length=256), nullable=True),
        sa.Column('normalized_title', sa.String(length=256), nullable=True),
        sa.Column('member_count', sa.Integer(), nullable=True),
        sa.Column('best_member_id', sa.String(length=64), nullable=True),
        sa.Column('split_out', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('family_key'),
    )

    # --- founder_facets ---------------------------------------------------------
    op.create_table(
        'founder_facets',
        sa.Column('facet_id', sa.String(length=64), nullable=False),
        sa.Column('mode', sa.String(length=16), nullable=False, server_default='off'),
        sa.Column('values_json', sa.Text(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('facet_id'),
    )

    # --- founder_saved_views -----------------------------------------------------
    op.create_table(
        'founder_saved_views',
        sa.Column('id', sa.String(length=64), nullable=False),
        sa.Column('name', sa.String(length=128), nullable=False),
        sa.Column('facets_json', sa.Text(), nullable=True),
        sa.Column('search_query', sa.Text(), nullable=True),
        sa.Column('is_default', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name', name='uq_founder_saved_views_name'),
    )

    # --- artifact_cache -----------------------------------------------------------
    op.create_table(
        'artifact_cache',
        sa.Column('cache_key', sa.String(length=128), nullable=False),
        sa.Column('opportunity_id', sa.String(length=64), nullable=True),
        sa.Column('truth_pack_hash', sa.String(length=64), nullable=True),
        sa.Column('template_id', sa.String(length=32), nullable=True),
        sa.Column('artifact_kind', sa.String(length=32), nullable=True),
        sa.Column('content_type', sa.String(length=128), nullable=True),
        sa.Column('payload', sa.LargeBinary(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('cache_key'),
    )

    # founder_opportunity_views: already exists (0002_match_evaluations) --
    # intentionally not touched here; see module docstring.


def downgrade() -> None:
    op.drop_table('artifact_cache')
    op.drop_table('founder_saved_views')
    op.drop_table('founder_facets')
    op.drop_table('opportunity_families')

    op.drop_index('ix_opportunities_search_tsv', table_name='opportunities')
    op.drop_index('ix_opportunities_family_key', table_name='opportunities')
    op.drop_index('ix_opportunities_title_family', table_name='opportunities')
    op.drop_index('ix_opportunities_location_country', table_name='opportunities')
    op.drop_index('ix_opportunities_work_mode', table_name='opportunities')

    op.drop_column('opportunities', 'search_tsv')
    op.drop_column('opportunities', 'family_key')
    op.drop_column('opportunities', 'title_level')
    op.drop_column('opportunities', 'title_family')
    op.drop_column('opportunities', 'compensation_period')
    op.drop_column('opportunities', 'compensation_currency')
    op.drop_column('opportunities', 'compensation_max')
    op.drop_column('opportunities', 'compensation_min')
    op.drop_column('opportunities', 'seniority_level')
    op.drop_column('opportunities', 'employment_type')
    op.drop_column('opportunities', 'remote_scope_regions')
    op.drop_column('opportunities', 'remote_scope')
    op.drop_column('opportunities', 'location_region')
    op.drop_column('opportunities', 'location_city')
    op.drop_column('opportunities', 'location_country')
    op.drop_column('opportunities', 'work_mode_source')
    op.drop_column('opportunities', 'work_mode')
