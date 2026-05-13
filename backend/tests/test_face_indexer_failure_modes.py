"""
Regression tests for the face-indexing failure-mode review:

P1 — CompreFace upstream failures must NOT be saved as no_faces.
P2 — Worker exception handler must rollback before marking the image failed,
     so partially-added Face rows don't leak.

Note: these tests bypass the `db_session` fixture because the worker
calls `db.rollback()` in its exception path (legitimate production
behaviour). The fixture wraps the entire test in one connection-level
transaction, so that rollback also wipes the test's seed data. We
instead build a fresh per-test session against the test engine, do
real commits, and clean up by hand.
"""
import io
import uuid

import pytest
from PIL import Image as PILImage
from sqlalchemy.orm import Session, sessionmaker

from app.models import Event, Image, Face, User
from app.workers import face_indexer_compreface as fic


def _async_return(value):
    """Build an `async def` callable that returns `value` — needed because the
    worker pipes its CompreFace helpers through `_run_async(coro)` which
    expects an actual coroutine object."""
    async def _fn(*args, **kwargs):
        return value
    return _fn


def _async_raise(exc):
    async def _fn(*args, **kwargs):
        raise exc
    return _fn


def _jpeg_bytes(width: int = 100, height: int = 100) -> bytes:
    img = PILImage.new("RGB", (width, height), (220, 220, 220))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    buf.seek(0)
    return buf.getvalue()


def _seed_event_and_image(session: Session) -> tuple[Event, Image]:
    user = User(email=f"owner-{uuid.uuid4().hex}@example.com", password_hash="h", is_verified=True)
    session.add(user)
    session.flush()

    event = Event(
        owner_user_id=user.id,
        slug=f"e-{uuid.uuid4().hex[:8]}",
        name="Indexer test",
        retention_days=30,
        status="active",
    )
    session.add(event)
    session.flush()

    img = Image(
        id=uuid.uuid4(),
        event_id=event.id,
        filename="t.jpg",
        file_hash=uuid.uuid4().hex + uuid.uuid4().hex,
        size_bytes=10,
        width=10,
        height=10,
        status="pending",
        face_count=0,
    )
    session.add(img)
    session.commit()
    session.refresh(img)
    return event, img


@pytest.fixture
def real_session(engine, tables):
    """Per-test session that does real commits + hand-rolled cleanup.

    The standard db_session fixture wraps every test in one transaction
    that gets rolled back at teardown. That conflicts with worker code
    that legitimately calls db.rollback() during its exception path —
    the worker's rollback unwinds the test's own seed inserts.
    """
    TestSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    s = TestSession()
    # Track every Image / Face / Event / User we add so cleanup wipes them.
    created_image_ids: list = []
    created_event_ids: list = []
    created_user_ids: list = []

    yield s, created_image_ids, created_event_ids, created_user_ids

    # Cleanup: faces and audit_logs cascade from event delete, so we just
    # need to wipe images-with-no-event-cascade and the events themselves.
    cleanup = TestSession()
    try:
        if created_image_ids:
            cleanup.query(Face).filter(Face.image_id.in_(created_image_ids)).delete(synchronize_session=False)
            cleanup.query(Image).filter(Image.id.in_(created_image_ids)).delete(synchronize_session=False)
        if created_event_ids:
            cleanup.query(Event).filter(Event.id.in_(created_event_ids)).delete(synchronize_session=False)
        if created_user_ids:
            cleanup.query(User).filter(User.id.in_(created_user_ids)).delete(synchronize_session=False)
        cleanup.commit()
    finally:
        cleanup.close()
    s.close()


def test_detection_upstream_failure_marks_image_failed_and_raises(real_session, monkeypatch):
    """If detection returns 5xx / network error / timeout, the worker must
    end the job with status='failed' and re-raise so RQ retries — NOT save
    a successful no_faces (which would hide the failure forever).
    """
    session, image_ids, event_ids, user_ids = real_session
    event, img = _seed_event_and_image(session)
    image_ids.append(img.id); event_ids.append(event.id); user_ids.append(event.owner_user_id)

    monkeypatch.setattr(fic.storage_service, "get_photo", lambda **kwargs: _jpeg_bytes())
    monkeypatch.setattr(
        fic, "_detect_faces_compreface",
        _async_raise(fic.CompreFaceUpstreamError("simulated 503 from CompreFace")),
    )

    with pytest.raises(fic.CompreFaceUpstreamError):
        fic.index_photo_compreface(str(img.id), api_key="x", db_session=session)

    session.expire_all()
    refreshed = session.query(Image).filter(Image.id == img.id).first()
    assert refreshed.status == "failed", "upstream failure must NOT save as no_faces or indexed"


