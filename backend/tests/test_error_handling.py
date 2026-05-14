"""Unit tests for error handling and logging."""

import pytest
from fastapi import Request
from fastapi.testclient import TestClient
from unittest.mock import Mock, patch, MagicMock
from sqlalchemy.exc import SQLAlchemyError
from minio.error import S3Error

from app.main import app
from app.exceptions import (
    PicUrException, InvalidTokenError, TokenExpiredError, InvalidCredentialsError,
    InvalidPasscodeError, ForbiddenError, EventNotOwnedError, DownloadsDisabledError,
    InvalidImageFormatError, MissingRequiredFieldError, InvalidSlugError,
    DuplicateEmailError, RateLimitExceededError, EventNotFoundError,
    ImageNotFoundError, UserNotFoundError, FaceDetectionFailedError,
    StorageError, DatabaseError
)
from app.error_handler import (
    create_error_response, picur_exception_handler, validation_exception_handler,
    sqlalchemy_exception_handler, s3_exception_handler, generic_exception_handler
)


client = TestClient(app)
client.headers.update({"X-Requested-With": "XMLHttpRequest"})

@pytest.fixture(autouse=True)
def _clear_module_client_cookies():
    """Reset cookies between tests so a stale picur_session/picur_event
    from a prior test does not poison auth on the next test."""
    client.cookies.clear()
    yield


class TestErrorResponseFormat:
    """Test standardized error response format."""
    
    def test_create_error_response_basic(self):
        """Test basic error response creation."""
        response = create_error_response(
            code="TEST_ERROR",
            message="Test error message",
            status_code=400
        )
        
        assert response.status_code == 400
        data = response.body.decode()
        assert "TEST_ERROR" in data
        assert "Test error message" in data
    
    def test_create_error_response_with_details(self):
        """Test error response with additional details."""
        response = create_error_response(
            code="VALIDATION_ERROR",
            message="Validation failed",
            status_code=422,
            details={"field": "email", "reason": "invalid format"}
        )
        
        assert response.status_code == 422
        data = response.body.decode()
        assert "VALIDATION_ERROR" in data
        assert "email" in data
        assert "invalid format" in data
    
    def test_create_error_response_with_request_context(self):
        """Test error response includes request context in logs."""
        mock_request = Mock(spec=Request)
        mock_request.method = "POST"
        mock_request.url = "http://test.com/api/test"
        mock_request.client = Mock()
        mock_request.client.host = "127.0.0.1"
        
        response = create_error_response(
            code="SERVER_ERROR",
            message="Internal error",
            status_code=500,
            request=mock_request
        )
        
        assert response.status_code == 500


