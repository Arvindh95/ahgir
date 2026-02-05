"""Initial schema with pgvector support

Revision ID: 001
Revises: 
Create Date: 2024-01-01 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
import uuid

# revision identifiers, used by Alembic.
revision = '001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Enable pgvector extension
    op.execute('CREATE EXTENSION IF NOT EXISTS vector')
    
    # Create users table
    op.create_table(
        'users',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column('email', sa.String(255), nullable=False, unique=True),
        sa.Column('password_hash', sa.String(255), nullable=False),
        sa.Column('created_at', sa.TIMESTAMP, server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.TIMESTAMP, server_default=sa.func.now(), nullable=False),
    )
    op.create_index('ix_users_email', 'users', ['email'])
    
    # Create events table
    op.create_table(
        'events',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column('owner_user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('slug', sa.String(255), nullable=False, unique=True),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('date', sa.Date),
        sa.Column('passcode_hash', sa.String(255)),
        sa.Column('allow_downloads', sa.Boolean, default=True, nullable=False),
        sa.Column('retention_days', sa.Integer, default=90, nullable=False),
        sa.Column('created_at', sa.TIMESTAMP, server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.TIMESTAMP, server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['owner_user_id'], ['users.id'], ondelete='CASCADE'),
    )
    op.create_index('ix_events_owner_user_id', 'events', ['owner_user_id'])
    op.create_index('ix_events_slug', 'events', ['slug'])
    
    # Create images table
    op.create_table(
        'images',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column('event_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('filename', sa.String(255), nullable=False),
        sa.Column('file_hash', sa.String(64), nullable=False),
        sa.Column('size_bytes', sa.BigInteger, nullable=False),
        sa.Column('width', sa.Integer),
        sa.Column('height', sa.Integer),
        sa.Column('exif_data', postgresql.JSONB),
        sa.Column('status', sa.String(20), nullable=False),
        sa.Column('face_count', sa.Integer, default=0, nullable=False),
        sa.Column('uploaded_at', sa.TIMESTAMP, server_default=sa.func.now(), nullable=False),
        sa.Column('indexed_at', sa.TIMESTAMP),
        sa.ForeignKeyConstraint(['event_id'], ['events.id'], ondelete='CASCADE'),
        sa.CheckConstraint("status IN ('pending', 'indexed', 'no_faces', 'failed')", name='valid_status'),
    )
    op.create_index('ix_images_event_id', 'images', ['event_id'])
    op.create_index('ix_images_status', 'images', ['status'])
    op.create_index('idx_event_hash', 'images', ['event_id', 'file_hash'])
    op.create_index('unique_hash_per_event', 'images', ['event_id', 'file_hash'], unique=True)
    
    # Create faces table with vector column
    op.create_table(
        'faces',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column('image_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('event_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('bbox', postgresql.ARRAY(sa.Float), nullable=False),
        sa.Column('quality_score', sa.Float, nullable=False),
        sa.Column('created_at', sa.TIMESTAMP, server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['image_id'], ['images.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['event_id'], ['events.id'], ondelete='CASCADE'),
    )
    
    # Add vector column separately (pgvector specific)
    op.execute('ALTER TABLE faces ADD COLUMN embedding vector(512) NOT NULL')
    
    op.create_index('ix_faces_image_id', 'faces', ['image_id'])
    op.create_index('ix_faces_event_id', 'faces', ['event_id'])
    
    # Create vector similarity index (ivfflat)
    op.execute(
        'CREATE INDEX idx_faces_embedding ON faces '
        'USING ivfflat (embedding vector_cosine_ops) '
        'WITH (lists = 100)'
    )
    
    # Create guest_sessions table
    op.create_table(
        'guest_sessions',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column('event_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('session_token', sa.String(255), nullable=False, unique=True),
        sa.Column('expires_at', sa.TIMESTAMP, nullable=False),
        sa.Column('created_at', sa.TIMESTAMP, server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['event_id'], ['events.id'], ondelete='CASCADE'),
    )
    op.create_index('ix_guest_sessions_event_id', 'guest_sessions', ['event_id'])
    op.create_index('ix_guest_sessions_session_token', 'guest_sessions', ['session_token'])
    
    # Create audit_logs table
    op.create_table(
        'audit_logs',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column('event_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('actor_type', sa.String(20), nullable=False),
        sa.Column('actor_id', postgresql.UUID(as_uuid=True)),
        sa.Column('action', sa.String(50), nullable=False),
        sa.Column('metadata', postgresql.JSONB),
        sa.Column('timestamp', sa.TIMESTAMP, server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['event_id'], ['events.id'], ondelete='CASCADE'),
        sa.CheckConstraint("actor_type IN ('admin', 'guest')", name='valid_actor_type'),
    )
    op.create_index('ix_audit_logs_event_id', 'audit_logs', ['event_id'])
    op.create_index('ix_audit_logs_timestamp', 'audit_logs', ['timestamp'])
    
    # Create rate_limits table
    op.create_table(
        'rate_limits',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column('session_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('action', sa.String(50), nullable=False),
        sa.Column('count', sa.Integer, default=1, nullable=False),
        sa.Column('window_start', sa.TIMESTAMP, nullable=False),
    )
    op.create_index('idx_session_action_window', 'rate_limits', ['session_id', 'action', 'window_start'])


def downgrade() -> None:
    # Drop tables in reverse order
    op.drop_table('rate_limits')
    op.drop_table('audit_logs')
    op.drop_table('guest_sessions')
    op.drop_table('faces')
    op.drop_table('images')
    op.drop_table('events')
    op.drop_table('users')
    
    # Drop pgvector extension
    op.execute('DROP EXTENSION IF EXISTS vector')
