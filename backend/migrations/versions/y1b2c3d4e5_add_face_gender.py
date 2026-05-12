"""add gender column to faces table

Revision ID: y1b2c3d4e5
Revises: x0a1b2c3d4
Create Date: 2026-05-12 17:30:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = 'y1b2c3d4e5'
down_revision = 'x0a1b2c3d4'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Gender label from the CompreFace demographics plugin (typical values:
    # 'male', 'female', or NULL when the plugin is disabled / inconclusive).
    op.add_column(
        'faces',
        sa.Column('gender', sa.String(length=16), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('faces', 'gender')
