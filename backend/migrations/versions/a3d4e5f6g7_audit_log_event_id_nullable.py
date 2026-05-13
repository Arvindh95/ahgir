"""make audit_logs.event_id nullable + change FK to SET NULL

Superadmin actions like user-tier updates aren't tied to a specific event,
so the existing NOT NULL prevents auditing them. Also, the original ON
DELETE CASCADE means deleting an event wipes its audit trail — which is
the opposite of what an audit log is for. Switch to ON DELETE SET NULL so
admin/guest actions remain auditable even after the event is gone.

Revision ID: a3d4e5f6g7
Revises: z2c3d4e5f6
Create Date: 2026-05-13 09:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = 'a3d4e5f6g7'
down_revision = 'z2c3d4e5f6'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Drop the cascade FK and replace with a SET NULL FK.
    op.drop_constraint('audit_logs_event_id_fkey', 'audit_logs', type_='foreignkey')
    op.alter_column('audit_logs', 'event_id', nullable=True)
    op.create_foreign_key(
        'audit_logs_event_id_fkey',
        'audit_logs',
        'events',
        ['event_id'],
        ['id'],
        ondelete='SET NULL',
    )


def downgrade() -> None:
    op.drop_constraint('audit_logs_event_id_fkey', 'audit_logs', type_='foreignkey')
    # Cannot safely set event_id back to NOT NULL if any rows have NULL.
    # Refuse to migrate if there are NULLs so we don't lose data.
    op.execute(
        "DO $$ BEGIN IF EXISTS (SELECT 1 FROM audit_logs WHERE event_id IS NULL) THEN "
        "RAISE EXCEPTION 'audit_logs has rows with event_id IS NULL — cannot downgrade'; "
        "END IF; END $$;"
    )
    op.alter_column('audit_logs', 'event_id', nullable=False)
    op.create_foreign_key(
        'audit_logs_event_id_fkey',
        'audit_logs',
        'events',
        ['event_id'],
        ['id'],
        ondelete='CASCADE',
    )
