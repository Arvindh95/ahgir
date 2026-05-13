"""update event_tiers.tier_name check constraint to allow starter / pro

The pricing rework renamed paid tiers `premium` / `premium_plus` to
`starter` / `pro`, but the original CheckConstraint on event_tiers still
listed the old names. Any insert with the new names errors out at the DB.

This migration drops the old constraint, normalizes any stragglers, and
recreates the constraint with the current canonical names.

Revision ID: z2c3d4e5f6
Revises: y1b2c3d4e5
Create Date: 2026-05-13 09:30:00.000000
"""
from alembic import op


revision = 'z2c3d4e5f6'
down_revision = 'y1b2c3d4e5'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint('valid_tier_name', 'event_tiers', type_='check')

    op.execute("UPDATE event_tiers SET tier_name = 'starter' WHERE tier_name = 'premium'")
    op.execute("UPDATE event_tiers SET tier_name = 'pro' WHERE tier_name = 'premium_plus'")
    op.execute("UPDATE event_tiers SET tier_name = 'free' WHERE tier_name = 'standard'")

    op.create_check_constraint(
        'valid_tier_name',
        'event_tiers',
        "tier_name IN ('free', 'starter', 'pro', 'custom')",
    )

    # user_tiers table uses the same naming and was created without an explicit
    # check constraint, but in case any stragglers exist normalise them too.
    op.execute("UPDATE user_tiers SET tier_name = 'starter' WHERE tier_name = 'premium'")
    op.execute("UPDATE user_tiers SET tier_name = 'pro' WHERE tier_name = 'premium_plus'")
    op.execute("UPDATE user_tiers SET tier_name = 'free' WHERE tier_name = 'standard'")

    # Same for payments.tier_name (history rows; safe to rewrite for consistency).
    op.execute("UPDATE payments SET tier_name = 'starter' WHERE tier_name = 'premium'")
    op.execute("UPDATE payments SET tier_name = 'pro' WHERE tier_name = 'premium_plus'")
    op.execute("UPDATE payments SET tier_name = 'free' WHERE tier_name = 'standard'")


def downgrade() -> None:
    op.drop_constraint('valid_tier_name', 'event_tiers', type_='check')
    op.create_check_constraint(
        'valid_tier_name',
        'event_tiers',
        "tier_name IN ('free', 'standard', 'premium', 'premium_plus', 'custom')",
    )