def test_all_add_face_upstream_failures_raise_not_no_faces(real_session, monkeypatch):
    """If detection finds N faces but every add_face fails with an upstream
    error, the worker must raise — preserving the chance to retry — not
    silently mark the image no_faces.
    """
    session, image_ids, event_ids, user_ids = real_session
    event, img = _seed_event_and_image(session)
    image_ids.append(img.id); event_ids.append(event.id); user_ids.append(event.owner_user_id)

    monkeypatch.setattr(fic.storage_service, "get_photo", lambda **kwargs: _jpeg_bytes(600, 400))
    detected = [
        {"box": {"x_min": 0, "y_min": 0, "x_max": 200, "y_max": 200, "probability": 0.99}},
        {"box": {"x_min": 300, "y_min": 0, "x_max": 500, "y_max": 200, "probability": 0.98}},
    ]
    monkeypatch.setattr(fic, "_detect_faces_compreface", _async_return(detected))
    monkeypatch.setattr(
        fic, "_add_face_to_compreface",
        _async_raise(fic.CompreFaceUpstreamError("simulated 502 from CompreFace recognition")),
    )

    with pytest.raises(fic.CompreFaceUpstreamError):
        fic.index_photo_compreface(str(img.id), api_key="x", db_session=session)

    session.expire_all()
    refreshed = session.query(Image).filter(Image.id == img.id).first()
    assert refreshed.status == "failed", "every add_face upstream-failing must NOT save as no_faces"
    assert refreshed.face_count == 0


def test_genuine_zero_detection_does_save_no_faces(db_session: Session, monkeypatch):
    """A 200 OK detection result with an empty list IS a legitimate no_faces."""
    _event, img = _seed_event_and_image(db_session)
    db_session.commit()

    monkeypatch.setattr(fic.storage_service, "get_photo", lambda **kw: _jpeg_bytes())
    monkeypatch.setattr(fic, "_detect_faces_compreface", _async_return([]))

    result = fic.index_photo_compreface(str(img.id), api_key="x", db_session=db_session)

    db_session.refresh(img)
    assert img.status == "no_faces"
    assert result["face_count"] == 0


def test_worker_exception_does_not_leak_partial_face_rows(real_session, monkeypatch):
    """If add_face raises mid-loop after some Face rows were added, the
    exception handler must rollback so partial rows aren't committed
    alongside image.status='failed'. Pre-fix the partial rows persisted.
    """
    session, image_ids, event_ids, user_ids = real_session
    event, img = _seed_event_and_image(session)
    image_ids.append(img.id); event_ids.append(event.id); user_ids.append(event.owner_user_id)

    monkeypatch.setattr(fic.storage_service, "get_photo", lambda **kw: _jpeg_bytes(600, 400))
    monkeypatch.setattr(
        fic, "_detect_faces_compreface",
        _async_return([
            {"box": {"x_min": 0, "y_min": 0, "x_max": 200, "y_max": 200, "probability": 0.99}},
            {"box": {"x_min": 300, "y_min": 0, "x_max": 500, "y_max": 200, "probability": 0.98}},
        ]),
    )

    # First face succeeds, second triggers a non-CompreFace error (something
    # in the worker code itself) to land in the outer except block.
    calls = {"n": 0}

    async def _add(face_bytes, subject_id, api_key, det_prob_threshold=0.5):
        calls["n"] += 1
        if calls["n"] == 1:
            return {"image_id": "ok"}  # success — Face row will be staged on the session
        raise RuntimeError("simulated crash after first face added")

    monkeypatch.setattr(fic, "_add_face_to_compreface", _add)

    with pytest.raises(RuntimeError):
        fic.index_photo_compreface(str(img.id), api_key="x", db_session=session)

    session.expire_all()
    refreshed = session.query(Image).filter(Image.id == img.id).first()
    assert refreshed.status == "failed"
    # No Face rows should be committed because the exception handler rolls back
    # before flipping the image status.
    leaked = session.query(Face).filter(Face.image_id == img.id).count()
    assert leaked == 0, f"{leaked} stale Face row(s) leaked from a failed indexing job"


def test_retry_clears_stale_face_rows(db_session: Session, monkeypatch):
    """A retry of a previously-failed job must NOT stack on top of stale
    Face rows from the prior attempt — the job clears them at start.
    """
    _event, img = _seed_event_and_image(db_session)
    # Pretend a prior attempt left two Face rows.
    db_session.add(Face(
        image_id=img.id, event_id=img.event_id,
        embedding=[0.0] * 512, bbox=[0, 0, 1, 1],
        quality_score=0.9, compreface_subject_id="stale/1",
    ))
    db_session.add(Face(
        image_id=img.id, event_id=img.event_id,
        embedding=[0.0] * 512, bbox=[0, 0, 1, 1],
        quality_score=0.9, compreface_subject_id="stale/2",
    ))
    db_session.commit()
    assert db_session.query(Face).filter(Face.image_id == img.id).count() == 2

    monkeypatch.setattr(fic.storage_service, "get_photo", lambda **kw: _jpeg_bytes())
    # No new faces detected this retry — but the stale rows from prior
    # attempt should be cleared regardless.
    monkeypatch.setattr(fic, "_detect_faces_compreface", _async_return([]))

    fic.index_photo_compreface(str(img.id), api_key="x", db_session=db_session)

    db_session.refresh(img)
    assert img.status == "no_faces"
    assert db_session.query(Face).filter(Face.image_id == img.id).count() == 0, "stale faces must be cleared on retry"
