"""
Regression tests for the stale-pending / enqueue-failure reconciler:

P2 — Upload-time enqueue failures (Redis hiccup) marked the image as
     'failed' but the reconciler only retried 'pending'. Result: a
     brief Redis blip permanently de-indexed photos until an admin
     manually reindexed the event. The reconciler now joins audit
     rows for ``index_enqueue_failed`` and recovers those images too.

P3 — Without deterministic job ids, a multi-day worker outage let
     the daily reconciler stack identical jobs for the same image.
     enqueue_face_indexing now passes ``job_id=index:{image_id}``;
     duplicate enqueues raise JobAlreadyQueued which the reconciler
     swallows as a no-op.

P3 — A genuine indexing failure (worker actually ran and CompreFace
     errored) must NOT be retried by this reconciler. Only enqueue-
     time failures recover automatically.
"""
import uuid
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest
from sqlalchemy.orm import Session

from app.audit import log_action
from app.auth import hash_password
from app.models import AuditLog, Event, Image, User
from app.queue import JobAlreadyQueued
from app.workers.retention_policy import requeue_stale_pending_indexing


def _seed_event(db: Session) -> Event:
    user = User(
        email=f"recon-{uuid.uuid4().hex}@example.com",
        password_hash=hash_password("x"),
        is_verified=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    event = Event(
        owner_user_id=user.id,
        slug=f"e-{uuid.uuid4().hex[:8]}",
        name="Reconciler test event",
        retention_days=30,
        status="active",
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    return event


def _insert_image(db: Session, event_id: uuid.UUID, *, status: str, age_minutes: int) -> Image:
    img = Image(
        id=uuid.uuid4(),
        event_id=event_id,
        filename=f"f-{uuid.uuid4().hex[:6]}.jpg",
        file_hash=uuid.uuid4().hex + uuid.uuid4().hex,
        size_bytes=100,
        width=100,
        height=100,
        status=status,
        face_count=0,
    )
    db.add(img)
    db.commit()
    db.refresh(img)
    # Backdate uploaded_at by raw SQL because the column has a
    # server_default.
    db.execute(
        Image.__table__.update()
        .where(Image.id == img.id)
        .values(uploaded_at=datetime.utcnow() - timedelta(minutes=age_minutes))
    )
    db.commit()
    db.refresh(img)
    return img


def test_pending_image_older_than_stale_minutes_is_requeued(db_session: Session):
    """The original case still works: an image stuck at status='pending'
    older than the stale-minutes window gets re-enqueued."""
    event = _seed_event(db_session)
    stuck = _insert_image(db_session, event.id, status="pending", age_minutes=60)

    enqueued = []
    with patch(
        "app.queue.enqueue_face_indexing",
        side_effect=lambda image_id: enqueued.append(image_id) or "job-1",
    ):
        n = requeue_stale_pending_indexing(db=db_session, stale_minutes=30)

    assert n == 1
    assert str(stuck.id) in enqueued


def test_failed_image_with_enqueue_audit_row_is_recovered(db_session: Session):
    """An image marked 'failed' specifically due to enqueue failure (i.e.
    has an index_enqueue_failed audit row) must be retried and reset to
    'pending' for the worker."""
    event = _seed_event(db_session)
    # Image marked failed by the upload path after enqueue blew up.
    failed_img = _insert_image(db_session, event.id, status="failed", age_minutes=120)
    # And the audit trail that proves it was an enqueue-time failure.
    log_action(
        db=db_session,
        event_id=event.id,
        actor_type="admin",
        actor_id=uuid.uuid4(),
        action="index_enqueue_failed",
        metadata={"image_id": str(failed_img.id), "error": "redis hiccup"},
    )

    enqueued = []
    with patch(
        "app.queue.enqueue_face_indexing",
        side_effect=lambda image_id: enqueued.append(image_id) or "job-1",
    ):
        n = requeue_stale_pending_indexing(db=db_session, stale_minutes=30)

    assert n == 1, "image with index_enqueue_failed audit row must be recovered"
    assert str(failed_img.id) in enqueued

    db_session.refresh(failed_img)
    assert failed_img.status == "pending", (
        "after re-enqueue, image must be reset to pending so the worker's "
        "already-indexed/already-failed guard doesn't make it a no-op"
    )


def test_failed_image_without_enqueue_audit_is_NOT_retried(db_session: Session):
    """A genuine indexing failure (worker ran, CompreFace 5xx'd or image
    was corrupted, etc.) has NO index_enqueue_failed audit row. The
    reconciler must leave it alone — recovery from those failures is a
    manual admin reindex.
    """
    event = _seed_event(db_session)
    # Failed image but NO matching audit row.
    failed_img = _insert_image(db_session, event.id, status="failed", age_minutes=120)

    enqueued = []
    with patch(
        "app.queue.enqueue_face_indexing",
        side_effect=lambda image_id: enqueued.append(image_id) or "job-1",
    ):
        n = requeue_stale_pending_indexing(db=db_session, stale_minutes=30)

    assert n == 0
    assert str(failed_img.id) not in enqueued
    db_session.refresh(failed_img)
    assert failed_img.status == "failed", "genuine failures must stay failed"


def test_job_already_queued_is_treated_as_noop(db_session: Session):
    """If the deterministic job id is already present (e.g., the worker
    has been down so prior reconciler runs already queued it), the
    reconciler must swallow JobAlreadyQueued and not error.
    Multi-day worker outages should not accumulate failures.
    """
    event = _seed_event(db_session)
    stuck = _insert_image(db_session, event.id, status="pending", age_minutes=60)

    def _already_queued(image_id):
        raise JobAlreadyQueued(f"index:{image_id} already exists")

    with patch("app.queue.enqueue_face_indexing", side_effect=_already_queued):
        # Should return 0 (nothing newly queued) but NOT raise.
        n = requeue_stale_pending_indexing(db=db_session, stale_minutes=30)

    assert n == 0
    db_session.refresh(stuck)
    # Image stays in its current state — no harm.
    assert stuck.status == "pending"


def test_audit_row_outside_lookback_window_is_ignored(db_session: Session):
    """A very old index_enqueue_failed audit row (older than the lookback
    window) must NOT trigger re-enqueue. That image's failure is now
    historical; the admin should have noticed by then.
    """
    event = _seed_event(db_session)
    failed_img = _insert_image(db_session, event.id, status="failed", age_minutes=60_000)
    # Stage the audit row, then backdate it past the 7-day lookback.
    log_action(
        db=db_session,
        event_id=event.id,
        actor_type="admin",
        actor_id=uuid.uuid4(),
        action="index_enqueue_failed",
        metadata={"image_id": str(failed_img.id), "error": "old failure"},
    )
    old_audit = (
        db_session.query(AuditLog)
        .filter(AuditLog.action == "index_enqueue_failed")
        .order_by(AuditLog.timestamp.desc())
        .first()
    )
    db_session.execute(
        AuditLog.__table__.update()
        .where(AuditLog.id == old_audit.id)
        .values(timestamp=datetime.utcnow() - timedelta(days=30))
    )
    db_session.commit()

    enqueued = []
    with patch(
        "app.queue.enqueue_face_indexing",
        side_effect=lambda image_id: enqueued.append(image_id) or "job-1",
    ):
        n = requeue_stale_pending_indexing(
            db=db_session,
            stale_minutes=30,
            enqueue_failed_lookback_days=7,
        )

    assert n == 0
    assert str(failed_img.id) not in enqueued
