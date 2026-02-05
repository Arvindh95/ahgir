"""Property-based tests for storage service."""

import pytest
from hypothesis import given, strategies as st, settings, HealthCheck
import uuid
from unittest.mock import Mock, patch

from app.storage import StorageService
from app.models import User, Event, Image


# Feature: picur, Property 5: Presigned URL Validation
@given(
    seed=st.integers(min_value=0, max_value=1000000)
)
@settings(
    max_examples=20,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture]
)
@pytest.mark.property_test
def test_presigned_url_validation(db_session, seed):
    """
    Property 5: Presigned URL Validation
    
    For any presigned URL generated for an image, when a Guest attempts to access it,
    the system SHALL verify that the image belongs to the Guest's current Event before
    serving the content.
    
    Validates: Requirements 7.3
    """
    # Create a test user (let DB generate ID)
    user = User(
        email=f"test_{seed}_{uuid.uuid4()}@example.com",
        password_hash="hashed_password"
    )
    db_session.add(user)
    db_session.flush()
    
    # Create two events (let DB generate IDs)
    event_a = Event(
        owner_user_id=user.id,
        slug=f"event-a-{seed}-{uuid.uuid4()}",
        name="Event A",
        allow_downloads=True,
        retention_days=90
    )
    event_b = Event(
        owner_user_id=user.id,
        slug=f"event-b-{seed}-{uuid.uuid4()}",
        name="Event B",
        allow_downloads=True,
        retention_days=90
    )
    db_session.add(event_a)
    db_session.add(event_b)
    db_session.flush()
    
    # Create an image that belongs to event_a (let DB generate ID)
    image = Image(
        event_id=event_a.id,
        filename="test.jpg",
        file_hash=f"abc123-{seed}",
        size_bytes=1024,
        status="indexed"
    )
    db_session.add(image)
    db_session.flush()
    
    # Create a storage service instance with mocked MinIO client
    storage = StorageService()
    mock_client = Mock()
    mock_client.presigned_get_object.return_value = f"https://minio/photos/events/{event_a.id}/original/{image.id}.jpg?signature=xyz"
    storage._client = mock_client
    
    # Test 1: Generating presigned URL with correct event should succeed
    try:
        url = storage.generate_presigned_url(
            event_id=event_a.id,
            image_id=image.id,
            photo_type="original",
            db=db_session,
            validate_event=True
        )
        assert url is not None
        assert isinstance(url, str)
        assert len(url) > 0
    except Exception as e:
        pytest.fail(f"Should succeed with correct event: {e}")
    
    # Test 2: Generating presigned URL with wrong event should fail
    with pytest.raises(ValueError) as exc_info:
        storage.generate_presigned_url(
            event_id=event_b.id,  # Wrong event
            image_id=image.id,
            photo_type="original",
            db=db_session,
            validate_event=True
        )
    
    assert "does not belong to event" in str(exc_info.value)
    
    # Test 3: Generating presigned URL for non-existent image should fail
    non_existent_image_id = uuid.uuid4()
    with pytest.raises(ValueError) as exc_info:
        storage.generate_presigned_url(
            event_id=event_a.id,
            image_id=non_existent_image_id,
            photo_type="original",
            db=db_session,
            validate_event=True
        )
    
    assert "not found" in str(exc_info.value)
