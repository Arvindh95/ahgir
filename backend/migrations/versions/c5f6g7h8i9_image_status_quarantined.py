"""add 'quarantined' to images.status CHECK

First half of the abuse-reporting wiring (ABUSE_REPORTING_PLAN.md).
Quarantined images keep their MinIO bytes + DB row, but no guest-facing
endpoint serves them. Operators reviewing an abuse report can still
fetch them via the 'abuse_review' signed photo_type.

Revision ID: c5f6g7h8i9
Revises: b4e5f6g7h8
Create Date: 2026-05-15 06:30:00.000000
"""
from alembic import op


revision = 'c5f6g7h8i9'
down_revision = 'b4e5f6g7h8'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint('valid_status', 'images', type_='check')
    op.create_check_constraint(
        'valid_status',
        'images',
        "status IN ('pending', 'indexed', 'no_faces', 'failed', 'quarantined')",
    )


def downgrade() -> None:
    # Refuse to downgrade if any images are currently quarantined — dropping
    # the value back to the old whitelist would silently break the rows.
    op.execute(
        "UPDATE images SET status = 'failed' WHERE status = 'quarantined'"
    )
    op.drop_constraint('valid_status', 'images', type_='check')
    op.create_check_constraint(
        'valid_status',
        'images',
        "status IN ('pending', 'indexed', 'no_faces', 'failed')",
    )
