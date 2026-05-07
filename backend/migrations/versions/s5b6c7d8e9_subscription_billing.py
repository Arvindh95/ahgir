"""subscription_billing

Adds subscription columns to user_tiers, status enum to events,
and renames legacy premium/premium_plus tiers to starter/pro.

Revision ID: s5b6c7d8e9
Revises: f4g5h6i7j8k9
Create Date: 2026-05-07 12:30:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = 's5b6c7d8e9'
down_revision = 'f4g5h6i7j8k9'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # user_tiers: subscription columns
    op.add_column('user_tiers', sa.Column('stripe_customer_id', sa.String(length=255), nullable=True))
    op.add_column('user_tiers', sa.Column('stripe_subscription_id', sa.String(length=255), nullable=True))
    op.add_column('user_tiers', sa.Column('subscription_status', sa.String(length=30), nullable=True))
    op.add_column('user_tiers', sa.Column('billing_interval', sa.String(length=10), nullable=True))
    op.add_column('user_tiers', sa.Column('current_period_end', sa.TIMESTAMP(), nullable=True))
    op.add_column('user_tiers', sa.Column('cancel_at_period_end', sa.Boolean(), nullable=False, server_default=sa.text('false')))
    op.add_column('user_tiers', sa.Column('retention_days', sa.Integer(), nullable=True))
    op.create_index('ix_user_tiers_stripe_customer_id', 'user_tiers', ['stripe_customer_id'])
    op.create_index('ix_user_tiers_stripe_subscription_id', 'user_tiers', ['stripe_subscription_id'])

    # Migrate legacy tier names: premium -> starter, premium_plus -> pro
    # Drop old constraint, rename rows, add new constraint
    op.drop_constraint('valid_user_tier_name', 'user_tiers', type_='check')
    op.execute("UPDATE user_tiers SET tier_name = 'starter' WHERE tier_name = 'premium'")
    op.execute("UPDATE user_tiers SET tier_name = 'pro' WHERE tier_name = 'premium_plus'")
    op.create_check_constraint(
        'valid_user_tier_name',
        'user_tiers',
        "tier_name IN ('free', 'starter', 'pro', 'custom')",
    )

    # subscription_status check
    op.create_check_constraint(
        'valid_subscription_status',
        'user_tiers',
        "subscription_status IS NULL OR subscription_status IN "
        "('active', 'trialing', 'past_due', 'canceled', 'incomplete', 'incomplete_expired', 'unpaid', 'paused')",
    )

    # billing_interval check
    op.create_check_constraint(
        'valid_billing_interval',
        'user_tiers',
        "billing_interval IS NULL OR billing_interval IN ('month', 'year')",
    )

    # events: status column
    op.add_column('events', sa.Column('status', sa.String(length=20), nullable=False, server_default='active'))
    op.create_check_constraint(
        'valid_event_status',
        'events',
        "status IN ('active', 'frozen', 'expired')",
    )
    op.create_index('ix_events_status', 'events', ['status'])

    # payments: track subscription invoices alongside one-time
    op.add_column('payments', sa.Column('stripe_invoice_id', sa.String(length=255), nullable=True))
    op.add_column('payments', sa.Column('stripe_subscription_id', sa.String(length=255), nullable=True))
    op.add_column('payments', sa.Column('billing_interval', sa.String(length=10), nullable=True))
    op.create_index('ix_payments_stripe_invoice_id', 'payments', ['stripe_invoice_id'])
    op.create_index('ix_payments_stripe_subscription_id', 'payments', ['stripe_subscription_id'])

    # Allow checkout_session_id to be NULL (subscription invoices don't have one)
    op.alter_column('payments', 'stripe_checkout_session_id', nullable=True)


def downgrade() -> None:
    op.alter_column('payments', 'stripe_checkout_session_id', nullable=False)
    op.drop_index('ix_payments_stripe_subscription_id', table_name='payments')
    op.drop_index('ix_payments_stripe_invoice_id', table_name='payments')
    op.drop_column('payments', 'billing_interval')
    op.drop_column('payments', 'stripe_subscription_id')
    op.drop_column('payments', 'stripe_invoice_id')

    op.drop_index('ix_events_status', table_name='events')
    op.drop_constraint('valid_event_status', 'events', type_='check')
    op.drop_column('events', 'status')

    op.drop_constraint('valid_billing_interval', 'user_tiers', type_='check')
    op.drop_constraint('valid_subscription_status', 'user_tiers', type_='check')
    op.drop_constraint('valid_user_tier_name', 'user_tiers', type_='check')

    op.execute("UPDATE user_tiers SET tier_name = 'premium' WHERE tier_name = 'starter'")
    op.execute("UPDATE user_tiers SET tier_name = 'premium_plus' WHERE tier_name = 'pro'")

    op.create_check_constraint(
        'valid_user_tier_name',
        'user_tiers',
        "tier_name IN ('free', 'premium', 'premium_plus', 'custom')",
    )

    op.drop_index('ix_user_tiers_stripe_subscription_id', table_name='user_tiers')
    op.drop_index('ix_user_tiers_stripe_customer_id', table_name='user_tiers')
    op.drop_column('user_tiers', 'retention_days')
    op.drop_column('user_tiers', 'cancel_at_period_end')
    op.drop_column('user_tiers', 'current_period_end')
    op.drop_column('user_tiers', 'billing_interval')
    op.drop_column('user_tiers', 'subscription_status')
    op.drop_column('user_tiers', 'stripe_subscription_id')
    op.drop_column('user_tiers', 'stripe_customer_id')
