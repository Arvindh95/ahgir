from sqlalchemy import Column, String, Integer, BigInteger, Boolean, Date, Float, ForeignKey, Index, TIMESTAMP, ARRAY, CheckConstraint
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from pgvector.sqlalchemy import Vector
import uuid

from app.database import Base

class User(Base):
    __tablename__ = "users"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    is_verified = Column(Boolean, default=False, nullable=False)
    is_superadmin = Column(Boolean, default=False, nullable=False)
    is_disabled = Column(Boolean, default=False, nullable=False)
    created_at = Column(TIMESTAMP, server_default=func.now(), nullable=False)
    updated_at = Column(TIMESTAMP, server_default=func.now(), onupdate=func.now(), nullable=False)
    
    # Relationships
    events = relationship("Event", back_populates="owner", cascade="all, delete-orphan")

class Event(Base):
    __tablename__ = "events"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    slug = Column(String(255), unique=True, nullable=False, index=True)
    name = Column(String(255), nullable=False)
    date = Column(Date)
    passcode_hash = Column(String(255))  # NULL if no passcode
    location = Column(String(500), nullable=True)
    description = Column(String(2000), nullable=True)
    cover_image = Column(String(500), nullable=True)  # MinIO object key for cover image
    allow_downloads = Column(Boolean, default=True, nullable=False)
    retention_days = Column(Integer, default=90, nullable=False)
    created_at = Column(TIMESTAMP, server_default=func.now(), nullable=False)
    updated_at = Column(TIMESTAMP, server_default=func.now(), onupdate=func.now(), nullable=False)
    
    # Relationships
    owner = relationship("User", back_populates="events")
    images = relationship("Image", back_populates="event", cascade="all, delete-orphan")
    faces = relationship("Face", back_populates="event", cascade="all, delete-orphan")
    guest_sessions = relationship("GuestSession", back_populates="event", cascade="all, delete-orphan")
    audit_logs = relationship("AuditLog", back_populates="event", cascade="all, delete-orphan")
    tier = relationship("EventTier", back_populates="event", uselist=False, cascade="all, delete-orphan")

class Image(Base):
    __tablename__ = "images"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    event_id = Column(UUID(as_uuid=True), ForeignKey("events.id", ondelete="CASCADE"), nullable=False, index=True)
    filename = Column(String(255), nullable=False)
    file_hash = Column(String(64), nullable=False)  # SHA256 for deduplication
    size_bytes = Column(BigInteger, nullable=False)
    width = Column(Integer)
    height = Column(Integer)
    exif_data = Column(JSONB)
    status = Column(String(20), nullable=False, index=True)  # pending, indexed, no_faces, failed
    face_count = Column(Integer, default=0, nullable=False)
    uploaded_at = Column(TIMESTAMP, server_default=func.now(), nullable=False)
    indexed_at = Column(TIMESTAMP)
    
    # Relationships
    event = relationship("Event", back_populates="images")
    faces = relationship("Face", back_populates="image", cascade="all, delete-orphan")
    
    # Indexes and constraints
    __table_args__ = (
        Index("idx_event_filename", "event_id", "filename"),
        CheckConstraint("status IN ('pending', 'indexed', 'no_faces', 'failed')", name="valid_status"),
        {"schema": None}
    )

# Unique filename per event
Index("unique_filename_per_event", Image.event_id, Image.filename, unique=True)

class Face(Base):
    __tablename__ = "faces"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    image_id = Column(UUID(as_uuid=True), ForeignKey("images.id", ondelete="CASCADE"), nullable=False, index=True)
    event_id = Column(UUID(as_uuid=True), ForeignKey("events.id", ondelete="CASCADE"), nullable=False, index=True)
    embedding = Column(Vector(512), nullable=False)  # pgvector type
    bbox = Column(ARRAY(Float), nullable=False)  # [x1, y1, x2, y2]
    quality_score = Column(Float, nullable=False)
    compreface_subject_id = Column(String(255), nullable=True, index=True)  # CompreFace reference
    created_at = Column(TIMESTAMP, server_default=func.now(), nullable=False)

    # Relationships
    image = relationship("Image", back_populates="faces")
    event = relationship("Event", back_populates="faces")

