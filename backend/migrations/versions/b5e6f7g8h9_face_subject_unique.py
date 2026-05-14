"""partial unique index on faces.compreface_subject_id (race backstop)

Two concurrent face-indexing jobs for the same image_id can race through
the worker's "clear then re-insert" flow and produce duplicate
compreface_subject_id values (and duplicate Face rows). The worker now
takes a row lock on the Image and bails idempotently on a duplicate run,
but we add a DB-level partial unique index as belt-and-suspenders so any
future regression in the worker can't silently corrupt the index.

The index is partial (excludes NULLs) because old Face rows from before
CompreFace integration legitimately have NULL compreface_subject_id.

The pre-flight cleanup keeps the oldest row per duplicate subject ID,
deleting the rest. Any straggler duplicates from before the worker fix
get dropped here so the unique index can be created.

Revision ID: b5e6f7g8h9
Revises: a3d4e5f6g7
Create Date: 2026-05-14 06:00:00.000000
"""
from alembic import op


revision = 'b5e6f7g8h9'
down_revision = 'a3d4e5f6g7'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Drop any straggler duplicates first. Keep the oldest row per
    # subject_id (lowest created_at) — that's the one most likely to be
    # the row CompreFace's recognizer associates with the embedding.
    op.execute("""
        DELETE FROM faces a
        USING faces b
        WHERE a.compreface_subject_id IS NOT NULL
          AND a.compreface_subject_id = b.compreface_subject_id
          AND a.created_at > b.created_at;
    """)

    op.create_index(
        "uq_faces_compreface_subject_id_not_null",
        "faces",
        ["compreface_subject_id"],
        unique=True,
        postgresql_where="compreface_subject_id IS NOT NULL",
    )


def downgrade() -> None:
    op.drop_index(
        "uq_faces_compreface_subject_id_not_null",
        table_name="faces",
    )
