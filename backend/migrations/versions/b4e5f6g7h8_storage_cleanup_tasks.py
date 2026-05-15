"""add storage_cleanup_tasks tombstone table

Storage and CompreFace cleanup happen on a best-effort basis from several
call sites (superadmin user delete, superadmin event delete, owner event
delete, retention worker). Pre-migration, every one of those sites caught
the exception and continued — the DB row went away, but original photo
bytes could remain in MinIO and face embeddings in CompreFace, with no
record that anything had failed.

This table is a durable tombstone: when an in-line cleanup attempt fails
we write a row here and retry asynchronously in the retention drainer.
Each row tracks how many attempts have been made, the last error
message, and a `next_attempt_at` we back-off exponentially.

Revision ID: b4e5f6g7h8
Revises: f9j2k3l4m5
Create Date: 2026-05-15 04:00:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = 'b4e5f6g7h8'
down_revision = 'f9j2k3l4m5'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'storage_cleanup_tasks',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text('gen_random_uuid()')),
        sa.Column('kind', sa.String(length=32), nullable=False),
        sa.Column('payload', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('status', sa.String(length=16), nullable=False,
                  server_default=sa.text("'pending'")),
        sa.Column('attempts', sa.Integer(), nullable=False, server_default=sa.text('0')),
        sa.Column('max_attempts', sa.Integer(), nullable=False, server_default=sa.text('10')),
        sa.Column('last_error', sa.Text(), nullable=True),
        sa.Column('last_attempt_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('next_attempt_at', sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text('now()')),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text('now()')),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "kind IN ('event_photos', 'compreface_event', 'image_photo', 'compreface_subject')",
            name='valid_cleanup_kind',
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'running', 'failed', 'done')",
            name='valid_cleanup_status',
        ),
    )
    # Drainer query: pending/failed rows ordered by next_attempt_at.
    op.create_index(
        'ix_cleanup_due',
        'storage_cleanup_tasks',
        ['status', 'next_attempt_at'],
        postgresql_where=sa.text("status IN ('pending', 'failed')"),
    )
    # Operator dashboard: list rows that have exhausted their retries.
    op.create_index(
        'ix_cleanup_failed',
        'storage_cleanup_tasks',
        ['attempts', 'status'],
        postgresql_where=sa.text("status = 'failed' AND attempts >= max_attempts"),
    )


def downgrade() -> None:
    op.drop_index('ix_cleanup_failed', table_name='storage_cleanup_tasks')
    op.drop_index('ix_cleanup_due', table_name='storage_cleanup_tasks')
    op.drop_table('storage_cleanup_tasks')
