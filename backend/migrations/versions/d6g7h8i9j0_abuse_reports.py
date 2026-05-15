"""create abuse_reports table

Second half of the abuse-reporting wiring (ABUSE_REPORTING_PLAN.md).
Anonymous reporters file rows here; superadmin operators review them and
choose dismiss / quarantine / remove.

Revision ID: d6g7h8i9j0
Revises: c5f6g7h8i9
Create Date: 2026-05-15 06:31:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = 'd6g7h8i9j0'
down_revision = 'c5f6g7h8i9'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'abuse_reports',
        sa.Column(
            'id', postgresql.UUID(as_uuid=True),
            primary_key=True, server_default=sa.text('gen_random_uuid()'),
        ),
        sa.Column(
            'image_id', postgresql.UUID(as_uuid=True),
            sa.ForeignKey('images.id', ondelete='CASCADE'),
            nullable=False,
        ),
        sa.Column(
            'event_id', postgresql.UUID(as_uuid=True),
            sa.ForeignKey('events.id', ondelete='CASCADE'),
            nullable=False,
        ),
        sa.Column('category', sa.String(length=32), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('reporter_email', sa.String(length=255), nullable=True),
        sa.Column('reporter_ip', sa.String(length=45), nullable=False),
        sa.Column('status', sa.String(length=32), nullable=False,
                  server_default=sa.text("'pending'")),
        sa.Column('action_taken', sa.String(length=32), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text('now()')),
        sa.Column('reviewed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            'reviewed_by', postgresql.UUID(as_uuid=True),
            sa.ForeignKey('users.id', ondelete='SET NULL'),
            nullable=True,
        ),
        sa.CheckConstraint(
            "category IN ('csam', 'nudity', 'harassment', 'copyright', 'violence', 'other')",
            name='valid_abuse_category',
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'reviewing', 'dismissed', 'quarantined', 'removed')",
            name='valid_abuse_status',
        ),
    )
    # Queue listing: pending/all reports sorted newest first.
    op.create_index(
        'idx_abuse_status_created', 'abuse_reports',
        ['status', sa.text('created_at DESC')],
    )
    # Event-scoped joins (per-event audit feed surfaces only the reports
    # against that event).
    op.create_index('idx_abuse_event_id', 'abuse_reports', ['event_id'])
    # Per-image lookup so the operator review page joins quickly.
    op.create_index('idx_abuse_image_id', 'abuse_reports', ['image_id'])
    # Per-IP rate limiter + reporter-reputation lookups.
    op.create_index(
        'idx_abuse_reporter_ip_created', 'abuse_reports',
        ['reporter_ip', sa.text('created_at DESC')],
    )


def downgrade() -> None:
    op.drop_index('idx_abuse_reporter_ip_created', table_name='abuse_reports')
    op.drop_index('idx_abuse_image_id', table_name='abuse_reports')
    op.drop_index('idx_abuse_event_id', table_name='abuse_reports')
    op.drop_index('idx_abuse_status_created', table_name='abuse_reports')
    op.drop_table('abuse_reports')
