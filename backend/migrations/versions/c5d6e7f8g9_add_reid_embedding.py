"""add reid_embedding column to faces

Phase 0 of the Re-Identification rollout. Adds a per-face body / clothing
embedding column populated by the indexer (via the reid-api sidecar) and
read by the scan endpoint's matching gate in a later phase.

The column is nullable so legacy rows remain valid; a background backfill
job (Phase 1) populates them. The scan endpoint will treat NULL as
"no Re-ID signal — fall back to face-only matching for this candidate".

Revision ID: c5d6e7f8g9
Revises: a4d5e6f7g8
Create Date: 2026-06-13 09:50:00.000000
"""
from alembic import op


revision = 'c5d6e7f8g9'
down_revision = 'a4d5e6f7g8'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Raw ALTER matches the pattern used by 001_initial_schema for the existing
    # faces.embedding column — keeps the migration self-contained without a
    # pgvector.sqlalchemy import at migration time.
    op.execute("ALTER TABLE faces ADD COLUMN reid_embedding vector(512)")
    # Cosine ivfflat index — same shape as the existing face `embedding`
    # index pattern. CONCURRENTLY isn't usable inside alembic's default
    # transaction; the table is small enough at deploy time that an
    # exclusive index build is acceptable. For very large tables in
    # future, switch to a manual `CREATE INDEX CONCURRENTLY` outside
    # alembic.
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_faces_reid_cosine "
        "ON faces USING ivfflat (reid_embedding vector_cosine_ops) "
        "WITH (lists = 100)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_faces_reid_cosine")
    op.execute("ALTER TABLE faces DROP COLUMN IF EXISTS reid_embedding")
