"""add last_subscription_event_at to user_tiers for webhook ordering

Revision ID: u7d8e9f0a1
Revises: t6c7d8e9f0
Create Date: 2026-05-07 14:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = 'u7d8e9f0a1'
down_revision = 't6c7d8e9f0'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Stripe webhook delivery is not ordered. After a customer.subscription.deleted
    # downgrades the user, a delayed customer.subscription.updated with active
    # status can arrive and re-grant the paid tier. Track the timestamp of the
    # last event we processed and reject older ones.
    op.add_column(
        'user_tiers',
        sa.Column('last_subscription_event_at', sa.TIMESTAMP(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('user_tiers', 'last_subscription_event_at')
