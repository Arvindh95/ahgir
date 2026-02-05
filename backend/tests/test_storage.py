"""Unit tests for storage service."""

import pytest
import uuid
from unittest.mock import Mock, MagicMock, patch
from io import BytesIO
from minio.error import S3Error

from app.storage import StorageService
from app.models import User, Event, Image


@pytest.fixture
def storage():
    """Create a storage service instance with mocked MinIO client."""
    service = StorageService()
    service._client = Mock()
    return service


def test_upload_photo_success(storage):
    """Test successful photo upload."""
    event_id = uuid.uuid4()
    image_id = uuid.uuid4()
    photo_data = b"fake_image_data"
    
    # Mock successful upload
    storage._client.put_object.return_value = None
    
    # Upload photo
    result = storage.upload_photo(event_id, image_id, photo_data, "original")
    
    # Verify
    expected_path = f"events/{event_id}/original/{image_id}.jpg"
    assert result == expected_path
    storage._client.put_object.assert_called_once()
    call_args = storage._client.put_object.call_args
    assert call_args[0][0] == "photos"  # bucket
    assert call_args[0][1] == expected_path  # object path
    assert call_args[1]["length"] == len(photo_data)
    assert call_args[1]["content_type"] == "image/jpeg"


def test_upload_photo_thumbnail(storage):
    """Test thumbnail upload."""
    event_id = uuid.uuid4()
    image_id = uuid.uuid4()
    photo_data = b"fake_thumbnail_data"
    
    storage._client.put_object.return_value = None
    
    result = storage.upload_photo(event_id, image_id, photo_data, "thumb")
    
    expected_path = f"events/{event_id}/thumb/{image_id}.jpg"
    assert result == expected_path


def test_upload_photo_failure(storage):
    """Test photo upload failure."""
    event_id = uuid.uuid4()
    image_id = uuid.uuid4()
    photo_data = b"fake_image_data"
    
    # Mock S3 error
    storage._client.put_object.side_effect = S3Error(
        "PutObject",
        "Upload failed",
        "resource",
        "request_id",
        "host_id",
        Mock()
    )
    
    # Verify exception is raised
    with pytest.raises(Exception) as exc_info:
        storage.upload_photo(event_id, image_id, photo_data)
    
    assert "Failed to upload photo" in str(exc_info.value)


def test_get_photo_success(storage):
    """Test successful photo retrieval."""
    event_id = uuid.uuid4()
    image_id = uuid.uuid4()
    expected_data = b"fake_image_data"
    
    # Mock successful retrieval
    mock_response = Mock()
    mock_response.read.return_value = expected_data
    storage._client.get_object.return_value = mock_response
    
    # Get photo
    result = storage.get_photo(event_id, image_id, "original")
    
    # Verify
    assert result == expected_data
    expected_path = f"events/{event_id}/original/{image_id}.jpg"
    storage._client.get_object.assert_called_once_with("photos", expected_path)
    mock_response.close.assert_called_once()
    mock_response.release_conn.assert_called_once()


def test_get_photo_not_found(storage):
    """Test photo retrieval when file doesn't exist."""
    event_id = uuid.uuid4()
    image_id = uuid.uuid4()
    
    # Mock NoSuchKey error
    mock_response = Mock()
    mock_response.status = 404
    # S3Error signature: (code, message, resource, request_id, host_id, response)
    error = S3Error(
        "NoSuchKey",  # code
        "GetObject",  # message
        "resource",
        "request_id",
        "host_id",
        mock_response
    )
    storage._client.get_object.side_effect = error
    
    # Verify FileNotFoundError is raised
    with pytest.raises(FileNotFoundError) as exc_info:
        storage.get_photo(event_id, image_id)
    
    assert "Photo not found" in str(exc_info.value)


def test_get_photo_other_error(storage):
    """Test photo retrieval with other S3 errors."""
    event_id = uuid.uuid4()
    image_id = uuid.uuid4()
    
    # Mock other S3 error
    storage._client.get_object.side_effect = S3Error(
        "GetObject",
        "Server error",
        "resource",
        "request_id",
        "host_id",
        Mock()
    )
    
    # Verify generic exception is raised
    with pytest.raises(Exception) as exc_info:
        storage.get_photo(event_id, image_id)
    
    assert "Failed to retrieve photo" in str(exc_info.value)


def test_delete_photo_single_type(storage):
    """Test deleting a single photo type."""
    event_id = uuid.uuid4()
    image_id = uuid.uuid4()
    
    storage._client.remove_object.return_value = None
    
    # Delete original
    storage.delete_photo(event_id, image_id, "original")
    
    expected_path = f"events/{event_id}/original/{image_id}.jpg"
    storage._client.remove_object.assert_called_once_with("photos", expected_path)


def test_delete_photo_both_types(storage):
    """Test deleting both original and thumbnail."""
    event_id = uuid.uuid4()
    image_id = uuid.uuid4()
    
    storage._client.remove_object.return_value = None
    
    # Delete both (photo_type=None)
    storage.delete_photo(event_id, image_id, photo_type=None)
    
    # Verify both were deleted
    assert storage._client.remove_object.call_count == 2
    calls = storage._client.remove_object.call_args_list
    
    original_path = f"events/{event_id}/original/{image_id}.jpg"
    thumb_path = f"events/{event_id}/thumb/{image_id}.jpg"
    
    called_paths = [call[0][1] for call in calls]
    assert original_path in called_paths
    assert thumb_path in called_paths


