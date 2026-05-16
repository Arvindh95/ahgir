import sqlalchemy as sa
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
    # Default=False at both Python AND DB level (migration d7f8g9h0i1
    # corrects the original migration that left the DB default as
    # 'true'). Aligned defaults stop raw INSERT paths from
    # accidentally creating already-verified accounts.
    is_verified = Column(Boolean, default=False, nullable=False, server_default=sa.text('false'))
    is_superadmin = Column(Boolean, default=False, nullable=False)
    is_disabled = Column(Boolean, default=False, nullable=False)
    # Set to NOW() whenever the user's password is reset or changed. Tokens
    # whose iat is before this timestamp are rejected, killing replay of any
    # outstanding access token or password-reset link.
    password_changed_at = Column(TIMESTAMP, nullable=True)
    created_at = Column(TIMESTAMP, server_default=func.now(), nullable=False)
    updated_at = Column(TIMESTAMP, server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    events = relationship("Event", back_populates="owner", cascade="all, delete-orphan")
    user_tier = relationship("UserTier", back_populates="user", uselist=False, cascade="all, delete-orphan")

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
    status = Column(String(20), default='active', nullable=False, index=True)  # active, frozen, expired
    created_at = Column(TIMESTAMP, server_default=func.now(), nullable=False)
    updated_at = Column(TIMESTAMP, server_default=func.now(), onupdate=func.now(), nullable=False)

    # Mirror the DB-level CHECK constraint added in migration s5b6c7d8e9.
    # The Base.metadata.create_all() path used by tests doesn't read live DB
    # constraints, so without this declaration the test schema accepts any
    # string and only production rejects bad values.
    __table_args__ = (
        CheckConstraint("status IN ('active', 'frozen', 'expired')", name="valid_event_status"),
        {"schema": None},
    )

    # Relationships
    owner = relationship("User", back_populates="events")
    images = relationship("Image", back_populates="event", cascade="all, delete-orphan")
    faces = relationship("Face", back_populates="event", cascade="all, delete-orphan")
    guest_sessions = relationship("GuestSession", back_populates="event", cascade="all, delete-orphan")
    # AuditLog rows DELIBERATELY survive event deletion via the FK's
    # ON DELETE SET NULL (see migration a3d4e5f6g7). passive_deletes=True
    # tells SQLAlchemy NOT to preemptively delete audit rows on Event delete,
    # so the DB-level FK action actually fires. Adding cascade="all,
    # delete-orphan" here would silently override the FK and wipe the
    # audit trail, defeating the migration's intent.
    audit_logs = relationship("AuditLog", back_populates="event", passive_deletes=True)
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
    status = Column(String(20), nullable=False, index=True)  # pending, indexed, no_faces, failed, quarantined
    face_count = Column(Integer, default=0, nullable=False)
    uploaded_at = Column(TIMESTAMP, server_default=func.now(), nullable=False)
    indexed_at = Column(TIMESTAMP)

    # Relationships
    event = relationship("Event", back_populates="images")
    faces = relationship("Face", back_populates="image", cascade="all, delete-orphan")
    # AbuseReport rows DELIBERATELY survive image deletion via the FK's
    # ON DELETE SET NULL (see migration e7h8i9j0k1). passive_deletes=True
    # tells SQLAlchemy NOT to preemptively delete report rows when
    # db.delete(image) runs, so the DB-level FK action actually fires and
    # report_id stays in the queue with image_id=NULL for audit history.
    # Adding cascade="all, delete-orphan" here would silently override the
    # FK and wipe the report trail, defeating the migration's intent.
    abuse_reports = relationship("AbuseReport", back_populates="image", passive_deletes=True)

    # Indexes and constraints
    __table_args__ = (
        Index("idx_event_filename", "event_id", "filename"),
        CheckConstraint(
            "status IN ('pending', 'indexed', 'no_faces', 'failed', 'quarantined')",
            name="valid_status",
        ),
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
    # Gender label from the CompreFace demographics plugin ('male' / 'female').
    # NULL when the plugin is disabled or inconclusive.
    gender = Column(String(16), nullable=True)
    # Accuracy-tuning metadata populated by the indexer (technical image quality,
    # not demographic). NULL for legacy rows indexed before these columns existed.
    face_min_side_px = Column(Float, nullable=True)
    blur_score = Column(Float, nullable=True)
    brightness_score = Column(Float, nullable=True)
    crop_clipped = Column(Boolean, nullable=False, default=False, server_default=sa.text('false'))
    # Set by the background same-person clustering job (see face_clustering.py).
    face_cluster_id = Column(UUID(as_uuid=True), nullable=True, index=True)
    created_at = Column(TIMESTAMP, server_default=func.now(), nullable=False)

    # Relationships
    image = relationship("Image", back_populates="faces")
    event = relationship("Event", back_populates="faces")


# Partial unique index on compreface_subject_id (excludes NULLs). Catches the
# race condition where two concurrent face-indexer jobs for the same image both
# clear stale faces and re-insert with overlapping `{event_id}/{image_id}/{seq}`
# subject IDs. Second concurrent insert fails with IntegrityError, the worker's
# row-lock-first approach (see face_indexer_compreface.py) makes the second
# job a no-op anyway, but this is the belt-and-suspenders DB-level guarantee.
Index(
    "uq_faces_compreface_subject_id_not_null",
    Face.compreface_subject_id,
    unique=True,
    postgresql_where=Face.compreface_subject_id.isnot(None),
)


class ScanMatchMetric(Base):
    """One row per (scan, candidate photo) pair — telemetry only.

    Captured at the end of /scan after enhanced scoring runs. Both
    matches that PASSED the threshold (and were returned to the guest)
    AND candidates that were FILTERED are logged, so post-event
    analytics can answer questions like "would lowering the floor
    to 0.85 have surfaced more legitimate photos?". Writing is
    best-effort: a failure here never breaks the scan endpoint.
    """
    __tablename__ = "scan_match_metrics"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # Unique per /scan call. Links a guest's whole scan session back to
    # the set of candidate photos that came out of CompreFace.
    scan_id = Column(UUID(as_uuid=True), nullable=False)
    session_id = Column(UUID(as_uuid=True), nullable=False)
    event_id = Column(UUID(as_uuid=True), ForeignKey("events.id", ondelete="CASCADE"), nullable=False, index=True)
    image_id = Column(UUID(as_uuid=True), ForeignKey("images.id", ondelete="CASCADE"), nullable=False)
    # Raw CompreFace max-of-frames similarity, before any bonus/penalty.
    raw_similarity = Column(Float, nullable=False)
    # After multi_frame_bonus + consistency_bonus + cluster_bonus,
    # minus ambiguous_gap penalty if applied.
    scored_similarity = Column(Float, nullable=False)
    # Difference between this match's scored_similarity and the next
    # match's scored_similarity. NULL on the last ranked candidate.
    score_gap = Column(Float, nullable=True)
    frame_count = Column(Integer, nullable=False)
    # The face-size-bucket threshold this match was compared against
    # (large/medium/small × quality-adjustment). Lets us bucket later.
    threshold_used = Column(Float, nullable=False)
    # True if this match was returned to the guest, False if filtered.
    passed = Column(Boolean, nullable=False)
    # Snapshot of the indexed face's quality fields at the time of the
    # match. NULL for pre-Gap-#1 indexed photos.
    blur_score = Column(Float, nullable=True)
    brightness_score = Column(Float, nullable=True)
    face_min_side_px = Column(Float, nullable=True)
    quality_score = Column(Float, nullable=True)
    cluster_id = Column(UUID(as_uuid=True), nullable=True)
    created_at = Column(TIMESTAMP, server_default=func.now(), nullable=False)


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
    # event_id is nullable: superadmin actions (user updates, tier changes,
    # retried jobs) aren't tied to a specific event. FK is SET NULL so audit
    # trail survives event deletion.
    event_id = Column(UUID(as_uuid=True), ForeignKey("events.id", ondelete="SET NULL"), nullable=True, index=True)
    actor_type = Column(String(20), nullable=False)  # admin, guest, system
    actor_id = Column(UUID(as_uuid=True))  # user_id, session_id, or NULL for system actions
    action = Column(String(50), nullable=False)  # access, scan, upload, reindex, delete
    metadata_ = Column("metadata", JSONB)  # Use metadata_ as attribute name, metadata as column name
    timestamp = Column(TIMESTAMP, server_default=func.now(), nullable=False, index=True)

    # Relationships
    event = relationship("Event", back_populates="audit_logs")

    # Constraints + composite indexes for analytics paths.
    __table_args__ = (
        # 'system' covers automated jobs (retention sweep, scheduled
        # downgrades) so they're not attributed to a human admin in the
        # audit viewer. Migration c6e7f8g9h0 brings the prod DB in line.
        CheckConstraint("actor_type IN ('admin', 'guest', 'system')", name="valid_actor_type"),
        # Global "scans by day", "downloads count", etc. filter by
        # action + timestamp. Without this index those queries did a
        # full scan of audit_logs once the table grew past a few
        # thousand rows. DESC ordering on timestamp matches every
        # callsite that wants the recent window first.
        Index(
            "idx_audit_action_timestamp",
            "action", "timestamp",
            postgresql_ops={"timestamp": "DESC"},
        ),
        # Per-event analytics ("scans-by-day for this event") filter by
        # event_id AND action AND timestamp. The composite covers the
        # common ordering of predicates so Postgres can use the index
        # for both the equality match and the range scan.
        Index(
            "idx_audit_event_action_timestamp",
            "event_id", "action", "timestamp",
            postgresql_ops={"timestamp": "DESC"},
        ),
        # actor_type filters (admin_only / guest_only / system_only in
        # the audit viewer, and unique-guest analytics) get their own
        # index because they're orthogonal to action.
        Index(
            "idx_audit_actor_type_timestamp",
            "actor_type", "timestamp",
            postgresql_ops={"timestamp": "DESC"},
        ),
        {"schema": None}
    )

class UserTier(Base):
    __tablename__ = "user_tiers"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False, index=True)
    tier_name = Column(String(50), nullable=False, default="free")  # free, starter, pro, custom
    max_events = Column(Integer, nullable=False, default=1)  # max active events
    max_photos_per_event = Column(Integer, nullable=False, default=50)
    retention_days = Column(Integer, nullable=True)  # tier-level retention (custom override)
    price_cents = Column(Integer, nullable=False, default=0)
    currency = Column(String(3), nullable=False, default="usd")
    is_active = Column(Boolean, default=True, nullable=False)
    activated_at = Column(TIMESTAMP, nullable=True)

    # Subscription state
    stripe_customer_id = Column(String(255), nullable=True, index=True)
    stripe_subscription_id = Column(String(255), nullable=True, index=True)
    subscription_status = Column(String(30), nullable=True)
    billing_interval = Column(String(10), nullable=True)  # month, year
    current_period_end = Column(TIMESTAMP, nullable=True)
    cancel_at_period_end = Column(Boolean, nullable=False, default=False)
    # Stripe event timestamp of the last subscription.* webhook applied. Used
    # to reject out-of-order deliveries (e.g., a stale subscription.updated
    # arriving after a subscription.deleted has already cleared this row).
    last_subscription_event_at = Column(TIMESTAMP, nullable=True)
    last_subscription_event_id = Column(String(255), nullable=True)
    last_subscription_event_type = Column(String(80), nullable=True)
    last_subscription_event_subscription_id = Column(String(255), nullable=True)

    created_at = Column(TIMESTAMP, server_default=func.now(), nullable=False)
    updated_at = Column(TIMESTAMP, server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    user = relationship("User", back_populates="user_tier")

    __table_args__ = (
        CheckConstraint("tier_name IN ('free', 'starter', 'pro', 'custom')", name="valid_user_tier_name"),
        CheckConstraint(
            "subscription_status IS NULL OR subscription_status IN "
            "('active', 'trialing', 'past_due', 'canceled', 'incomplete', 'incomplete_expired', 'unpaid', 'paused')",
            name="valid_subscription_status",
        ),
        CheckConstraint(
            "billing_interval IS NULL OR billing_interval IN ('month', 'year')",
            name="valid_billing_interval",
        ),
        {"schema": None}
    )


class EventTier(Base):
    """Per-event photo limit override (superadmin only)."""
    __tablename__ = "event_tiers"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    event_id = Column(UUID(as_uuid=True), ForeignKey("events.id", ondelete="CASCADE"), unique=True, nullable=False, index=True)
    tier_name = Column(String(50), nullable=False, default="free")  # kept for backward compat
    photo_limit = Column(Integer, nullable=False, default=50)
    price_cents = Column(Integer, nullable=False, default=0)
    currency = Column(String(3), nullable=False, default="usd")
    is_active = Column(Boolean, default=True, nullable=False)
    activated_at = Column(TIMESTAMP, nullable=True)
    created_at = Column(TIMESTAMP, server_default=func.now(), nullable=False)
    updated_at = Column(TIMESTAMP, server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    event = relationship("Event", back_populates="tier")

    __table_args__ = (
        CheckConstraint("tier_name IN ('free', 'starter', 'pro', 'custom')", name="valid_tier_name"),
        {"schema": None}
    )


class Payment(Base):
    __tablename__ = "payments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    tier_name = Column(String(50), nullable=True)  # what tier was purchased
    stripe_checkout_session_id = Column(String(255), unique=True, nullable=True, index=True)
    stripe_payment_intent_id = Column(String(255), unique=True, nullable=True, index=True)
    stripe_invoice_id = Column(String(255), nullable=True, index=True)
    stripe_subscription_id = Column(String(255), nullable=True, index=True)
    billing_interval = Column(String(10), nullable=True)
    amount_cents = Column(Integer, nullable=False)
    currency = Column(String(3), nullable=False, default="usd")
    status = Column(String(30), nullable=False, default="pending")  # pending, completed, failed, refunded
    metadata_ = Column("metadata", JSONB, nullable=True)
    created_at = Column(TIMESTAMP, server_default=func.now(), nullable=False)
    updated_at = Column(TIMESTAMP, server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    user = relationship("User")

    __table_args__ = (
        CheckConstraint("status IN ('pending', 'completed', 'failed', 'refunded')", name="valid_payment_status"),
        {"schema": None}
    )


Index(
    "uq_payments_stripe_invoice_id_not_null",
    Payment.stripe_invoice_id,
    unique=True,
    postgresql_where=Payment.stripe_invoice_id.isnot(None),
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


class StorageCleanupTask(Base):
    """Tombstone for asynchronous, retried storage / CompreFace cleanups.

    When an in-line cleanup attempt fails (MinIO unavailable, CompreFace 5xx,
    network blip), we used to swallow the error and continue — the DB row
    deletion succeeded, but the original photo bytes / face embeddings
    remained. This table is the durable record so a background drainer can
    keep retrying until storage is genuinely clean.
    """
    __tablename__ = "storage_cleanup_tasks"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # 'event_photos' — delete all MinIO objects for an event_id
    # 'compreface_event' — delete all CompreFace subjects for an event_id
    # 'image_photo' — delete a single image's MinIO objects (event_id + image_id)
    # 'compreface_subject' — delete a single CompreFace subject id
    kind = Column(String(32), nullable=False)
    # Polymorphic payload: keys depend on `kind`.
    payload = Column(JSONB, nullable=False)
    # 'pending' | 'running' | 'failed' (still retryable) | 'done'
    status = Column(String(16), nullable=False, default="pending")
    attempts = Column(Integer, nullable=False, default=0)
    max_attempts = Column(Integer, nullable=False, default=10)
    last_error = Column(sa.Text(), nullable=True)
    last_attempt_at = Column(TIMESTAMP(timezone=True), nullable=True)
    next_attempt_at = Column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
    created_at = Column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
    completed_at = Column(TIMESTAMP(timezone=True), nullable=True)

    __table_args__ = (
        CheckConstraint(
            "kind IN ('event_photos', 'compreface_event', 'image_photo', 'compreface_subject')",
            name="valid_cleanup_kind",
        ),
        CheckConstraint(
            "status IN ('pending', 'running', 'failed', 'done')",
            name="valid_cleanup_status",
        ),
    )


class AbuseReport(Base):
    """A user-filed abuse report against a single photo.

    Reports are per-image and arrive anonymously (or with an optional
    reporter_email) via POST /report. Superadmin reviews each report,
    optionally reveals the image (writes an abuse_review_view audit row),
    and decides: dismiss, quarantine, or remove.

    See ABUSE_REPORTING_PLAN.md for the full design rationale.
    """
    __tablename__ = "abuse_reports"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    image_id = Column(
        UUID(as_uuid=True),
        ForeignKey("images.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    event_id = Column(
        UUID(as_uuid=True),
        ForeignKey("events.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    category = Column(String(32), nullable=False)
    description = Column(sa.Text(), nullable=True)
    reporter_email = Column(String(255), nullable=True)
    reporter_ip = Column(String(45), nullable=False)
    status = Column(String(32), nullable=False, default="pending")
    action_taken = Column(String(32), nullable=True)
    notes = Column(sa.Text(), nullable=True)
    created_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
    reviewed_at = Column(TIMESTAMP(timezone=True), nullable=True)
    reviewed_by = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    image = relationship("Image", back_populates="abuse_reports")

    __table_args__ = (
        CheckConstraint(
            "category IN ('csam', 'nudity', 'harassment', 'copyright', 'violence', 'other')",
            name="valid_abuse_category",
        ),
        CheckConstraint(
            "status IN ('pending', 'reviewing', 'dismissed', 'quarantined', 'removed')",
            name="valid_abuse_status",
        ),
        Index("idx_abuse_status_created", "status", "created_at"),
    )
