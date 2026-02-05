"""add_compreface_subject_id_to_faces

Revision ID: 2b317bc8e1cd
Revises: fb5fead30de1
Create Date: 2026-02-05 02:29:41.405661

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '2b317bc8e1cd'
down_revision = 'fb5fead30de1'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add compreface_subject_id column to faces table
    op.add_column('faces', sa.Column('compreface_subject_id', sa.String(length=255), nullable=True))


def downgrade() -> None:
    # Remove compreface_subject_id column from faces table
    op.drop_column('faces', 'compreface_subject_id')
