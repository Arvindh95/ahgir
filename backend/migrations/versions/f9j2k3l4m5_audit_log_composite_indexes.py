"""composite indexes on audit_logs for analytics paths

The analytics dashboards (per-event ``/events/{id}/analytics`` and the
superadmin ``/admin/stats``) filter audit_logs by (action, timestamp),
(event_id, action, timestamp), and (actor_type, timestamp). The base
schema only indexed event_id and timestamp individually, so every
analytics query did a full table scan once the audit log grew past a
few thousand rows. These composite indexes turn those into index
scans.

Revision ID: f9j2k3l4m5
Revises: e8g9h0i1j2
Create Date: 2026-05-14 10:00:00.000000
"""
from alembic import op


revision = 'f9j2k3l4m5'
down_revision = 'e8g9h0i1j2'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # IF NOT EXISTS so re-running the migration on a partially-applied
    # DB doesn't fail. Plain CREATE INDEX (not CONCURRENTLY) because
    # this migration runs inside Alembic's transaction; audit_logs is
    # small enough that the brief lock is acceptable. If the table
    # ever grows enough to make the lock noticeable, switch to a
    # custom out-of-band migration that uses CREATE INDEX CONCURRENTLY.
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_audit_action_timestamp
        ON audit_logs (action, timestamp DESC);
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_audit_event_action_timestamp
        ON audit_logs (event_id, action, timestamp DESC);
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_audit_actor_type_timestamp
        ON audit_logs (actor_type, timestamp DESC);
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_audit_actor_type_timestamp;")
    op.execute("DROP INDEX IF EXISTS idx_audit_event_action_timestamp;")
    op.execute("DROP INDEX IF EXISTS idx_audit_action_timestamp;")
