"""abuse_reports.image_id ON DELETE SET NULL + make column nullable

P1 fix. /admin/abuse-reports/{id}/delete-photo would db.delete(image),
which cascade-deleted the abuse_reports row via the original FK
constraint (ON DELETE CASCADE). The route still read report.* fields
after the commit — and even when it didn't crash, the queue lost the
durable "report was actioned with status=removed" history we want to
keep for audit purposes.

Switch the FK to ON DELETE SET NULL so deleting the image preserves
the report row with image_id=NULL; the row still surfaces in the queue
with status='removed' and the audit metadata snapshot.

Revision ID: e7h8i9j0k1
Revises: d6g7h8i9j0
Create Date: 2026-05-15 09:30:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = 'e7h8i9j0k1'
down_revision = 'd6g7h8i9j0'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column('abuse_reports', 'image_id', nullable=True)
    # Drop + recreate with the new ondelete behaviour. Postgres names
    # the constraint after the table.column pair by default.
    op.drop_constraint('abuse_reports_image_id_fkey', 'abuse_reports', type_='foreignkey')
    op.create_foreign_key(
        'abuse_reports_image_id_fkey',
        'abuse_reports',
        'images',
        ['image_id'],
        ['id'],
        ondelete='SET NULL',
    )


def downgrade() -> None:
    # On downgrade, surviving rows with image_id=NULL would block the
    # NOT NULL change; null them out by deleting (they're orphan
    # historical rows). The old ondelete=CASCADE is restored after.
    op.execute("DELETE FROM abuse_reports WHERE image_id IS NULL")
    op.drop_constraint('abuse_reports_image_id_fkey', 'abuse_reports', type_='foreignkey')
    op.create_foreign_key(
        'abuse_reports_image_id_fkey',
        'abuse_reports',
        'images',
        ['image_id'],
        ['id'],
        ondelete='CASCADE',
    )
    op.alter_column('abuse_reports', 'image_id', nullable=False)
