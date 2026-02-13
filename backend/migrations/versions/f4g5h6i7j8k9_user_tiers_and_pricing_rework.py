"""user_tiers_and_pricing_rework

Revision ID: f4g5h6i7j8k9
Revises: e3f4a5b6c7d8
Create Date: 2026-02-13 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


# revision identifiers, used by Alembic.
revision = 'f4g5h6i7j8k9'
down_revision = 'e3f4a5b6c7d8'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create user_tiers table
    op.create_table(
        'user_tiers',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('user_id', UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), unique=True, nullable=False),
        sa.Column('tier_name', sa.String(50), nullable=False, server_default='free'),
        sa.Column('max_events', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('max_photos_per_event', sa.Integer(), nullable=False, server_default='50'),
        sa.Column('price_cents', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('currency', sa.String(3), nullable=False, server_default='myr'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('activated_at', sa.TIMESTAMP(), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.TIMESTAMP(), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("tier_name IN ('free', 'premium', 'premium_plus', 'custom')", name='valid_user_tier_name'),
    )
    op.create_index('ix_user_tiers_user_id', 'user_tiers', ['user_id'], unique=True)

    # Add tier_name column to payments table
    op.add_column('payments', sa.Column('tier_name', sa.String(50), nullable=True))

    # Update event_tiers check constraint to include premium_plus
    op.drop_constraint('valid_tier_name', 'event_tiers', type_='check')
    op.create_check_constraint(
        'valid_tier_name', 'event_tiers',
        "tier_name IN ('free', 'standard', 'premium', 'premium_plus', 'custom')"
    )

    # Drop event_tier_id FK from payments (no longer needed)
    op.drop_constraint('payments_event_tier_id_fkey', 'payments', type_='foreignkey')
    op.drop_index('ix_payments_event_tier_id', table_name='payments')
    op.drop_column('payments', 'event_tier_id')

    # Backfill: create free tier for all existing users
    op.execute("""
        INSERT INTO user_tiers (id, user_id, tier_name, max_events, max_photos_per_event, price_cents, currency, is_active, activated_at, created_at, updated_at)
        SELECT gen_random_uuid(), id, 'free', 1, 50, 0, 'myr', true, now(), now(), now()
        FROM users
        WHERE id NOT IN (SELECT user_id FROM user_tiers)
    """)


def downgrade() -> None:
    # Add back event_tier_id to payments
    op.add_column('payments', sa.Column('event_tier_id', UUID(as_uuid=True), nullable=True))
    op.create_index('ix_payments_event_tier_id', 'payments', ['event_tier_id'])
    op.create_foreign_key('payments_event_tier_id_fkey', 'payments', 'event_tiers', ['event_tier_id'], ['id'], ondelete='CASCADE')

    # Remove tier_name from payments
    op.drop_column('payments', 'tier_name')

    # Revert event_tiers check constraint
    op.drop_constraint('valid_tier_name', 'event_tiers', type_='check')
    op.create_check_constraint(
        'valid_tier_name', 'event_tiers',
        "tier_name IN ('free', 'standard', 'premium', 'custom')"
    )

    # Drop user_tiers table
    op.drop_table('user_tiers')
