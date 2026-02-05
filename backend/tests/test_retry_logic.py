"""Unit tests for retry logic with exponential backoff."""

import pytest
import time
from unittest.mock import Mock, patch, call
from minio.error import S3Error

from app.retry_utils import exponential_backoff, retry_on_failure
from app.exceptions import StorageError


class TestExponentialBackoffDecorator:
    """Test exponential backoff decorator."""
    
    def test_successful_execution_no_retry(self):
        """Test that successful execution doesn't trigger retries."""
        call_count = 0
        
        @exponential_backoff(max_retries=3, base_delay=0.1)
        def successful_function():
            nonlocal call_count
            call_count += 1
            return "success"
        
        result = successful_function()
        
        assert result == "success"
        assert call_count == 1
    
    def test_retry_on_failure(self):
        """Test that function retries on failure."""
        call_count = 0
        
        @exponential_backoff(max_retries=3, base_delay=0.1)
        def failing_function():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ValueError("Temporary failure")
            return "success"
        
        result = failing_function()
        
        assert result == "success"
        assert call_count == 3
    
    def test_max_retries_exceeded(self):
        """Test that exception is raised after max retries."""
        call_count = 0
        
        @exponential_backoff(max_retries=2, base_delay=0.1)
        def always_failing_function():
            nonlocal call_count
            call_count += 1
            raise ValueError("Permanent failure")
        
        with pytest.raises(ValueError, match="Permanent failure"):
            always_failing_function()
        
        assert call_count == 3  # Initial attempt + 2 retries
    
    def test_exponential_delay_calculation(self):
        """Test that delays follow exponential backoff pattern."""
        call_count = 0
        delays = []
        
        @exponential_backoff(max_retries=3, base_delay=1.0, exponential_base=2.0)
        def failing_function():
            nonlocal call_count
            call_count += 1
            raise ValueError("Test failure")
        
        with patch('time.sleep') as mock_sleep:
            with pytest.raises(ValueError):
                failing_function()
            
            # Verify exponential backoff: 1.0, 2.0, 4.0
            calls = mock_sleep.call_args_list
            assert len(calls) == 3
            assert calls[0][0][0] == 1.0  # First retry: base_delay * 2^0
            assert calls[1][0][0] == 2.0  # Second retry: base_delay * 2^1
            assert calls[2][0][0] == 4.0  # Third retry: base_delay * 2^2
    
    def test_max_delay_cap(self):
        """Test that delay is capped at max_delay."""
        @exponential_backoff(max_retries=5, base_delay=10.0, max_delay=15.0, exponential_base=2.0)
        def failing_function():
            raise ValueError("Test failure")
        
        with patch('time.sleep') as mock_sleep:
            with pytest.raises(ValueError):
                failing_function()
            
            # Verify delays are capped at max_delay
            calls = mock_sleep.call_args_list
            for call_obj in calls:
                assert call_obj[0][0] <= 15.0
    
    def test_specific_exception_types(self):
        """Test that only specified exception types trigger retries."""
        call_count = 0
        
        @exponential_backoff(max_retries=3, base_delay=0.1, exceptions=(ValueError,))
        def function_with_different_exceptions():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ValueError("Retryable error")
            elif call_count == 2:
                raise TypeError("Non-retryable error")
        
        # TypeError should not be retried
        with pytest.raises(TypeError, match="Non-retryable error"):
            function_with_different_exceptions()
        
        assert call_count == 2  # Initial + 1 retry for ValueError, then TypeError
    
    @patch('app.retry_utils.logger')
    def test_retry_logging(self, mock_logger):
        """Test that retries are logged properly."""
        call_count = 0
        
        @exponential_backoff(max_retries=2, base_delay=0.1)
        def failing_function():
            nonlocal call_count
            call_count += 1
            raise ValueError("Test failure")
        
        with pytest.raises(ValueError):
            failing_function()
        
        # Verify warning logs for retries
        assert mock_logger.warning.call_count == 2
        
        # Verify error log for final failure
        assert mock_logger.error.call_count == 1


class TestRetryOnFailureFunction:
    """Test retry_on_failure function."""
    
    def test_successful_execution(self):
        """Test successful execution without retries."""
        call_count = 0
        
        def successful_function():
            nonlocal call_count
            call_count += 1
            return "success"
        
        result = retry_on_failure(successful_function, max_retries=3, base_delay=0.1)
        
        assert result == "success"
        assert call_count == 1
    
    def test_retry_with_lambda(self):
        """Test retry with lambda function."""
        call_count = 0
        
        def increment_and_fail():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ValueError("Temporary failure")
            return call_count
        
        result = retry_on_failure(
            lambda: increment_and_fail(),
            max_retries=3,
            base_delay=0.1
        )
        
        assert result == 3
        assert call_count == 3
    
    def test_on_retry_callback(self):
        """Test that on_retry callback is called on each retry."""
        retry_attempts = []
        
        def on_retry_callback(exception, attempt):
            retry_attempts.append((str(exception), attempt))
        
        call_count = 0
        
        def failing_function():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ValueError(f"Failure {call_count}")
            return "success"
        
        result = retry_on_failure(
            failing_function,
            max_retries=3,
            base_delay=0.1,
            on_retry=on_retry_callback
        )
        
        assert result == "success"
        assert len(retry_attempts) == 2
        assert retry_attempts[0][1] == 1  # First retry
        assert retry_attempts[1][1] == 2  # Second retry


