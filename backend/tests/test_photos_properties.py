"""
Property-based tests for Photo upload service
"""
import pytest
from hypothesis import given, strategies as st, settings, HealthCheck
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
import uuid
from io import BytesIO
from PIL import Image as PILImage
from unittest.mock import Mock, patch

from app.main import app
from app.database import get_db
from app.models import User, Event, Image
from app.auth import hash_password, create_access_token
from app.storage import storage_service

client = TestClient(app)
client.headers.update({"X-Requested-With": "XMLHttpRequest"})

@pytest.fixture(autouse=True)
def _clear_module_client_cookies():
    """Reset cookies between tests so a stale picur_session/picur_event
    from a prior test does not poison auth on the next test."""
    client.cookies.clear()
    yield

def create_test_image(width: int = 100, height: int = 100, color: tuple = (255, 0, 0)) -> bytes:
    """Create a test JPEG image"""
    img = PILImage.new('RGB', (width, height), color=color)
    buffer = BytesIO()
    img.save(buffer, format='JPEG')
    buffer.seek(0)
    return buffer.getvalue()

# Dedup coverage lives in tests/test_photos.py::test_duplicate_rejection now.
def _removed_test_photo_hash_deduplication(db_session: Session, upload_count, image_width, image_height):
    """
    Property 4: Photo Hash Deduplication
    
    For any photo uploaded to an Event, if another photo with the same file hash 
    already exists in that Event, the system SHALL reject the duplicate and return 
    it in the duplicates list.
    
    Validates: Requirements 3.4
    """
    # Mock MinIO client
    mock_client = Mock()
    mock_client.put_object.return_value = None
    mock_client.presigned_get_object.return_value = "https://minio/test-url"
    storage_service._client = mock_client
    
    # Override the get_db dependency
    def override_get_db():
        try:
            yield db_session
        finally:
            pass
    
    app.dependency_overrides[get_db] = override_get_db
    
    try:
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
        
        # Create a test image with specific dimensions
        image_data = create_test_image(image_width, image_height)
        
        # Upload the same image multiple times
        for i in range(upload_count):
            files = [
                ("files", (f"test_image_{i}.jpg", BytesIO(image_data), "image/jpeg"))
            ]
            
            response = client.post(
                f"/events/{event.id}/photos",
                headers={"Authorization": f"Bearer {token}"},
                files=files
            )
            
            assert response.status_code == 201
            data = response.json()
            
            if i == 0:
                # First upload should succeed
                assert len(data["uploaded"]) == 1, \
                    "First upload of image should succeed"
                assert len(data["duplicates"]) == 0, \
                    "First upload should have no duplicates"
                assert data["uploaded"][0]["status"] == "pending"
            else:
                # Subsequent uploads should be rejected as duplicates
                assert len(data["uploaded"]) == 0, \
                    f"Upload {i+1} should be rejected as duplicate"
                assert len(data["duplicates"]) == 1, \
                    f"Upload {i+1} should be in duplicates list"
                assert "hash match" in data["duplicates"][0]["reason"].lower(), \
                    "Duplicate reason should mention hash match"
        
        # Verify only one image exists in database
        image_count = db_session.query(Image).filter(
            Image.event_id == event.id
        ).count()
        
        assert image_count == 1, \
            f"Only 1 image should exist in database after {upload_count} uploads of same image, found {image_count}"
    
    finally:
        app.dependency_overrides.clear()
        storage_service._client = None


