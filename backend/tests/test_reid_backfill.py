"""Phase 1 Re-ID backfill tests.

Covers the backfill worker's contract — only NULL rows are touched, fail-soft
on a down sidecar, degenerate crops skipped, missing originals tolerated, event
scoping — plus the admin enqueue endpoint's auth / validation.

The autouse `_disable_reid_in_tests` fixture (conftest) forces both Re-ID flags
OFF for the rest of the suite; the backfill short-circuits to "skipped" in that
state, so every test that wants real work re-enables indexing via `enable_reid`.
"""
import io
import uuid
from unittest.mock import AsyncMock, patch

import pytest
from PIL import Image as PILImage

from app.auth import create_access_token, hash_password
from app.models import Event, Face, Image, User
from app.workers import reid_backfill


# --------------------------------------------------------------------------- #
# Fixtures / helpers
# --------------------------------------------------------------------------- #

@pytest.fixture
def enable_reid():
    """Re-enable index-side Re-ID for a test (conftest forces it off)."""
    from app.config import settings as app_settings
    original = app_settings.reid_enabled_indexing
    app_settings.reid_enabled_indexing = True
    try:
        yield
    finally:
        app_settings.reid_enabled_indexing = original


def _jpeg_bytes(w: int = 400, h: int = 500) -> bytes:
    buf = io.BytesIO()
    PILImage.new("RGB", (w, h), (123, 117, 104)).save(buf, format="JPEG")
    return buf.getvalue()


def _seed_event(db) -> Event:
    user = User(email=f"u_{uuid.uuid4()}@example.com", password_hash=hash_password("pw"))
    db.add(user)
    db.commit()
    event = Event(
        owner_user_id=user.id,
        slug=f"ev-{uuid.uuid4()}",
        name="Re-ID Event",
        allow_downloads=True,
        retention_days=90,
    )
    db.add(event)
    db.commit()
    return event


def _seed_image_with_face(db, event, *, bbox=None, reid=None) -> tuple[Image, Face]:
    image = Image(
        event_id=event.id,
        filename=f"{uuid.uuid4()}.jpg",
        file_hash=f"h_{uuid.uuid4()}",
        size_bytes=2048,
        width=400,
        height=500,
        status="indexed",
        face_count=1,
    )
    db.add(image)
    db.commit()
    face = Face(
        image_id=image.id,
        event_id=event.id,
        embedding=[0.1] * 512,
        bbox=bbox or [100.0, 100.0, 200.0, 200.0],
        quality_score=0.95,
        reid_embedding=reid,
    )
    db.add(face)
    db.commit()
    return image, face


# --------------------------------------------------------------------------- #
# Worker
# --------------------------------------------------------------------------- #

