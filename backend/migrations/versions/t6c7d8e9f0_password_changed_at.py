"""add password_changed_at to users for token-replay invalidation

Revision ID: t6c7d8e9f0
Revises: s5b6c7d8e9
Create Date: 2026-05-07 12:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = 't6c7d8e9f0'
down_revision = 's5b6c7d8e9'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Nullable on existing rows: NULL means "no constraint, accept any
    # signed token". Once a user resets/changes their password, we set
    # this to NOW() and tokens issued before that point are rejected.
    op.add_column('users', sa.Column('password_changed_at', sa.TIMESTAMP(), nullable=True))


def downgrade() -> None:
    op.drop_column('users', 'password_changed_at')
