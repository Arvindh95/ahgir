"""switch_dedup_to_filename

Revision ID: a1b2c3d4e5f6
Revises: b4244148af48
Create Date: 2026-02-05 10:00:00.000000

"""
from alembic import op


# revision identifiers, used by Alembic.
revision = 'a1b2c3d4e5f6'
down_revision = 'b4244148af48'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Drop old hash-based indexes
    op.drop_index('unique_hash_per_event', table_name='images')
    op.drop_index('idx_event_hash', table_name='images')

    # Create filename-based unique index
    op.create_index('unique_filename_per_event', 'images', ['event_id', 'filename'], unique=True)


def downgrade() -> None:
    op.drop_index('unique_filename_per_event', table_name='images')
    op.create_index('idx_event_hash', 'images', ['event_id', 'file_hash'])
    op.create_index('unique_hash_per_event', 'images', ['event_id', 'file_hash'], unique=True)
