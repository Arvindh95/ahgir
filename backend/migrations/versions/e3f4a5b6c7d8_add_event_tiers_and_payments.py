"""add_event_tiers_and_payments

Revision ID: e3f4a5b6c7d8
Revises: d1e2f3a4b5c6
Create Date: 2026-02-10 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB


# revision identifiers, used by Alembic.
revision = 'e3f4a5b6c7d8'
down_revision = 'd1e2f3a4b5c6'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create event_tiers table
    op.create_table(
        'event_tiers',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('event_id', UUID(as_uuid=True), sa.ForeignKey('events.id', ondelete='CASCADE'), unique=True, nullable=False),
        sa.Column('tier_name', sa.String(50), nullable=False, server_default='free'),
        sa.Column('photo_limit', sa.Integer(), nullable=False, server_default='25'),
        sa.Column('price_cents', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('currency', sa.String(3), nullable=False, server_default='myr'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('activated_at', sa.TIMESTAMP(), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.TIMESTAMP(), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("tier_name IN ('free', 'standard', 'premium', 'custom')", name='valid_tier_name'),
    )
    op.create_index('ix_event_tiers_event_id', 'event_tiers', ['event_id'], unique=True)

    # Create payments table
    op.create_table(
        'payments',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('event_tier_id', UUID(as_uuid=True), sa.ForeignKey('event_tiers.id', ondelete='CASCADE'), nullable=True),
        sa.Column('user_id', UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('stripe_checkout_session_id', sa.String(255), unique=True, nullable=False),
        sa.Column('stripe_payment_intent_id', sa.String(255), unique=True, nullable=True),
        sa.Column('amount_cents', sa.Integer(), nullable=False),
        sa.Column('currency', sa.String(3), nullable=False, server_default='myr'),
        sa.Column('status', sa.String(30), nullable=False, server_default='pending'),
        sa.Column('metadata', JSONB, nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.TIMESTAMP(), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("status IN ('pending', 'completed', 'failed', 'refunded')", name='valid_payment_status'),
    )
    op.create_index('ix_payments_event_tier_id', 'payments', ['event_tier_id'])
    op.create_index('ix_payments_user_id', 'payments', ['user_id'])
    op.create_index('ix_payments_stripe_checkout_session_id', 'payments', ['stripe_checkout_session_id'], unique=True)

    # Backfill: create a free tier for every existing event
    op.execute("""
        INSERT INTO event_tiers (id, event_id, tier_name, photo_limit, price_cents, currency, is_active, activated_at, created_at, updated_at)
        SELECT gen_random_uuid(), id, 'free', 25, 0, 'myr', true, now(), now(), now()
        FROM events
        WHERE id NOT IN (SELECT event_id FROM event_tiers)
    """)


def downgrade() -> None:
    op.drop_table('payments')
    op.drop_table('event_tiers')
