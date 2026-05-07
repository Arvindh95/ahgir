"""add unique Stripe invoice id index

Revision ID: x0a1b2c3d4
Revises: w9f0a1b2c3
Create Date: 2026-05-07 16:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = 'x0a1b2c3d4'
down_revision = 'w9f0a1b2c3'
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    duplicates = bind.execute(sa.text("""
        SELECT stripe_invoice_id, COUNT(*) AS count
        FROM payments
        WHERE stripe_invoice_id IS NOT NULL
        GROUP BY stripe_invoice_id
        HAVING COUNT(*) > 1
        LIMIT 10
    """)).fetchall()
    if duplicates:
        examples = ", ".join(f"{row.stripe_invoice_id} ({row.count})" for row in duplicates)
        raise RuntimeError(
            "Cannot create unique Stripe invoice index; duplicate stripe_invoice_id values exist: "
            f"{examples}. Resolve or merge duplicate payment rows before rerunning this migration."
        )

    op.create_index(
        'uq_payments_stripe_invoice_id_not_null',
        'payments',
        ['stripe_invoice_id'],
        unique=True,
        postgresql_where=sa.text('stripe_invoice_id IS NOT NULL'),
    )


def downgrade() -> None:
    op.drop_index('uq_payments_stripe_invoice_id_not_null', table_name='payments')