def test_delete_photo_ignores_missing_files(storage):
    """Test that delete ignores errors when files don't exist."""
    event_id = uuid.uuid4()
    image_id = uuid.uuid4()
    
    # Mock S3 error for missing files
    storage._client.remove_object.side_effect = S3Error(
        "RemoveObject",
        "Not found",
        "resource",
        "request_id",
        "host_id",
        Mock()
    )
    
    # Should not raise exception when deleting both types
    storage.delete_photo(event_id, image_id, photo_type=None)
    
    # Verify both delete attempts were made
    assert storage._client.remove_object.call_count == 2


def test_generate_presigned_url_success(storage):
    """Test successful presigned URL generation."""
    event_id = uuid.uuid4()
    image_id = uuid.uuid4()
    expected_url = f"https://minio/photos/events/{event_id}/original/{image_id}.jpg?signature=xyz"
    
    storage._client.presigned_get_object.return_value = expected_url
    
    # Generate URL without validation
    result = storage.generate_presigned_url(
        event_id,
        image_id,
        "original",
        expiry_minutes=15,
        validate_event=False
    )
    
    assert result == expected_url
    expected_path = f"events/{event_id}/original/{image_id}.jpg"
    storage._client.presigned_get_object.assert_called_once()


def test_generate_presigned_url_with_validation(storage, db_session):
    """Test presigned URL generation with event validation."""
    event_id = uuid.uuid4()
    image_id = uuid.uuid4()
    expected_url = f"https://minio/photos/events/{event_id}/original/{image_id}.jpg?signature=xyz"
    
    # Create test data
    user = User(
        id=uuid.uuid4(),
        email="test@example.com",
        password_hash="hashed"
    )
    db_session.add(user)
    
    event = Event(
        id=event_id,
        owner_user_id=user.id,
        slug="test-event",
        name="Test Event",
        allow_downloads=True,
        retention_days=90
    )
    db_session.add(event)
    
    image = Image(
        id=image_id,
        event_id=event_id,
        filename="test.jpg",
        file_hash="abc123",
        size_bytes=1024,
        status="indexed"
    )
    db_session.add(image)
    db_session.commit()
    
    storage._client.presigned_get_object.return_value = expected_url
    
    # Generate URL with validation
    result = storage.generate_presigned_url(
        event_id,
        image_id,
        "original",
        db=db_session,
        validate_event=True
    )
    
    assert result == expected_url


def test_generate_presigned_url_validation_wrong_event(storage, db_session):
    """Test presigned URL validation fails for wrong event."""
    event_a_id = uuid.uuid4()
    event_b_id = uuid.uuid4()
    image_id = uuid.uuid4()
    
    # Create test data
    user = User(
        id=uuid.uuid4(),
        email="test@example.com",
        password_hash="hashed"
    )
    db_session.add(user)
    
    event_a = Event(
        id=event_a_id,
        owner_user_id=user.id,
        slug="event-a",
        name="Event A",
        allow_downloads=True,
        retention_days=90
    )
    event_b = Event(
        id=event_b_id,
        owner_user_id=user.id,
        slug="event-b",
        name="Event B",
        allow_downloads=True,
        retention_days=90
    )
    db_session.add(event_a)
    db_session.add(event_b)
    
    # Image belongs to event_a
    image = Image(
        id=image_id,
        event_id=event_a_id,
        filename="test.jpg",
        file_hash="abc123",
        size_bytes=1024,
        status="indexed"
    )
    db_session.add(image)
    db_session.commit()
    
    # Try to generate URL for event_b (wrong event)
    with pytest.raises(ValueError) as exc_info:
        storage.generate_presigned_url(
            event_b_id,  # Wrong event
            image_id,
            "original",
            db=db_session,
            validate_event=True
        )
    
    assert "does not belong to event" in str(exc_info.value)


def test_generate_presigned_url_validation_image_not_found(storage, db_session):
    """Test presigned URL validation fails for non-existent image."""
    event_id = uuid.uuid4()
    image_id = uuid.uuid4()
    
    # Try to generate URL for non-existent image
    with pytest.raises(ValueError) as exc_info:
        storage.generate_presigned_url(
            event_id,
            image_id,
            "original",
            db=db_session,
            validate_event=True
        )
    
    assert "not found" in str(exc_info.value)


def test_generate_presigned_url_failure(storage):
    """Test presigned URL generation failure."""
    event_id = uuid.uuid4()
    image_id = uuid.uuid4()
    
    # Mock S3 error
    storage._client.presigned_get_object.side_effect = S3Error(
        "PresignedGetObject",
        "Failed",
        "resource",
        "request_id",
        "host_id",
        Mock()
    )
    
    with pytest.raises(Exception) as exc_info:
        storage.generate_presigned_url(
            event_id,
            image_id,
            validate_event=False
        )
    
    assert "Failed to generate presigned URL" in str(exc_info.value)
