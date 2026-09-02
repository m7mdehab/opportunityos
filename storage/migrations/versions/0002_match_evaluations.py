"""0002_match_evaluations

Revision ID: 0002_match_evaluations
Revises: 0001_baseline_schema
Create Date: 2026-09-02 00:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = '0002_match_evaluations'
down_revision: Union[str, None] = '0001_baseline_schema'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'match_evaluations',
        sa.Column('id', sa.String(length=64), nullable=False),
        sa.Column('opportunity_id', sa.String(length=64), nullable=False),
        sa.Column('truth_pack_hash', sa.String(length=64), nullable=False),
        sa.Column('qualification_decision', sa.String(length=32), nullable=False),
        sa.Column('fit_score', sa.Float(), nullable=False),
        sa.Column('dimension_scores_json', sa.Text(), nullable=False),
        sa.Column('reasons_json', sa.Text(), nullable=False),
        sa.Column('policy_version', sa.String(length=32), nullable=False),
        sa.Column('evaluated_at', sa.DateTime(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['opportunity_id'], ['opportunities.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('opportunity_id', 'truth_pack_hash', name='uq_match_evaluations_opportunity_truth_pack')
    )
    op.create_index(op.f('ix_match_evaluations_opportunity_id'), 'match_evaluations', ['opportunity_id'], unique=False)
    op.create_index(op.f('ix_match_evaluations_truth_pack_hash'), 'match_evaluations', ['truth_pack_hash'], unique=False)
    op.create_index(op.f('ix_match_evaluations_evaluated_at'), 'match_evaluations', ['evaluated_at'], unique=False)

    op.create_table(
        'source_poll_runs',
        sa.Column('id', sa.String(length=64), nullable=False),
        sa.Column('source_id', sa.String(length=128), nullable=False),
        sa.Column('job_id', sa.String(length=64), nullable=True),
        sa.Column('started_at', sa.DateTime(), nullable=False),
        sa.Column('finished_at', sa.DateTime(), nullable=True),
        sa.Column('status', sa.String(length=32), nullable=False),
        sa.Column('refusal_reason', sa.String(length=128), nullable=True),
        sa.Column('raw_ingested', sa.Integer(), nullable=False),
        sa.Column('unique_opportunities', sa.Integer(), nullable=False),
        sa.Column('inserted', sa.Integer(), nullable=False),
        sa.Column('unchanged', sa.Integer(), nullable=False),
        sa.Column('updated', sa.Integer(), nullable=False),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_source_poll_runs_source_id'), 'source_poll_runs', ['source_id'], unique=False)
    op.create_index(op.f('ix_source_poll_runs_started_at'), 'source_poll_runs', ['started_at'], unique=False)
    op.create_index(op.f('ix_source_poll_runs_status'), 'source_poll_runs', ['status'], unique=False)

    op.create_table(
        'founder_opportunity_views',
        sa.Column('id', sa.String(length=64), nullable=False),
        sa.Column('opportunity_id', sa.String(length=64), nullable=False),
        sa.Column('viewed_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['opportunity_id'], ['opportunities.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_founder_opportunity_views_opportunity_id'), 'founder_opportunity_views', ['opportunity_id'], unique=False)
    op.create_index(op.f('ix_founder_opportunity_views_viewed_at'), 'founder_opportunity_views', ['viewed_at'], unique=False)

    op.create_table(
        'founder_triage_states',
        sa.Column('opportunity_id', sa.String(length=64), nullable=False),
        sa.Column('state', sa.String(length=32), nullable=False),
        sa.Column('snoozed_until', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['opportunity_id'], ['opportunities.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('opportunity_id')
    )
    op.create_index(op.f('ix_founder_triage_states_state'), 'founder_triage_states', ['state'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_founder_triage_states_state'), table_name='founder_triage_states')
    op.drop_table('founder_triage_states')

    op.drop_index(op.f('ix_founder_opportunity_views_viewed_at'), table_name='founder_opportunity_views')
    op.drop_index(op.f('ix_founder_opportunity_views_opportunity_id'), table_name='founder_opportunity_views')
    op.drop_table('founder_opportunity_views')

    op.drop_index(op.f('ix_source_poll_runs_status'), table_name='source_poll_runs')
    op.drop_index(op.f('ix_source_poll_runs_started_at'), table_name='source_poll_runs')
    op.drop_index(op.f('ix_source_poll_runs_source_id'), table_name='source_poll_runs')
    op.drop_table('source_poll_runs')

    op.drop_index(op.f('ix_match_evaluations_evaluated_at'), table_name='match_evaluations')
    op.drop_index(op.f('ix_match_evaluations_truth_pack_hash'), table_name='match_evaluations')
    op.drop_index(op.f('ix_match_evaluations_opportunity_id'), table_name='match_evaluations')
    op.drop_table('match_evaluations')
