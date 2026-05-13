"""
Regression tests for the face-indexing failure-mode review:

P1 — CompreFace upstream failures must NOT be saved as no_faces.
P2 — Worker exception handler must rollback before marking the image failed,
     so partially-added Face rows don't leak.
"""
import uuid
from unittest.mock import patch

import pytest
from sqlalchemy.orm import Session

from app.models import Event, Image, Face, User
from app.workers import face_indexer_compreface as fic


def _seed_event_and_image(db_session: Session) -> tuple[Event, Image]:
    user = User(email=f"owner-{uuid.uuid4().hex}@example.com", password_hash="h", is_verified=True)
    db_session.add(user)
    db_session.flush()

    event = Event(
        owner_user_id=user.id,
        slug=f"e-{uuid.uuid4().hex[:8]}",
        name="Indexer test",
        retention_days=30,
        status="active",
    )
    db_session.add(event)
    db_session.flush()

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
    db_session.add(img)
    db_session.flush()
    return event, img


def test_detection_upstream_failure_marks_image_failed_and_raises(db_session: Session, monkeypatch):
    """If detection returns 5xx / network error / timeout, the worker must
    end the job with status='failed' and re-raise so RQ retries — NOT save
    a successful no_faces (which would hide the failure forever).
    """
    _event, img = _seed_event_and_image(db_session)
    db_session.commit()

    def _raise_upstream(*args, **kwargs):
        raise fic.CompreFaceUpstreamError("simulated 503 from CompreFace")

    # Skip MinIO entirely — the failure must surface BEFORE we even reach
    # detection. We patch storage to return a minimal valid JPEG.
    monkeypatch.setattr(
        fic.storage_service,
        "get_photo",
        lambda **kwargs: b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00\xff\xd9",
    )
    # The image-open path uses PIL on the bytes; safe_open should accept the
    # minimal JPEG above. Patch detection to throw upstream.
    monkeypatch.setattr(fic, "_detect_faces_compreface", _raise_upstream)

    with pytest.raises(fic.CompreFaceUpstreamError):
        fic.index_photo_compreface(str(img.id), api_key="x", db_session=db_session)

    db_session.refresh(img)
    assert img.status == "failed", "upstream failure must NOT save as no_faces or indexed"


def test_all_add_face_upstream_failures_raise_not_no_faces(db_session: Session, monkeypatch):
    """If detection finds N faces but every add_face fails with an upstream
    error, the worker must raise — preserving the chance to retry — not
    silently mark the image no_faces.
    """
    _event, img = _seed_event_and_image(db_session)
    db_session.commit()

    monkeypatch.setattr(
        fic.storage_service,
        "get_photo",
        lambda **kwargs: b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00\xff\xd9",
    )
    # Detection finds two large high-confidence faces.
    monkeypatch.setattr(
        fic, "_detect_faces_compreface",
        lambda *a, **kw: [
            {"box": {"x_min": 0, "y_min": 0, "x_max": 200, "y_max": 200, "probability": 0.99}},
            {"box": {"x_min": 300, "y_min": 0, "x_max": 500, "y_max": 200, "probability": 0.98}},
        ]
    )
    # Replace the image bytes with one that PIL can actually crop from.
    import io
    from PIL import Image as PILImage
    big = PILImage.new("RGB", (600, 400), (200, 200, 200))
    buf = io.BytesIO(); big.save(buf, format="JPEG"); buf.seek(0)
    monkeypatch.setattr(fic.storage_service, "get_photo", lambda **kw: buf.getvalue())

    def _raise_upstream(*args, **kwargs):
        raise fic.CompreFaceUpstreamError("simulated 502 from CompreFace recognition")

    monkeypatch.setattr(fic, "_add_face_to_compreface", _raise_upstream)

    with pytest.raises(fic.CompreFaceUpstreamError):
        fic.index_photo_compreface(str(img.id), api_key="x", db_session=db_session)

    db_session.refresh(img)
    assert img.status == "failed", "every add_face upstream-failing must NOT save as no_faces"
    assert img.face_count == 0


def test_genuine_zero_detection_does_save_no_faces(db_session: Session, monkeypatch):
    """A 200 OK detection result with an empty list IS a legitimate no_faces."""
    _event, img = _seed_event_and_image(db_session)
    db_session.commit()

    import io
    from PIL import Image as PILImage
    blank = PILImage.new("RGB", (100, 100), (255, 255, 255))
    buf = io.BytesIO(); blank.save(buf, format="JPEG"); buf.seek(0)
    monkeypatch.setattr(fic.storage_service, "get_photo", lambda **kw: buf.getvalue())
    monkeypatch.setattr(fic, "_detect_faces_compreface", lambda *a, **kw: [])

    result = fic.index_photo_compreface(str(img.id), api_key="x", db_session=db_session)

    db_session.refresh(img)
    assert img.status == "no_faces"
    assert result["face_count"] == 0


def test_worker_exception_does_not_leak_partial_face_rows(db_session: Session, monkeypatch):
    """If add_face raises mid-loop after some Face rows were added, the
    exception handler must rollback so partial rows aren't committed
    alongside image.status='failed'. Pre-fix the partial rows persisted.
    """
    _event, img = _seed_event_and_image(db_session)
    db_session.commit()

    import io
    from PIL import Image as PILImage
    big = PILImage.new("RGB", (600, 400), (200, 200, 200))
    buf = io.BytesIO(); big.save(buf, format="JPEG"); buf.seek(0)
    monkeypatch.setattr(fic.storage_service, "get_photo", lambda **kw: buf.getvalue())

    monkeypatch.setattr(
        fic, "_detect_faces_compreface",
        lambda *a, **kw: [
            {"box": {"x_min": 0, "y_min": 0, "x_max": 200, "y_max": 200, "probability": 0.99}},
            {"box": {"x_min": 300, "y_min": 0, "x_max": 500, "y_max": 200, "probability": 0.98}},
        ]
    )

    # First face succeeds, second triggers a non-CompreFace error (something
    # in the worker code itself) to land in the outer except block.
    calls = {"n": 0}

    def _add(face_bytes, subject_id, api_key, det_prob_threshold=0.5):
        calls["n"] += 1
        if calls["n"] == 1:
            return {"image_id": "ok"}  # success — Face row will be staged on the session
        raise RuntimeError("simulated crash after first face added")

    monkeypatch.setattr(fic, "_add_face_to_compreface", _add)

    with pytest.raises(RuntimeError):
        fic.index_photo_compreface(str(img.id), api_key="x", db_session=db_session)

    db_session.refresh(img)
    assert img.status == "failed"
    # No Face rows should be committed because the exception handler rolls back
    # before flipping the image status.
    leaked = db_session.query(Face).filter(Face.image_id == img.id).count()
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

    import io
    from PIL import Image as PILImage
    blank = PILImage.new("RGB", (100, 100), (255, 255, 255))
    buf = io.BytesIO(); blank.save(buf, format="JPEG"); buf.seek(0)
    monkeypatch.setattr(fic.storage_service, "get_photo", lambda **kw: buf.getvalue())
    # No new faces detected this retry — but the stale rows from prior
    # attempt should be cleared regardless.
    monkeypatch.setattr(fic, "_detect_faces_compreface", lambda *a, **kw: [])

    fic.index_photo_compreface(str(img.id), api_key="x", db_session=db_session)

    db_session.refresh(img)
    assert img.status == "no_faces"
    assert db_session.query(Face).filter(Face.image_id == img.id).count() == 0, "stale faces must be cleared on retry"