class TestCustomExceptions:
    """Test custom PicUr exceptions."""
    
    def test_invalid_token_error(self):
        """Test InvalidTokenError exception."""
        exc = InvalidTokenError()
        assert exc.code == "INVALID_TOKEN"
        assert exc.status_code == 401
        assert "malformed" in exc.message.lower() or "invalid" in exc.message.lower()
    
    def test_token_expired_error(self):
        """Test TokenExpiredError exception."""
        exc = TokenExpiredError()
        assert exc.code == "TOKEN_EXPIRED"
        assert exc.status_code == 401
        assert "expired" in exc.message.lower()
    
    def test_invalid_credentials_error(self):
        """Test InvalidCredentialsError exception."""
        exc = InvalidCredentialsError()
        assert exc.code == "INVALID_CREDENTIALS"
        assert exc.status_code == 401
        assert "credentials" in exc.message.lower()
    
    def test_invalid_passcode_error(self):
        """Test InvalidPasscodeError exception."""
        exc = InvalidPasscodeError()
        assert exc.code == "INVALID_PASSCODE"
        assert exc.status_code == 401
        assert "passcode" in exc.message.lower()
    
    def test_forbidden_error(self):
        """Test ForbiddenError exception."""
        exc = ForbiddenError()
        assert exc.code == "FORBIDDEN"
        assert exc.status_code == 403
    
    def test_event_not_owned_error(self):
        """Test EventNotOwnedError exception."""
        exc = EventNotOwnedError()
        assert exc.code == "EVENT_NOT_OWNED"
        assert exc.status_code == 403
        assert "own" in exc.message.lower()
    
    def test_downloads_disabled_error(self):
        """Test DownloadsDisabledError exception."""
        exc = DownloadsDisabledError()
        assert exc.code == "DOWNLOADS_DISABLED"
        assert exc.status_code == 403
        assert "download" in exc.message.lower()
    
    def test_invalid_image_format_error(self):
        """Test InvalidImageFormatError exception."""
        exc = InvalidImageFormatError()
        assert exc.code == "INVALID_IMAGE_FORMAT"
        assert exc.status_code == 400
    
    def test_missing_required_field_error(self):
        """Test MissingRequiredFieldError exception."""
        exc = MissingRequiredFieldError("email")
        assert exc.code == "MISSING_REQUIRED_FIELD"
        assert exc.status_code == 400
        assert "email" in exc.message
        assert exc.details["field"] == "email"
    
    def test_duplicate_email_error(self):
        """Test DuplicateEmailError exception."""
        exc = DuplicateEmailError()
        assert exc.code == "DUPLICATE_EMAIL"
        assert exc.status_code == 400
        assert "email" in exc.message.lower()
    
    def test_rate_limit_exceeded_error(self):
        """Test RateLimitExceededError exception."""
        exc = RateLimitExceededError(retry_after=60)
        assert exc.code == "RATE_LIMIT_EXCEEDED"
        assert exc.status_code == 429
        assert exc.retry_after == 60
    
    def test_event_not_found_error(self):
        """Test EventNotFoundError exception."""
        exc = EventNotFoundError()
        assert exc.code == "EVENT_NOT_FOUND"
        assert exc.status_code == 404
    
    def test_image_not_found_error(self):
        """Test ImageNotFoundError exception."""
        exc = ImageNotFoundError()
        assert exc.code == "IMAGE_NOT_FOUND"
        assert exc.status_code == 404
    
    def test_user_not_found_error(self):
        """Test UserNotFoundError exception."""
        exc = UserNotFoundError()
        assert exc.code == "USER_NOT_FOUND"
        assert exc.status_code == 404
    
    def test_face_detection_failed_error(self):
        """Test FaceDetectionFailedError exception."""
        exc = FaceDetectionFailedError()
        assert exc.code == "FACE_DETECTION_FAILED"
        assert exc.status_code == 500
    
    def test_storage_error(self):
        """Test StorageError exception."""
        exc = StorageError()
        assert exc.code == "STORAGE_ERROR"
        assert exc.status_code == 500
    
    def test_database_error(self):
        """Test DatabaseError exception."""
        exc = DatabaseError()
        assert exc.code == "DATABASE_ERROR"
        assert exc.status_code == 500


class TestExceptionHandlers:
    """Test exception handler functions."""
    
    @pytest.mark.asyncio
    async def test_picur_exception_handler(self):
        """Test PicUr exception handler."""
        mock_request = Mock(spec=Request)
        mock_request.method = "GET"
        mock_request.url = "http://test.com/api/test"
        mock_request.client = Mock()
        mock_request.client.host = "127.0.0.1"
        
        exc = InvalidTokenError()
        response = await picur_exception_handler(mock_request, exc)
        
        assert response.status_code == 401
        data = response.body.decode()
        assert "INVALID_TOKEN" in data
    
    @pytest.mark.asyncio
    async def test_rate_limit_exception_handler_includes_retry_after(self):
        """Test rate limit exception includes Retry-After header."""
        mock_request = Mock(spec=Request)
        mock_request.method = "POST"
        mock_request.url = "http://test.com/api/scan"
        mock_request.client = Mock()
        mock_request.client.host = "127.0.0.1"
        
        exc = RateLimitExceededError(retry_after=120)
        response = await picur_exception_handler(mock_request, exc)
        
        assert response.status_code == 429
        assert "Retry-After" in response.headers
        assert response.headers["Retry-After"] == "120"
    
    @pytest.mark.asyncio
    async def test_sqlalchemy_exception_handler(self):
        """Test SQLAlchemy exception handler."""
        mock_request = Mock(spec=Request)
        mock_request.method = "POST"
        mock_request.url = "http://test.com/api/test"
        mock_request.client = Mock()
        mock_request.client.host = "127.0.0.1"
        
        exc = SQLAlchemyError("Database connection failed")
        response = await sqlalchemy_exception_handler(mock_request, exc)
        
        assert response.status_code == 500
        data = response.body.decode()
        assert "DATABASE_ERROR" in data
    
    @pytest.mark.asyncio
    async def test_s3_exception_handler(self):
        """Test MinIO S3 exception handler."""
        mock_request = Mock(spec=Request)
        mock_request.method = "GET"
        mock_request.url = "http://test.com/api/photos"
        mock_request.client = Mock()
        mock_request.client.host = "127.0.0.1"
        
        exc = S3Error(
            code="NoSuchKey",
            message="Object not found",
            resource="/bucket/key",
            request_id="123",
            host_id="456",
            response=Mock()
        )
        response = await s3_exception_handler(mock_request, exc)
        
        assert response.status_code == 500
        data = response.body.decode()
        assert "STORAGE_ERROR" in data
    
    @pytest.mark.asyncio
    async def test_generic_exception_handler(self):
        """Test generic exception handler for unhandled errors."""
        mock_request = Mock(spec=Request)
        mock_request.method = "POST"
        mock_request.url = "http://test.com/api/test"
        mock_request.client = Mock()
        mock_request.client.host = "127.0.0.1"
        
        exc = ValueError("Unexpected error")
        response = await generic_exception_handler(mock_request, exc)
        
        assert response.status_code == 500
        data = response.body.decode()
        assert "INTERNAL_SERVER_ERROR" in data


