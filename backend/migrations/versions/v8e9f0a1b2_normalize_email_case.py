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
    # Normalize existing rows. If two users registered as User@x.com and
    # user@x.com, this UPDATE will fail on the existing UNIQUE(email)
    # constraint — that's intentional. Resolve the duplicate manually
    # before re-running the migration.
    op.execute("UPDATE users SET email = lower(email) WHERE email <> lower(email)")

    # Defense-in-depth: enforce case-insensitive uniqueness at the DB even
    # if a future code path bypasses the Pydantic boundary.
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS ix_users_email_lower ON users (lower(email))")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_users_email_lower")
    # No data downgrade — lowercased emails stay lowercased.