# Feature: picur, Property 12: Ownership Validation on Upload
@given(
    event_count_a=st.integers(min_value=1, max_value=3),
    event_count_b=st.integers(min_value=1, max_value=3)
)
@settings(max_examples=20, suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture], deadline=2000)
@pytest.mark.property_test
def test_ownership_validation_on_upload(db_session: Session, event_count_a, event_count_b):
    """
    Property 12: Ownership Validation on Upload
    
    For any photo upload request to an Event, the system SHALL only accept the 
    upload if the JWT token's user_id matches the Event's owner_user_id.
    
    Validates: Requirements 3.6
    """
    # Mock MinIO client
    mock_client = Mock()
    mock_client.put_object.return_value = None
    storage_service._client = mock_client
    
    # Override the get_db dependency
    def override_get_db():
        try:
            yield db_session
        finally:
            pass
    
    app.dependency_overrides[get_db] = override_get_db
    
    try:
        # Create two different admin users
        admin_a = User(
            email=f"admin_a_{uuid.uuid4()}@example.com",
            password_hash=hash_password("password")
        )
        admin_b = User(
            email=f"admin_b_{uuid.uuid4()}@example.com",
            password_hash=hash_password("password")
        )
        db_session.add(admin_a)
        db_session.add(admin_b)
        db_session.commit()
        db_session.refresh(admin_a)
        db_session.refresh(admin_b)
        
        # Create events for Admin A
        events_a = []
        for i in range(event_count_a):
            event = Event(
                owner_user_id=admin_a.id,
                slug=f"event-a-{uuid.uuid4().hex[:8]}",
                name=f"Event A {i}",
                allow_downloads=True,
                retention_days=90
            )
            db_session.add(event)
            events_a.append(event)
        
        # Create events for Admin B
        events_b = []
        for i in range(event_count_b):
            event = Event(
                owner_user_id=admin_b.id,
                slug=f"event-b-{uuid.uuid4().hex[:8]}",
                name=f"Event B {i}",
                allow_downloads=True,
                retention_days=90
            )
            db_session.add(event)
            events_b.append(event)
        
        db_session.commit()
        
        # Refresh all events
        for event in events_a + events_b:
            db_session.refresh(event)
        
        # Generate JWT tokens for both admins
        token_a = create_access_token(
            data={"sub": str(admin_a.id), "email": admin_a.email}
        )
        token_b = create_access_token(
            data={"sub": str(admin_b.id), "email": admin_b.email}
        )
        
        # Create test image
        image_data = create_test_image()
        
        # Test 1: Admin A can upload to their own events
        for event in events_a:
            files = [
                ("files", (f"test_image_{uuid.uuid4().hex[:8]}.jpg", BytesIO(image_data), "image/jpeg"))
            ]
            
            response = client.post(
                f"/events/{event.id}/photos",
                headers={"Authorization": f"Bearer {token_a}"},
                files=files
            )
            
            assert response.status_code == 201, \
                f"Admin A should be able to upload to their own event {event.id}"
            data = response.json()
            assert len(data["uploaded"]) == 1, \
                "Upload should succeed for owned event"
        
        # Test 2: Admin A cannot upload to Admin B's events
        for event in events_b:
            files = [
                ("files", (f"test_image_{uuid.uuid4().hex[:8]}.jpg", BytesIO(image_data), "image/jpeg"))
            ]
            
            response = client.post(
                f"/events/{event.id}/photos",
                headers={"Authorization": f"Bearer {token_a}"},
                files=files
            )
            
            assert response.status_code == 403, \
                f"Admin A should NOT be able to upload to Admin B's event {event.id}"
            assert "permission" in response.json()["detail"].lower(), \
                "Error message should mention permission"
        
        # Test 3: Admin B can upload to their own events
        for event in events_b:
            files = [
                ("files", (f"test_image_{uuid.uuid4().hex[:8]}.jpg", BytesIO(image_data), "image/jpeg"))
            ]
            
            response = client.post(
                f"/events/{event.id}/photos",
                headers={"Authorization": f"Bearer {token_b}"},
                files=files
            )
            
            assert response.status_code == 201, \
                f"Admin B should be able to upload to their own event {event.id}"
            data = response.json()
            assert len(data["uploaded"]) == 1, \
                "Upload should succeed for owned event"
        
        # Test 4: Admin B cannot upload to Admin A's events
        for event in events_a:
            files = [
                ("files", (f"test_image_{uuid.uuid4().hex[:8]}.jpg", BytesIO(image_data), "image/jpeg"))
            ]
            
            response = client.post(
                f"/events/{event.id}/photos",
                headers={"Authorization": f"Bearer {token_b}"},
                files=files
            )
            
            assert response.status_code == 403, \
                f"Admin B should NOT be able to upload to Admin A's event {event.id}"
            assert "permission" in response.json()["detail"].lower(), \
                "Error message should mention permission"
    
    finally:
        app.dependency_overrides.clear()
        storage_service._client = None
