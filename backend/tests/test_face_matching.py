"""
Unit tests for face matching service
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
import uuid
import base64
import numpy as np
from datetime import datetime, timedelta
from io import BytesIO
from PIL import Image as PILImage
from unittest.mock import patch, MagicMock, AsyncMock

from app.main import app
from app.database import get_db
from app.models import User, Event, Image, Face, GuestSession
from app.auth import hash_password, create_event_token
from app.rate_limiter import rate_limiter
from app.storage import storage_service

client = TestClient(app)
client.headers.update({"X-Requested-With": "XMLHttpRequest"})

@pytest.fixture(autouse=True)
def _clear_module_client_cookies():
    """Reset cookies between tests so a stale picur_session/picur_event
    from a prior test does not poison auth on the next test."""
    client.cookies.clear()
    yield


@pytest.fixture(autouse=True)
def _reset_scan_bucket():
    """conftest already lifts auth/passcode/share limits — also flush the scan
    bucket for these tests because /scan is the focal endpoint here.
    """
    rate_limiter.reset_limit("testclient", "scan")
    yield


def _compreface_subject_result(event_id, image_id, similarity: float = 0.95):
    """Build a CompreFace-shaped recognize() result containing one matching subject.

    The recognizer stores subjects as ``{event_id}/{image_id}`` and the scan
    handler filters by similarity >= ``settings.face_similarity_threshold``.
    """
    return [
        {
            "box": {"x_min": 10, "y_min": 10, "x_max": 60, "y_max": 60, "probability": 0.99},
            "subjects": [
                {"subject": f"{event_id}/{image_id}", "similarity": similarity}
            ],
        }
    ]


def create_dummy_image_bytes() -> bytes:
    """Create a simple dummy image for testing."""
    img = PILImage.new('RGB', (100, 100), color='white')
    buffer = BytesIO()
    img.save(buffer, format='JPEG')
    return buffer.getvalue()


def create_test_embedding() -> np.ndarray:
    """Create a normalized test embedding."""
    embedding = np.random.randn(512)
    return embedding / np.linalg.norm(embedding)


@pytest.fixture
def setup_event_with_faces(db_session: Session):
    """Setup an event with images and faces for testing.

    Each Face stores a ``compreface_subject_id`` of ``{event_id}/{image_id}``
    so a mocked CompreFace response matching that subject yields a real DB
    lookup and a populated FaceMatch.
    """
    admin = User(
        email=f"admin_{uuid.uuid4()}@example.com",
        password_hash=hash_password("password"),
    )
    db_session.add(admin)
    db_session.commit()
    db_session.refresh(admin)

    event = Event(
        owner_user_id=admin.id,
        slug=f"event-{uuid.uuid4().hex[:8]}",
        name="Test Event",
        allow_downloads=True,
        retention_days=90,
    )
    db_session.add(event)
    db_session.commit()
    db_session.refresh(event)

    images = []
    faces = []
    for i in range(3):
        image = Image(
            event_id=event.id,
            filename=f"image_{i}.jpg",
            file_hash=f"hash_{uuid.uuid4().hex}",
            size_bytes=1024,
            status="indexed",
            face_count=1,
        )
        db_session.add(image)
        images.append(image)

    db_session.commit()
    for image in images:
        db_session.refresh(image)

    for i, image in enumerate(images):
        # Bbox sized to a min_side of ~80 px (medium-tier under face_size_*_px).
        # Threshold buckets are flat at 0.90 today, but keeping the sizing
        # explicit means the test still exercises a defined tier rather than
        # accidentally landing in the small-face bucket if defaults are tuned.
        # The matching-engine behaviour under test is sort + dedupe, not
        # threshold tiering — the mocked similarities below are chosen to
        # comfortably clear the floor.
        face = Face(
            image_id=image.id,
            event_id=event.id,
            bbox=[10.0 + i * 10, 10.0 + i * 10, 90.0 + i * 10, 90.0 + i * 10],
            quality_score=0.9,
            embedding=[0.0] * 512,
            compreface_subject_id=f"{event.id}/{image.id}",
        )
        db_session.add(face)
        faces.append(face)

    db_session.commit()

    session_id = uuid.uuid4()
    event_token = create_event_token(event.id, session_id)

    guest_session = GuestSession(
        id=session_id,
        event_id=event.id,
        session_token=event_token,
        expires_at=datetime.utcnow() + timedelta(hours=1),
    )
    db_session.add(guest_session)
    db_session.commit()

    return {
        "admin": admin,
        "event": event,
        "images": images,
        "faces": faces,
        "event_token": event_token,
    }


def test_successful_face_scan_with_matches(db_session: Session, setup_event_with_faces):
    """End-to-end /scan with a mocked CompreFace recognizer."""
    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db

    try:
        data = setup_event_with_faces
        event = data["event"]
        event_token = data["event_token"]
        target_image_id = data["images"][0].id

        image_bytes = create_dummy_image_bytes()
        image_b64 = base64.b64encode(image_bytes).decode("utf-8")

        # Patch the recognizer used by /scan so we don't need a real CompreFace.
        mock_frame = AsyncMock(
            return_value=_compreface_subject_result(event.id, target_image_id, similarity=0.95)
        )
        with patch("app.routers.guest._recognize_single_frame", mock_frame):
            response = client.post(
                "/scan",
                json={"image": image_b64},
                headers={"Authorization": f"Bearer {event_token}"},
            )

        assert response.status_code == 200, response.text
        scan_result = response.json()

        assert "matches" in scan_result
        assert "scan_id" in scan_result
        assert "total_matches" in scan_result

        matches = scan_result["matches"]
        assert len(matches) == 1
        match = matches[0]
        assert match["image_id"] == str(target_image_id)
        assert match["similarity"] >= 0.9
        assert match["thumbnail_url"]
        assert match["original_url"]
        # Event was created with allow_downloads=True.
        assert match["download_url"]
        assert isinstance(match["face_bbox"], list) and len(match["face_bbox"]) == 4
    finally:
        app.dependency_overrides.clear()


def test_face_scan_returns_all_matches_sorted_by_similarity(db_session: Session, setup_event_with_faces):
    """A scan can match several event photos; return all above-threshold matches in confidence order."""
    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db

    try:
        data = setup_event_with_faces
        event = data["event"]
        event_token = data["event_token"]
        images = data["images"]

        image_bytes = create_dummy_image_bytes()
        image_b64 = base64.b64encode(image_bytes).decode("utf-8")

        recognition_result = [{
            "box": {"x_min": 10, "y_min": 10, "x_max": 60, "y_max": 60, "probability": 0.99},
            "subjects": [
                {"subject": f"{event.id}/{images[1].id}", "similarity": 0.91},
                {"subject": f"{event.id}/{images[0].id}", "similarity": 0.96},
                {"subject": f"{event.id}/{images[2].id}", "similarity": 0.93},
                {"subject": f"{event.id}/{images[1].id}", "similarity": 0.94},
            ],
        }]

        mock_frame = AsyncMock(return_value=recognition_result)
        with patch("app.routers.guest._recognize_single_frame", mock_frame):
            response = client.post(
                "/scan",
                json={"image": image_b64},
                headers={"Authorization": f"Bearer {event_token}"},
            )

        assert response.status_code == 200, response.text
        matches = response.json()["matches"]

        assert [m["image_id"] for m in matches] == [
            str(images[0].id),
            str(images[1].id),
            str(images[2].id),
        ]
        assert [m["similarity"] for m in matches] == [0.96, 0.94, 0.93]
    finally:
        app.dependency_overrides.clear()


def test_download_url_generation_based_on_allow_downloads(db_session: Session):
    """When allow_downloads is False, /scan responses must not expose download_url."""
    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db

    try:
        admin = User(
            email=f"admin_{uuid.uuid4()}@example.com",
            password_hash=hash_password("password"),
        )
        db_session.add(admin)
        db_session.commit()
        db_session.refresh(admin)

        event = Event(
            owner_user_id=admin.id,
            slug=f"event-{uuid.uuid4().hex[:8]}",
            name="Test Event",
            allow_downloads=False,  # downloads disabled
            retention_days=90,
        )
        db_session.add(event)
        db_session.commit()
        db_session.refresh(event)

        image = Image(
            event_id=event.id,
            filename="test.jpg",
            file_hash=f"hash_{uuid.uuid4().hex}",
            size_bytes=1024,
            status="indexed",
            face_count=1,
        )
        db_session.add(image)
        db_session.commit()
        db_session.refresh(image)

        face = Face(
            image_id=image.id,
            event_id=event.id,
            bbox=[10.0, 10.0, 50.0, 50.0],
            quality_score=0.9,
            embedding=[0.0] * 512,
            compreface_subject_id=f"{event.id}/{image.id}",
        )
        db_session.add(face)
        db_session.commit()

        session_id = uuid.uuid4()
        event_token = create_event_token(event.id, session_id)

        guest_session = GuestSession(
            id=session_id,
            event_id=event.id,
            session_token=event_token,
            expires_at=datetime.utcnow() + timedelta(hours=1),
        )
        db_session.add(guest_session)
        db_session.commit()

        image_bytes = create_dummy_image_bytes()
        image_b64 = base64.b64encode(image_bytes).decode("utf-8")

        mock_frame = AsyncMock(
            return_value=_compreface_subject_result(event.id, image.id, similarity=0.95)
        )
        with patch("app.routers.guest._recognize_single_frame", mock_frame):
            response = client.post(
                "/scan",
                json={"image": image_b64},
                headers={"Authorization": f"Bearer {event_token}"},
            )

        assert response.status_code == 200, response.text
        matches = response.json()["matches"]
        assert len(matches) == 1
        match = matches[0]
        # Downloads disabled → no download URL leaks to guests.
        assert match["download_url"] is None
        # Thumbnail + original (which is also the thumbnail URL when downloads
        # are off, per _guest_photo_urls) must still be present for viewing.
        assert match["thumbnail_url"]
        assert match["original_url"]
    finally:
        app.dependency_overrides.clear()


def test_face_scan_with_invalid_token(db_session: Session):
    """Test face scan with invalid or missing token"""
    # Override the get_db dependency
    def override_get_db():
        try:
            yield db_session
        finally:
            pass
    
    app.dependency_overrides[get_db] = override_get_db
    
    try:
        image_bytes = create_dummy_image_bytes()
        image_b64 = base64.b64encode(image_bytes).decode('utf-8')
        
        # Test without token. 401 (not 403) since the cookie-auth dependency
        # raises InvalidTokenError uniformly on missing creds.
        response = client.post(
            "/scan",
            json={"image": image_b64}
        )
        assert response.status_code == 401
        
        # Test with invalid token
        response = client.post(
            "/scan",
            json={"image": image_b64},
            headers={"Authorization": "Bearer invalid_token"}
        )
        assert response.status_code == 401  # Unauthorized
    
    finally:
        app.dependency_overrides.clear()


