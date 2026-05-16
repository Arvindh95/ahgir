"""add face accuracy metadata columns

Adds technical image-quality and same-person clustering columns to the
faces table. Populated by the indexer (quality fields) and a separate
background job (face_cluster_id). All columns are nullable / safely
defaulted so existing rows remain valid without backfill.

Revision ID: a3b4c5d6e7
Revises: e7h8i9j0k1
Create Date: 2026-05-16 12:30:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


revision = 'a3b4c5d6e7'
down_revision = 'e7h8i9j0k1'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('faces', sa.Column('face_min_side_px', sa.Float(), nullable=True))
    op.add_column('faces', sa.Column('blur_score', sa.Float(), nullable=True))
    op.add_column('faces', sa.Column('brightness_score', sa.Float(), nullable=True))
    op.add_column(
        'faces',
        sa.Column('crop_clipped', sa.Boolean(), nullable=False, server_default=sa.text('false')),
    )
    op.add_column('faces', sa.Column('face_cluster_id', UUID(as_uuid=True), nullable=True))

    # Partial index — only event-scoped cluster lookups, never the bulk of NULLs.
    op.create_index(
        'idx_faces_event_cluster',
        'faces',
        ['event_id', 'face_cluster_id'],
        postgresql_where=sa.text('face_cluster_id IS NOT NULL'),
    )
    # Composite index for the per-event quality bucket query used by the scoring
    # path when grouping candidates by indexed face size.
    op.create_index(
        'idx_faces_quality_cluster',
        'faces',
        ['event_id', 'quality_score', 'face_min_side_px'],
    )


def downgrade() -> None:
    op.drop_index('idx_faces_quality_cluster', table_name='faces')
    op.drop_index('idx_faces_event_cluster', table_name='faces')
    op.drop_column('faces', 'face_cluster_id')
    op.drop_column('faces', 'crop_clipped')
    op.drop_column('faces', 'brightness_score')
    op.drop_column('faces', 'blur_score')
    op.drop_column('faces', 'face_min_side_px')
