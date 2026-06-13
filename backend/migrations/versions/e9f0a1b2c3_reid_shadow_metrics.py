"""add Re-ID shadow columns to scan_match_metrics

Phase 2 of the Re-Identification rollout. The scan endpoint computes the
guest probe's body embedding from the full video frame, cosine-compares it
against each candidate's faces.reid_embedding, and logs the result here
WITHOUT enforcing it (the gate stays off until Phase 3 flips
reid_enabled_scan). These two columns are the shadow-mode sink:

    SELECT image_id, scored_similarity AS face_sim, reid_similarity,
           reid_would_pass
    FROM   scan_match_metrics
    WHERE  reid_similarity IS NOT NULL;

so the team can confirm Re-ID separates a known sibling pair (sister
reid_similarity < ~0.40, self > ~0.65) before trusting the gate live.

Both columns are nullable: legacy rows, scans without a usable full frame,
sidecar-down scans, and candidates still mid-backfill all leave them NULL.

Revision ID: e9f0a1b2c3
Revises: c5d6e7f8g9
Create Date: 2026-06-13 12:05:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = 'e9f0a1b2c3'
down_revision = 'c5d6e7f8g9'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'scan_match_metrics',
        sa.Column('reid_similarity', sa.Float(), nullable=True),
    )
    op.add_column(
        'scan_match_metrics',
        sa.Column('reid_would_pass', sa.Boolean(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('scan_match_metrics', 'reid_would_pass')
    op.drop_column('scan_match_metrics', 'reid_similarity')
