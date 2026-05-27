"""google_oauth_user_fields

Make users.password_hash nullable (Google-OAuth-only accounts have no
password) and add users.google_sub for the Google identity link.

Revision ID: a4d5e6f7g8
Revises: b4c5d6e7f8
Create Date: 2026-05-27 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a4d5e6f7g8'
down_revision = 'b4c5d6e7f8'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Password is optional once accounts can be created via Google sign-in.
    op.alter_column(
        'users', 'password_hash',
        existing_type=sa.String(length=255),
        nullable=True,
    )
    op.add_column('users', sa.Column('google_sub', sa.String(length=255), nullable=True))
    # Unique index doubles as the lookup index used by the OAuth callback.
    # Name matches SQLAlchemy's create_all output for Column(unique=True,
    # index=True) so the test schema and the migrated schema agree.
    op.create_index('ix_users_google_sub', 'users', ['google_sub'], unique=True)


def downgrade() -> None:
    op.drop_index('ix_users_google_sub', table_name='users')
    op.drop_column('users', 'google_sub')
    # Reverting to NOT NULL fails if any OAuth-only rows (NULL hash) exist;
    # that's expected — you must remove/repair those rows before downgrading.
    op.alter_column(
        'users', 'password_hash',
        existing_type=sa.String(length=255),
        nullable=False,
    )