class TestErrorLogging:
    """Test error logging functionality."""
    
    @patch('app.error_handler.logger')
    def test_client_error_logging(self, mock_logger):
        """Test that client errors (4xx) are logged as warnings."""
        create_error_response(
            code="BAD_REQUEST",
            message="Invalid input",
            status_code=400
        )
        
        mock_logger.warning.assert_called_once()
    
    @patch('app.error_handler.logger')
    def test_server_error_logging(self, mock_logger):
        """Test that server errors (5xx) are logged as errors."""
        create_error_response(
            code="INTERNAL_ERROR",
            message="Server error",
            status_code=500
        )
        
        mock_logger.error.assert_called_once()
    
    @patch('app.error_handler.logger')
    def test_error_logging_includes_context(self, mock_logger):
        """Test that error logs include request context."""
        mock_request = Mock(spec=Request)
        mock_request.method = "POST"
        mock_request.url = "http://test.com/api/test"
        mock_request.client = Mock()
        mock_request.client.host = "127.0.0.1"
        
        create_error_response(
            code="TEST_ERROR",
            message="Test message",
            status_code=500,
            request=mock_request
        )
        
        # Verify logger was called with context
        mock_logger.error.assert_called_once()
        call_args = mock_logger.error.call_args
        # Check that the log message contains the context information
        assert "method" in str(call_args) or "POST" in str(call_args)


class TestAuthErrorHandling:
    """Test error handling in authentication endpoints."""

    def test_register_duplicate_email_returns_proper_error(self, client):
        """Test registration with duplicate email returns proper error format."""
        import uuid
        unique_email = f"test-{uuid.uuid4()}@example.com"
        # UserRegister validator now requires upper/lower/digit/special.
        password = "SecurePass1!"

        # First registration
        response1 = client.post("/auth/register", json={
            "email": unique_email,
            "password": password,
        })
        assert response1.status_code == 201

        # Duplicate registration
        response2 = client.post("/auth/register", json={
            "email": unique_email,
            "password": password,
        })
        assert response2.status_code == 400
        data = response2.json()
        assert "error" in data
        assert data["error"]["code"] == "DUPLICATE_EMAIL"

    def test_login_invalid_credentials_returns_proper_error(self, client):
        """Test login with invalid credentials returns proper error format."""
        response = client.post("/auth/login", json={
            "email": "nonexistent@example.com",
            "password": "wrongpassword"
        })
        assert response.status_code == 401
        data = response.json()
        assert "error" in data
        assert data["error"]["code"] == "INVALID_CREDENTIALS"

    def test_invalid_token_returns_proper_error(self, client):
        """Test request with invalid token returns proper error format."""
        response = client.get("/auth/me", headers={
            "Authorization": "Bearer invalid_token"
        })
        assert response.status_code in [401, 422]  # Could be validation or auth error
        data = response.json()
        assert "error" in data
