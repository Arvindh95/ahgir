"""wipe stored Image.exif_data values

The public security copy promises that EXIF metadata (GPS, camera
serial, capture timestamps) is forgotten before storage. The image
BYTES were already stripped by the upload helper, but the previous
code path also persisted everything except GPS into the
``Image.exif_data`` JSONB column — leaving camera make/model, serial,
lens info, and capture timestamps in the database. Nothing in the
codebase actually reads that column, and the upload helper now stops
writing it, so this migration NULLs every existing row to bring stored
data in line with the public promise.

Revision ID: e8g9h0i1j2
Revises: d7f8g9h0i1
Create Date: 2026-05-14 09:00:00.000000
"""
from alembic import op


revision = 'e8g9h0i1j2'
down_revision = 'd7f8g9h0i1'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("UPDATE images SET exif_data = NULL WHERE exif_data IS NOT NULL")


def downgrade() -> None:
    # No reverse — once wiped, the original tags are gone.
    pass
