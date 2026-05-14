"""extend audit_logs.actor_type CHECK to include 'system'

Automated jobs (daily retention sweep, scheduled downgrades) used to log
themselves as actor_type='admin' with the event owner as actor_id, which
made system cleanup look like a human admin action in the audit viewer.
The retention path now logs actor_type='system' with actor_id=NULL;
update the DB CHECK constraint so those inserts don't violate it.

Revision ID: c6e7f8g9h0
Revises: b5e6f7g8h9
Create Date: 2026-05-14 07:00:00.000000
"""
from alembic import op


revision = 'c6e7f8g9h0'
down_revision = 'b5e6f7g8h9'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint('valid_actor_type', 'audit_logs', type_='check')
    op.create_check_constraint(
        'valid_actor_type',
        'audit_logs',
        "actor_type IN ('admin', 'guest', 'system')",
    )


def downgrade() -> None:
    # Re-tightening to admin/guest only would fail if any 'system' rows
    # already exist. Migrate them back to 'admin' attribution first.
    op.execute(
        "UPDATE audit_logs SET actor_type = 'admin' WHERE actor_type = 'system'"
    )
    op.drop_constraint('valid_actor_type', 'audit_logs', type_='check')
    op.create_check_constraint(
        'valid_actor_type',
        'audit_logs',
        "actor_type IN ('admin', 'guest')",
    )
