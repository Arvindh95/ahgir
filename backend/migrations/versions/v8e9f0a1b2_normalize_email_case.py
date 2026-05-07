"""normalize user.email casing and enforce case-insensitive uniqueness

Revision ID: v8e9f0a1b2
Revises: u7d8e9f0a1
Create Date: 2026-05-07 14:30:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = 'v8e9f0a1b2'
down_revision = 'u7d8e9f0a1'
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    duplicates = bind.execute(sa.text("""
        SELECT lower(email) AS normalized_email, count(*) AS row_count,
               array_agg(email ORDER BY email) AS emails
        FROM users
        GROUP BY lower(email)
        HAVING count(*) > 1
        ORDER BY lower(email)
        LIMIT 10
    """)).mappings().all()
    if duplicates:
        examples = "; ".join(
            f"{row['normalized_email']} ({row['row_count']} rows: {', '.join(row['emails'])})"
            for row in duplicates
        )
        raise RuntimeError(
            "Cannot normalize users.email because case-insensitive duplicates exist. "
            "Merge or delete the duplicate accounts first, then rerun the migration. "
            f"Examples: {examples}"
        )

    # Safe after the duplicate preflight: no existing row will collide with
    # another row once lowercased.
    op.execute("UPDATE users SET email = lower(email) WHERE email <> lower(email)")

    # Defense-in-depth: enforce case-insensitive uniqueness at the DB even
    # if a future code path bypasses the Pydantic boundary.
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS ix_users_email_lower ON users (lower(email))")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_users_email_lower")
    # No data downgrade — lowercased emails stay lowercased.