class GuestSession(Base):
    __tablename__ = "guest_sessions"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    event_id = Column(UUID(as_uuid=True), ForeignKey("events.id", ondelete="CASCADE"), nullable=False, index=True)
    session_token = Column(String(512), unique=True, nullable=False, index=True)  # Increased to 512 for JWT tokens
    expires_at = Column(TIMESTAMP, nullable=False)
    created_at = Column(TIMESTAMP, server_default=func.now(), nullable=False)
    
    # Relationships
    event = relationship("Event", back_populates="guest_sessions")

class AuditLog(Base):
    __tablename__ = "audit_logs"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    event_id = Column(UUID(as_uuid=True), ForeignKey("events.id", ondelete="CASCADE"), nullable=False, index=True)
    actor_type = Column(String(20), nullable=False)  # admin, guest
    actor_id = Column(UUID(as_uuid=True))  # user_id or session_id
    action = Column(String(50), nullable=False)  # access, scan, upload, reindex, delete
    metadata_ = Column("metadata", JSONB)  # Use metadata_ as attribute name, metadata as column name
    timestamp = Column(TIMESTAMP, server_default=func.now(), nullable=False, index=True)
    
    # Relationships
    event = relationship("Event", back_populates="audit_logs")
    
    # Constraints
    __table_args__ = (
        CheckConstraint("actor_type IN ('admin', 'guest')", name="valid_actor_type"),
        {"schema": None}
    )

class EventTier(Base):
    __tablename__ = "event_tiers"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    event_id = Column(UUID(as_uuid=True), ForeignKey("events.id", ondelete="CASCADE"), unique=True, nullable=False, index=True)
    tier_name = Column(String(50), nullable=False, default="free")  # free, standard, premium, custom
    photo_limit = Column(Integer, nullable=False, default=25)
    price_cents = Column(Integer, nullable=False, default=0)  # Price in sen (MYR cents). 50000 = RM500
    currency = Column(String(3), nullable=False, default="myr")
    is_active = Column(Boolean, default=True, nullable=False)
    activated_at = Column(TIMESTAMP, nullable=True)
    created_at = Column(TIMESTAMP, server_default=func.now(), nullable=False)
    updated_at = Column(TIMESTAMP, server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    event = relationship("Event", back_populates="tier")
    payments = relationship("Payment", back_populates="event_tier", cascade="all, delete-orphan")

    __table_args__ = (
        CheckConstraint("tier_name IN ('free', 'standard', 'premium', 'custom')", name="valid_tier_name"),
        {"schema": None}
    )


class Payment(Base):
    __tablename__ = "payments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    event_tier_id = Column(UUID(as_uuid=True), ForeignKey("event_tiers.id", ondelete="CASCADE"), nullable=True, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    stripe_checkout_session_id = Column(String(255), unique=True, nullable=False, index=True)
    stripe_payment_intent_id = Column(String(255), unique=True, nullable=True, index=True)
    amount_cents = Column(Integer, nullable=False)
    currency = Column(String(3), nullable=False, default="myr")
    status = Column(String(30), nullable=False, default="pending")  # pending, completed, failed, refunded
    metadata_ = Column("metadata", JSONB, nullable=True)
    created_at = Column(TIMESTAMP, server_default=func.now(), nullable=False)
    updated_at = Column(TIMESTAMP, server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    event_tier = relationship("EventTier", back_populates="payments")
    user = relationship("User")

    __table_args__ = (
        CheckConstraint("status IN ('pending', 'completed', 'failed', 'refunded')", name="valid_payment_status"),
        {"schema": None}
    )


class RateLimit(Base):
    __tablename__ = "rate_limits"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id = Column(UUID(as_uuid=True), nullable=False)
    action = Column(String(50), nullable=False)  # scan
    count = Column(Integer, default=1, nullable=False)
    window_start = Column(TIMESTAMP, nullable=False)
    
    # Indexes
    __table_args__ = (
        Index("idx_session_action_window", "session_id", "action", "window_start"),
        {"schema": None}
    )
