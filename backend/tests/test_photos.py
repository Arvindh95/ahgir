"""
Unit tests for photo upload service
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
import uuid
from io import BytesIO
from PIL import Image as PILImage
from unittest.mock import Mock

from app.main import app
from app.database import get_db
from app.models import User, Event, Image
from app.auth import hash_password, create_access_token
from app.storage import storage_service

client = TestClient(app)


def create_test_image(width: int = 100, height: int = 100, color: tuple = (255, 0, 0)) -> bytes:
    """Create a test JPEG image"""
    img = PILImage.new('RGB', (width, height), color=color)
    buffer = BytesIO()
    img.save(buffer, format='JPEG')
    buffer.seek(0)
    return buffer.getvalue()


def create_test_png(width: int = 100, height: int = 100) -> bytes:
    """Create a test PNG image"""
    img = PILImage.new('RGB', (width, height), color=(0, 255, 0))
    buffer = BytesIO()
    img.save(buffer, format='PNG')
    buffer.seek(0)
    return buffer.getvalue()


@pytest.fixture
def setup_admin_and_event(db_session):
    """Create admin user and event for testing"""
    # Mock MinIO client
    mock_client = Mock()
    mock_client.put_object.return_value = None
    mock_client.presigned_get_object.return_value = "https://minio/test-url"
    storage_service._client = mock_client
    
    # Override get_db
    def override_get_db():
        try:
            yield db_session
        finally:
            pass
    
    app.dependency_overrides[get_db] = override_get_db
    
    # Create admin user
    admin = User(
        email=f"admin_{uuid.uuid4()}@example.com",
        password_hash=hash_password("password")
    )
    db_session.add(admin)
    db_session.commit()
    db_session.refresh(admin)
    
    # Create event
    event = Event(
        owner_user_id=admin.id,
        slug=f"test-event-{uuid.uuid4().hex[:8]}",
        name="Test Event",
        allow_downloads=True,
        retention_days=90
    )
    db_session.add(event)
    db_session.commit()
    db_session.refresh(event)
    
    # Generate JWT token
    token = create_access_token(
        data={"sub": str(admin.id), "email": admin.email}
    )
    
    yield {
        "admin": admin,
        "event": event,
        "token": token,
        "db": db_session
    }
    
    # Cleanup
    app.dependency_overrides.clear()
    storage_service._client = None


def test_successful_upload(setup_admin_and_event):
    """Test successful photo upload"""
    data = setup_admin_and_event
    event = data["event"]
    token = data["token"]
    
    # Create test image
    image_data = create_test_image()
    
    # Upload photo
    files = [
        ("files", ("test_image.jpg", BytesIO(image_data), "image/jpeg"))
    ]
    
    response = client.post(
        f"/events/{event.id}/photos",
        headers={"Authorization": f"Bearer {token}"},
        files=files
    )
    
    assert response.status_code == 201
    data_response = response.json()
    
    assert len(data_response["uploaded"]) == 1
    assert len(data_response["failed"]) == 0

    uploaded = data_response["uploaded"][0]
    assert uploaded["filename"] == "test_image.jpg"
    assert uploaded["status"] == "pending"
    assert uploaded["size_bytes"] > 0
    assert "image_id" in uploaded


def test_upload_multiple_photos(setup_admin_and_event):
    """Test uploading multiple photos at once"""
    data = setup_admin_and_event
    event = data["event"]
    token = data["token"]
    
    # Create multiple test images with different colors
    image1 = create_test_image(color=(255, 0, 0))
    image2 = create_test_image(color=(0, 255, 0))
    image3 = create_test_image(color=(0, 0, 255))
    
    # Upload photos
    files = [
        ("files", ("image1.jpg", BytesIO(image1), "image/jpeg")),
        ("files", ("image2.jpg", BytesIO(image2), "image/jpeg")),
        ("files", ("image3.jpg", BytesIO(image3), "image/jpeg"))
    ]
    
    response = client.post(
        f"/events/{event.id}/photos",
        headers={"Authorization": f"Bearer {token}"},
        files=files
    )
    
    assert response.status_code == 201
    data_response = response.json()
    
    assert len(data_response["uploaded"]) == 3
    assert len(data_response["failed"]) == 0


def test_duplicate_rejection(setup_admin_and_event):
    """Test duplicate photo rejection — same filename within an event."""
    data = setup_admin_and_event
    event = data["event"]
    token = data["token"]

    image_data = create_test_image()

    # Upload first time
    files = [
        ("files", ("test_image.jpg", BytesIO(image_data), "image/jpeg"))
    ]

    response = client.post(
        f"/events/{event.id}/photos",
        headers={"Authorization": f"Bearer {token}"},
        files=files
    )

    assert response.status_code == 201
    assert len(response.json()["uploaded"]) == 1

    # Upload again with the same filename — current dedup is filename-scoped
    # per event (see unique_filename_per_event index).
    files = [
        ("files", ("test_image.jpg", BytesIO(image_data), "image/jpeg"))
    ]

    response = client.post(
        f"/events/{event.id}/photos",
        headers={"Authorization": f"Bearer {token}"},
        files=files
    )

    assert response.status_code == 201
    data_response = response.json()

    assert len(data_response["uploaded"]) == 0
    assert len(data_response["failed"]) == 1
    failure = data_response["failed"][0]
    assert failure["category"] == "duplicate"
    assert "already exists" in failure["reason"].lower()


def test_invalid_format_rejection(setup_admin_and_event):
    """Test invalid image format rejection"""
    data = setup_admin_and_event
    event = data["event"]
    token = data["token"]
    
    # Create invalid file (text file)
    invalid_data = b"This is not an image"
    
    files = [
        ("files", ("test.txt", BytesIO(invalid_data), "text/plain"))
    ]
    
    response = client.post(
        f"/events/{event.id}/photos",
        headers={"Authorization": f"Bearer {token}"},
        files=files
    )
    
    assert response.status_code == 201
    data_response = response.json()

    assert len(data_response["uploaded"]) == 0
    assert len(data_response["failed"]) == 1
    failure = data_response["failed"][0]
    assert failure["category"] == "invalid_format"
    assert "invalid image format" in failure["reason"].lower()


def test_png_format_accepted(setup_admin_and_event):
    """Test that PNG format is accepted"""
    data = setup_admin_and_event
    event = data["event"]
    token = data["token"]
    
    # Create PNG image
    image_data = create_test_png()
    
    files = [
        ("files", ("test_image.png", BytesIO(image_data), "image/png"))
    ]
    
    response = client.post(
        f"/events/{event.id}/photos",
        headers={"Authorization": f"Bearer {token}"},
        files=files
    )
    
    assert response.status_code == 201
    data_response = response.json()
    
    assert len(data_response["uploaded"]) == 1
    assert len(data_response["failed"]) == 0


def test_unauthorized_upload_attempt(setup_admin_and_event):
    """Test unauthorized upload attempt"""
    data = setup_admin_and_event
    event = data["event"]
    db = data["db"]
    
    # Create another admin user
    other_admin = User(
        email=f"other_admin_{uuid.uuid4()}@example.com",
        password_hash=hash_password("password")
    )
    db.add(other_admin)
    db.commit()
    db.refresh(other_admin)
    
    # Generate token for other admin
    other_token = create_access_token(
        data={"sub": str(other_admin.id), "email": other_admin.email}
    )
    
    # Try to upload to first admin's event
    image_data = create_test_image()
    files = [
        ("files", ("test_image.jpg", BytesIO(image_data), "image/jpeg"))
    ]
    
    response = client.post(
        f"/events/{event.id}/photos",
        headers={"Authorization": f"Bearer {other_token}"},
        files=files
    )
    
    assert response.status_code == 403
    assert "permission" in response.json()["detail"].lower()


def test_upload_without_authentication(setup_admin_and_event):
    """Test upload without authentication token"""
    data = setup_admin_and_event
    event = data["event"]
    
    image_data = create_test_image()
    files = [
        ("files", ("test_image.jpg", BytesIO(image_data), "image/jpeg"))
    ]
    
    response = client.post(
        f"/events/{event.id}/photos",
        files=files
    )
    
    assert response.status_code == 403


def test_upload_to_nonexistent_event(setup_admin_and_event):
    """Test upload to non-existent event"""
    data = setup_admin_and_event
    token = data["token"]
    
    fake_event_id = uuid.uuid4()
    
    image_data = create_test_image()
    files = [
        ("files", ("test_image.jpg", BytesIO(image_data), "image/jpeg"))
    ]
    
    response = client.post(
        f"/events/{fake_event_id}/photos",
        headers={"Authorization": f"Bearer {token}"},
        files=files
    )
    
    assert response.status_code == 404


def test_list_photos(setup_admin_and_event):
    """Test listing photos for an event"""
    data = setup_admin_and_event
    event = data["event"]
    token = data["token"]
    db = data["db"]
    
    # Upload some photos first
    for i in range(3):
        image_data = create_test_image(color=(i * 50, i * 50, i * 50))
        files = [
            ("files", (f"test_image_{i}.jpg", BytesIO(image_data), "image/jpeg"))
        ]
        
        response = client.post(
            f"/events/{event.id}/photos",
            headers={"Authorization": f"Bearer {token}"},
            files=files
        )
        assert response.status_code == 201
    
    # List photos
    response = client.get(
        f"/events/{event.id}/photos",
        headers={"Authorization": f"Bearer {token}"}
    )
    
    assert response.status_code == 200
    data_response = response.json()
    
    assert data_response["total"] == 3
    assert len(data_response["photos"]) == 3
    assert data_response["page"] == 1
    assert data_response["limit"] == 50
    
    # Check photo structure
    photo = data_response["photos"][0]
    assert "image_id" in photo
    assert "filename" in photo
    assert "status" in photo
    assert "face_count" in photo
    assert "thumbnail_url" in photo
    assert "uploaded_at" in photo


def test_list_photos_with_pagination(setup_admin_and_event):
    """Test photo listing with pagination"""
    data = setup_admin_and_event
    event = data["event"]
    token = data["token"]
    
    # Upload 5 photos
    for i in range(5):
        image_data = create_test_image(color=(i * 50, i * 50, i * 50))
        files = [
            ("files", (f"test_image_{i}.jpg", BytesIO(image_data), "image/jpeg"))
        ]
        
        response = client.post(
            f"/events/{event.id}/photos",
            headers={"Authorization": f"Bearer {token}"},
            files=files
        )
        assert response.status_code == 201
    
    # Get first page with limit 2
    response = client.get(
        f"/events/{event.id}/photos?page=1&limit=2",
        headers={"Authorization": f"Bearer {token}"}
    )
    
    assert response.status_code == 200
    data_response = response.json()
    
    assert data_response["total"] == 5
    assert len(data_response["photos"]) == 2
    assert data_response["page"] == 1
    assert data_response["limit"] == 2
    
    # Get second page
    response = client.get(
        f"/events/{event.id}/photos?page=2&limit=2",
        headers={"Authorization": f"Bearer {token}"}
    )
    
    assert response.status_code == 200
    data_response = response.json()
    
    assert data_response["total"] == 5
    assert len(data_response["photos"]) == 2
    assert data_response["page"] == 2


def test_list_photos_with_status_filter(setup_admin_and_event):
    """Test photo listing with status filter"""
    data = setup_admin_and_event
    event = data["event"]
    token = data["token"]
    db = data["db"]
    
    # Upload photos
    for i in range(3):
        image_data = create_test_image(color=(i * 50, i * 50, i * 50))
        files = [
            ("files", (f"test_image_{i}.jpg", BytesIO(image_data), "image/jpeg"))
        ]
        
        response = client.post(
            f"/events/{event.id}/photos",
            headers={"Authorization": f"Bearer {token}"},
            files=files
        )
        assert response.status_code == 201
    
    # Update one image to indexed status
    image = db.query(Image).filter(Image.event_id == event.id).first()
    image.status = 'indexed'
    db.commit()
    
    # Filter by pending status
    response = client.get(
        f"/events/{event.id}/photos?status_filter=pending",
        headers={"Authorization": f"Bearer {token}"}
    )
    
    assert response.status_code == 200
    data_response = response.json()
    assert data_response["total"] == 2
    
    # Filter by indexed status
    response = client.get(
        f"/events/{event.id}/photos?status_filter=indexed",
        headers={"Authorization": f"Bearer {token}"}
    )
    
    assert response.status_code == 200
    data_response = response.json()
    assert data_response["total"] == 1


def test_delete_photo(setup_admin_and_event):
    """Test deleting a photo"""
    data = setup_admin_and_event
    event = data["event"]
    token = data["token"]
    db = data["db"]
    
    # Upload a photo
    image_data = create_test_image()
    files = [
        ("files", ("test_image.jpg", BytesIO(image_data), "image/jpeg"))
    ]
    
    response = client.post(
        f"/events/{event.id}/photos",
        headers={"Authorization": f"Bearer {token}"},
        files=files
    )
    
    assert response.status_code == 201
    image_id = response.json()["uploaded"][0]["image_id"]
    
    # Delete the photo
    response = client.delete(
        f"/events/{event.id}/photos/{image_id}",
        headers={"Authorization": f"Bearer {token}"}
    )
    
    assert response.status_code == 200
    data_response = response.json()
    assert data_response["message"] == "Photo deleted"
    assert data_response["image_id"] == image_id
    
    # Verify photo is deleted from database
    image = db.query(Image).filter(Image.id == uuid.UUID(image_id)).first()
    assert image is None


def test_delete_photo_unauthorized(setup_admin_and_event):
    """Test deleting a photo without authorization"""
    data = setup_admin_and_event
    event = data["event"]
    token = data["token"]
    db = data["db"]
    
    # Upload a photo
    image_data = create_test_image()
    files = [
        ("files", ("test_image.jpg", BytesIO(image_data), "image/jpeg"))
    ]
    
    response = client.post(
        f"/events/{event.id}/photos",
        headers={"Authorization": f"Bearer {token}"},
        files=files
    )
    
    assert response.status_code == 201
    image_id = response.json()["uploaded"][0]["image_id"]
    
    # Create another admin
    other_admin = User(
        email=f"other_admin_{uuid.uuid4()}@example.com",
        password_hash=hash_password("password")
    )
    db.add(other_admin)
    db.commit()
    db.refresh(other_admin)
    
    other_token = create_access_token(
        data={"sub": str(other_admin.id), "email": other_admin.email}
    )
    
    # Try to delete with other admin's token
    response = client.delete(
        f"/events/{event.id}/photos/{image_id}",
        headers={"Authorization": f"Bearer {other_token}"}
    )
    
    assert response.status_code == 403


def test_delete_nonexistent_photo(setup_admin_and_event):
    """Test deleting a non-existent photo"""
    data = setup_admin_and_event
    event = data["event"]
    token = data["token"]
    
    fake_image_id = uuid.uuid4()
    
    response = client.delete(
        f"/events/{event.id}/photos/{fake_image_id}",
        headers={"Authorization": f"Bearer {token}"}
    )
    
    assert response.status_code == 404