class TestBackfillWorker:

    def test_fills_only_null_faces(self, test_db, enable_reid):
        """NULL faces get an embedding; already-filled ones are untouched."""
        event = _seed_event(test_db)
        _, null_face = _seed_image_with_face(test_db, event)
        _, filled_face = _seed_image_with_face(test_db, event, reid=[0.2] * 512)

        vec = [0.05] * 512
        with patch.object(reid_backfill, "compute_reid_embedding", new=AsyncMock(return_value=vec)), \
             patch.object(reid_backfill.storage_service, "get_photo", return_value=_jpeg_bytes()):
            result = reid_backfill.backfill_reid_embeddings(event_id=str(event.id), db=test_db)

        assert result["faces_written"] == 1
        assert result["images_total"] == 1, "only the NULL-face image is a candidate"
        test_db.refresh(null_face)
        test_db.refresh(filled_face)
        assert null_face.reid_embedding is not None
        assert list(filled_face.reid_embedding) == pytest.approx([0.2] * 512), "filled row not overwritten"

    def test_idempotent_second_pass_no_candidates(self, test_db, enable_reid):
        event = _seed_event(test_db)
        _seed_image_with_face(test_db, event)
        with patch.object(reid_backfill, "compute_reid_embedding", new=AsyncMock(return_value=[0.05] * 512)), \
             patch.object(reid_backfill.storage_service, "get_photo", return_value=_jpeg_bytes()):
            reid_backfill.backfill_reid_embeddings(event_id=str(event.id), db=test_db)
            second = reid_backfill.backfill_reid_embeddings(event_id=str(event.id), db=test_db)
        assert second["images_total"] == 0
        assert second["faces_written"] == 0

    def test_sidecar_down_leaves_null(self, test_db, enable_reid):
        """compute returns None (sidecar down) → row stays NULL, counted failed."""
        event = _seed_event(test_db)
        _, face = _seed_image_with_face(test_db, event)
        with patch.object(reid_backfill, "compute_reid_embedding", new=AsyncMock(return_value=None)), \
             patch.object(reid_backfill.storage_service, "get_photo", return_value=_jpeg_bytes()):
            result = reid_backfill.backfill_reid_embeddings(event_id=str(event.id), db=test_db)
        assert result["faces_failed"] == 1
        assert result["faces_written"] == 0
        test_db.refresh(face)
        assert face.reid_embedding is None

    def test_degenerate_bbox_skipped(self, test_db, enable_reid):
        """Zero-area face bbox → derive returns the 1x1 sentinel → skip, NULL."""
        event = _seed_event(test_db)
        _, face = _seed_image_with_face(test_db, event, bbox=[0.0, 0.0, 0.0, 0.0])
        embed = AsyncMock(return_value=[0.05] * 512)
        with patch.object(reid_backfill, "compute_reid_embedding", new=embed), \
             patch.object(reid_backfill.storage_service, "get_photo", return_value=_jpeg_bytes()):
            result = reid_backfill.backfill_reid_embeddings(event_id=str(event.id), db=test_db)
        assert result["faces_degenerate"] == 1
        assert result["faces_written"] == 0
        embed.assert_not_called()  # degenerate crop must never hit the sidecar
        test_db.refresh(face)
        assert face.reid_embedding is None

    def test_missing_original_tolerated(self, test_db, enable_reid):
        event = _seed_event(test_db)
        _, face = _seed_image_with_face(test_db, event)
        with patch.object(reid_backfill, "compute_reid_embedding", new=AsyncMock(return_value=[0.05] * 512)), \
             patch.object(reid_backfill.storage_service, "get_photo", side_effect=FileNotFoundError):
            result = reid_backfill.backfill_reid_embeddings(event_id=str(event.id), db=test_db)
        assert result["images_missing"] == 1
        assert result["faces_written"] == 0
        test_db.refresh(face)
        assert face.reid_embedding is None

    def test_event_scoping(self, test_db, enable_reid):
        """A backfill scoped to event A leaves event B's NULL faces alone."""
        event_a = _seed_event(test_db)
        event_b = _seed_event(test_db)
        _, face_a = _seed_image_with_face(test_db, event_a)
        _, face_b = _seed_image_with_face(test_db, event_b)
        with patch.object(reid_backfill, "compute_reid_embedding", new=AsyncMock(return_value=[0.05] * 512)), \
             patch.object(reid_backfill.storage_service, "get_photo", return_value=_jpeg_bytes()):
            result = reid_backfill.backfill_reid_embeddings(event_id=str(event_a.id), db=test_db)
        assert result["faces_written"] == 1
        test_db.refresh(face_a)
        test_db.refresh(face_b)
        assert face_a.reid_embedding is not None
        assert face_b.reid_embedding is None

    def test_max_images_cap_flags_remainder(self, test_db, enable_reid):
        event = _seed_event(test_db)
        _seed_image_with_face(test_db, event)
        _seed_image_with_face(test_db, event)
        with patch.object(reid_backfill, "compute_reid_embedding", new=AsyncMock(return_value=[0.05] * 512)), \
             patch.object(reid_backfill.storage_service, "get_photo", return_value=_jpeg_bytes()):
            result = reid_backfill.backfill_reid_embeddings(event_id=str(event.id), max_images=1, db=test_db)
        assert result["images_total"] == 2
        assert result["images_processed"] == 1
        assert result["images_remaining_capped"] is True

    def test_disabled_short_circuits(self, test_db):
        """Without enable_reid, conftest leaves both flags off → skipped, no work."""
        event = _seed_event(test_db)
        _, face = _seed_image_with_face(test_db, event)
        with patch.object(reid_backfill.storage_service, "get_photo") as get_photo:
            result = reid_backfill.backfill_reid_embeddings(event_id=str(event.id), db=test_db)
        assert result == {"skipped": True, "reason": "reid disabled"}
        get_photo.assert_not_called()

    def test_invalid_event_id(self, test_db, enable_reid):
        result = reid_backfill.backfill_reid_embeddings(event_id="not-a-uuid", db=test_db)
        assert result == {"error": "invalid event_id"}


# --------------------------------------------------------------------------- #
# Admin endpoint
# --------------------------------------------------------------------------- #

class TestBackfillEndpoint:

    def _user_and_token(self, db):
        user = User(email=f"u_{uuid.uuid4()}@example.com", password_hash=hash_password("pw"))
        db.add(user)
        db.commit()
        return user, create_access_token({"sub": str(user.id), "email": user.email})

    def test_enqueue_success(self, client, test_db):
        user, token = self._user_and_token(test_db)
        event = Event(owner_user_id=user.id, slug=f"ev-{uuid.uuid4()}", name="E",
                      allow_downloads=True, retention_days=90)
        test_db.add(event)
        test_db.commit()
        with patch("app.queue.enqueue_reid_backfill", return_value="reid_backfill:job") as fake:
            resp = client.post(f"/events/{event.id}/reid-backfill",
                               headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        assert resp.json()["job_id"] == "reid_backfill:job"
        fake.assert_called_once_with(str(event.id))

    def test_not_found(self, client, test_db):
        _, token = self._user_and_token(test_db)
        resp = client.post(f"/events/{uuid.uuid4()}/reid-backfill",
                           headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 404

    def test_unauthorized_non_owner(self, client, test_db):
        owner, _ = self._user_and_token(test_db)
        _, other_token = self._user_and_token(test_db)
        event = Event(owner_user_id=owner.id, slug=f"ev-{uuid.uuid4()}", name="E",
                      allow_downloads=True, retention_days=90)
        test_db.add(event)
        test_db.commit()
        resp = client.post(f"/events/{event.id}/reid-backfill",
                           headers={"Authorization": f"Bearer {other_token}"})
        assert resp.status_code == 403

    def test_invalid_id(self, client, test_db):
        _, token = self._user_and_token(test_db)
        resp = client.post("/events/not-a-uuid/reid-backfill",
                           headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 400

    def test_no_auth(self, client):
        resp = client.post(f"/events/{uuid.uuid4()}/reid-backfill")
        assert resp.status_code == 401