class TestStorageRetryIntegration:
    """Test retry logic integration with storage operations."""
    
    @patch('app.storage.StorageService.client')
    def test_upload_photo_retries_on_s3_error(self, mock_client):
        """Test that upload_photo retries on S3Error."""
        from app.storage import StorageService
        import uuid
        
        storage = StorageService()
        storage._client = mock_client
        
        # Mock S3Error on first two attempts, success on third
        call_count = 0
        
        def put_object_side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise S3Error(
                    code="ServiceUnavailable",
                    message="Service temporarily unavailable",
                    resource="/bucket/key",
                    request_id="123",
                    host_id="456",
                    response=Mock()
                )
            return None
        
        mock_client.put_object.side_effect = put_object_side_effect
        
        # Should succeed after retries
        event_id = uuid.uuid4()
        image_id = uuid.uuid4()
        result = storage.upload_photo(event_id, image_id, b"test data")
        
        assert call_count == 3
        assert result == f"events/{event_id}/original/{image_id}.jpg"
    
    @patch('app.storage.StorageService.client')
    def test_get_photo_retries_on_s3_error(self, mock_client):
        """Test that get_photo retries on S3Error."""
        from app.storage import StorageService
        import uuid
        
        storage = StorageService()
        storage._client = mock_client
        
        # Mock S3Error on first attempt, success on second
        call_count = 0
        
        def get_object_side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise S3Error(
                    code="ServiceUnavailable",
                    message="Service temporarily unavailable",
                    resource="/bucket/key",
                    request_id="123",
                    host_id="456",
                    response=Mock()
                )
            
            # Return mock response
            mock_response = Mock()
            mock_response.read.return_value = b"photo data"
            mock_response.close = Mock()
            mock_response.release_conn = Mock()
            return mock_response
        
        mock_client.get_object.side_effect = get_object_side_effect
        
        # Should succeed after retry
        event_id = uuid.uuid4()
        image_id = uuid.uuid4()
        result = storage.get_photo(event_id, image_id)
        
        assert call_count == 2
        assert result == b"photo data"
    
    @patch('app.storage.StorageService.client')
    def test_upload_photo_fails_after_max_retries(self, mock_client):
        """Test that upload_photo raises StorageError after max retries."""
        from app.storage import StorageService
        import uuid
        
        storage = StorageService()
        storage._client = mock_client
        
        # Always fail
        mock_client.put_object.side_effect = S3Error(
            code="ServiceUnavailable",
            message="Service unavailable",
            resource="/bucket/key",
            request_id="123",
            host_id="456",
            response=Mock()
        )
        
        event_id = uuid.uuid4()
        image_id = uuid.uuid4()
        
        with pytest.raises(StorageError):
            storage.upload_photo(event_id, image_id, b"test data")
        
        # Should have tried 4 times (initial + 3 retries)
        assert mock_client.put_object.call_count == 4


class TestFaceDetectionRetryIntegration:
    """Test retry logic integration with face detection."""

    @patch('app.workers.face_indexer.face_detector.detect_faces')
    @patch('app.workers.face_indexer.storage_service.get_photo')
    def test_face_detection_retries_on_failure(self, mock_get_photo, mock_detect_faces, test_db):
        """Test that face detection retries on failure."""
        from app.workers.face_indexer import index_photo
        from app.models import Image, Event, User
        import uuid

        # Create test user and event using the test fixture db
        user = User(email=f"test_{uuid.uuid4()}@example.com", password_hash="hash")
        test_db.add(user)
        test_db.commit()

        event = Event(
            owner_user_id=user.id,
            slug=f"test-event-{uuid.uuid4()}",
            name="Test Event"
        )
        test_db.add(event)
        test_db.commit()

        # Create test image
        image = Image(
            event_id=event.id,
            filename="test.jpg",
            file_hash=f"hash_{uuid.uuid4()}",
            size_bytes=1000,
            status="pending"
        )
        test_db.add(image)
        test_db.commit()

        # Mock storage to return photo data
        mock_get_photo.return_value = b"fake photo data"

        # Mock face detection to fail twice, then succeed
        call_count = 0

        def detect_faces_side_effect(photo_data):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise Exception("Face detection failed")
            return []  # No faces detected

        mock_detect_faces.side_effect = detect_faces_side_effect

        # Should succeed after retries
        result = index_photo(str(image.id), db_session=test_db)

        assert call_count == 3
        assert result["status"] == "no_faces"
        # No cleanup needed - test_db fixture handles rollback
