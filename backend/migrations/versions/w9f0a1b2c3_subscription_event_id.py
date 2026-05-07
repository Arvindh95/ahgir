"""add last Stripe subscription event markers

Revision ID: w9f0a1b2c3
Revises: v8e9f0a1b2
Create Date: 2026-05-07 15:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = 'w9f0a1b2c3'
down_revision = 'v8e9f0a1b2'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'user_tiers',
        sa.Column('last_subscription_event_id', sa.String(length=255), nullable=True),
    )
    op.add_column(
        'user_tiers',
        sa.Column('last_subscription_event_type', sa.String(length=80), nullable=True),
    )
    op.add_column(
        'user_tiers',
        sa.Column('last_subscription_event_subscription_id', sa.String(length=255), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('user_tiers', 'last_subscription_event_subscription_id')
    op.drop_column('user_tiers', 'last_subscription_event_type')
    op.drop_column('user_tiers', 'last_subscription_event_id')
