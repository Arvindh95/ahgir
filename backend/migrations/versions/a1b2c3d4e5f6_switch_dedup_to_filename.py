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

    # Pre-flight: the original schema allowed (event_id, filename)
    # duplicates as long as the SHA-256 hashes differed. Two distinct
    # photos named IMG_0001.jpg in the same event was therefore valid.
    # Without this cleanup the unique index below blocks alembic
    # upgrade on any DB with such pairs. We keep the oldest row (by id)
    # in each group untouched and rename the rest by appending
    # `.dup.<id_prefix>` so they remain unique without losing the
    # underlying file reference. The renamed images stay viewable;
    # admins can rename / delete them via the regular UI afterwards.
    op.execute("""
        UPDATE images
        SET filename = filename || '.dup.' || substring(id::text FROM 1 FOR 8)
        WHERE id IN (
            SELECT id FROM (
                SELECT id, row_number() OVER (
                    PARTITION BY event_id, filename
                    ORDER BY uploaded_at, id
                ) AS rn
                FROM images
            ) t
            WHERE rn > 1
        );
    """)

    # Create filename-based unique index
    op.create_index('unique_filename_per_event', 'images', ['event_id', 'filename'], unique=True)


def downgrade() -> None:
    op.drop_index('unique_filename_per_event', table_name='images')
    op.create_index('idx_event_hash', 'images', ['event_id', 'file_hash'])
    op.create_index('unique_hash_per_event', 'images', ['event_id', 'file_hash'], unique=True)
