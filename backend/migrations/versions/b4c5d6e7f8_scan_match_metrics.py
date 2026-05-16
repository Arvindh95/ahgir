"""add scan_match_metrics table for tuning telemetry

Each /scan request logs one row per candidate photo (matched and
filtered both), so the team can answer questions like:
- Is the current threshold cutting the right line?
- Is multi-frame bonus pulling its weight?
- Are quality penalties correctly hitting blurry indexed faces?
- Where do guests' real similarity scores cluster on the curve?

Tuning has been done blind so far. This table backs a future SQL
view / admin dashboard that turns "vibes" into data.

Revision ID: b4c5d6e7f8
Revises: a3b4c5d6e7
Create Date: 2026-05-16 23:30:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


revision = 'b4c5d6e7f8'
down_revision = 'a3b4c5d6e7'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'scan_match_metrics',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('scan_id', UUID(as_uuid=True), nullable=False),
        sa.Column('session_id', UUID(as_uuid=True), nullable=False),
        sa.Column('event_id', UUID(as_uuid=True), nullable=False),
        sa.Column('image_id', UUID(as_uuid=True), nullable=False),
        sa.Column('raw_similarity', sa.Float(), nullable=False),
        sa.Column('scored_similarity', sa.Float(), nullable=False),
        sa.Column('score_gap', sa.Float(), nullable=True),
        sa.Column('frame_count', sa.Integer(), nullable=False),
        sa.Column('threshold_used', sa.Float(), nullable=False),
        sa.Column('passed', sa.Boolean(), nullable=False),
        sa.Column('blur_score', sa.Float(), nullable=True),
        sa.Column('brightness_score', sa.Float(), nullable=True),
        sa.Column('face_min_side_px', sa.Float(), nullable=True),
        sa.Column('quality_score', sa.Float(), nullable=True),
        sa.Column('cluster_id', UUID(as_uuid=True), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['event_id'], ['events.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['image_id'], ['images.id'], ondelete='CASCADE'),
    )

    # Per-event analytics — the rollup view groups by event_id and slices
    # on a recent time window.
    op.create_index(
        'idx_scan_match_metrics_event_created',
        'scan_match_metrics',
        ['event_id', 'created_at'],
    )

    # Per-scan grouping — useful when correlating a guest's whole scan
    # session against the matches that came back.
    op.create_index(
        'idx_scan_match_metrics_scan',
        'scan_match_metrics',
        ['scan_id'],
    )


def downgrade() -> None:
    op.drop_index('idx_scan_match_metrics_scan', table_name='scan_match_metrics')
    op.drop_index('idx_scan_match_metrics_event_created', table_name='scan_match_metrics')
    op.drop_table('scan_match_metrics')
