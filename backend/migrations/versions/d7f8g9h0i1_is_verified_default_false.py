"""flip users.is_verified default from true to false

c7d8e9f0a1b2 originally set server_default=true so existing rows
backfilled as verified — that was the right call for the one-shot
migration. But the default stuck around as the column default, so any
raw INSERT (a backfill script, a manual psql session, a future import
path) that omits is_verified silently creates a verified account. The
ORM model declares default=False to match application intent.

This migration aligns the DB default with the model: unspecified
inserts become unverified, and the registration handler keeps its
explicit `is_verified=False` (now redundant but harmless).

Revision ID: d7f8g9h0i1
Revises: c6e7f8g9h0
Create Date: 2026-05-14 08:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = 'd7f8g9h0i1'
down_revision = 'c6e7f8g9h0'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        'users',
        'is_verified',
        server_default=sa.text('false'),
        existing_type=sa.Boolean(),
        existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        'users',
        'is_verified',
        server_default=sa.text('true'),
        existing_type=sa.Boolean(),
        existing_nullable=False,
    )
