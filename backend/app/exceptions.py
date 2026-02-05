"""Custom exceptions and error handling for PicUr API."""

from typing import Optional, Dict, Any


class PicUrException(Exception):
    """Base exception for all PicUr errors."""
    
    def __init__(
        self,
        message: str,
        code: str,
        status_code: int = 500,
        details: Optional[Dict[str, Any]] = None
    ):
        self.message = message
        self.code = code
        self.status_code = status_code
        self.details = details or {}
        super().__init__(self.message)


# Authentication Errors (401)
class InvalidTokenError(PicUrException):
    """JWT token is malformed or invalid."""
    
    def __init__(self, message: str = "JWT token is malformed or invalid", details: Optional[Dict[str, Any]] = None):
        super().__init__(message, "INVALID_TOKEN", 401, details)


class TokenExpiredError(PicUrException):
    """JWT token has exceeded expiration time."""
    
    def __init__(self, message: str = "JWT token has expired", details: Optional[Dict[str, Any]] = None):
        super().__init__(message, "TOKEN_EXPIRED", 401, details)


class InvalidCredentialsError(PicUrException):
    """Email/password combination is incorrect."""
    
    def __init__(self, message: str = "Invalid credentials", details: Optional[Dict[str, Any]] = None):
        super().__init__(message, "INVALID_CREDENTIALS", 401, details)


class InvalidPasscodeError(PicUrException):
    """Event passcode is incorrect."""
    
    def __init__(self, message: str = "Invalid passcode", details: Optional[Dict[str, Any]] = None):
        super().__init__(message, "INVALID_PASSCODE", 401, details)


# Authorization Errors (403)
class ForbiddenError(PicUrException):
    """User does not have permission to access resource."""
    
    def __init__(self, message: str = "Access forbidden", details: Optional[Dict[str, Any]] = None):
        super().__init__(message, "FORBIDDEN", 403, details)


class EventNotOwnedError(PicUrException):
    """Admin attempting to access another Admin's Event."""
    
    def __init__(self, message: str = "You do not own this event", details: Optional[Dict[str, Any]] = None):
        super().__init__(message, "EVENT_NOT_OWNED", 403, details)


class DownloadsDisabledError(PicUrException):
    """Guest attempting to download when not allowed."""
    
    def __init__(self, message: str = "Downloads are disabled for this event", details: Optional[Dict[str, Any]] = None):
        super().__init__(message, "DOWNLOADS_DISABLED", 403, details)


# Validation Errors (400)
class InvalidImageFormatError(PicUrException):
    """Uploaded file is not a valid image."""
    
    def __init__(self, message: str = "Invalid image format", details: Optional[Dict[str, Any]] = None):
        super().__init__(message, "INVALID_IMAGE_FORMAT", 400, details)


class MissingRequiredFieldError(PicUrException):
    """Required field is missing from request."""
    
    def __init__(self, field: str, details: Optional[Dict[str, Any]] = None):
        message = f"Missing required field: {field}"
        super().__init__(message, "MISSING_REQUIRED_FIELD", 400, details or {"field": field})


class InvalidSlugError(PicUrException):
    """Event slug format is invalid."""
    
    def __init__(self, message: str = "Invalid slug format", details: Optional[Dict[str, Any]] = None):
        super().__init__(message, "INVALID_SLUG", 400, details)


class DuplicateEmailError(PicUrException):
    """Email already registered."""
    
    def __init__(self, message: str = "Email already registered", details: Optional[Dict[str, Any]] = None):
        super().__init__(message, "DUPLICATE_EMAIL", 400, details)


# Rate Limiting Errors (429)
class RateLimitExceededError(PicUrException):
    """Too many requests in time window."""
    
    def __init__(self, retry_after: int, message: str = "Rate limit exceeded", details: Optional[Dict[str, Any]] = None):
        super().__init__(message, "RATE_LIMIT_EXCEEDED", 429, details or {"retry_after": retry_after})
        self.retry_after = retry_after


# Not Found Errors (404)
class EventNotFoundError(PicUrException):
    """Event slug does not exist."""
    
    def __init__(self, message: str = "Event not found", details: Optional[Dict[str, Any]] = None):
        super().__init__(message, "EVENT_NOT_FOUND", 404, details)


class ImageNotFoundError(PicUrException):
    """Image ID does not exist."""
    
    def __init__(self, message: str = "Image not found", details: Optional[Dict[str, Any]] = None):
        super().__init__(message, "IMAGE_NOT_FOUND", 404, details)


class UserNotFoundError(PicUrException):
    """User ID does not exist."""
    
    def __init__(self, message: str = "User not found", details: Optional[Dict[str, Any]] = None):
        super().__init__(message, "USER_NOT_FOUND", 404, details)


# Server Errors (500)
class FaceDetectionFailedError(PicUrException):
    """InsightFace processing error."""
    
    def __init__(self, message: str = "Face detection failed", details: Optional[Dict[str, Any]] = None):
        super().__init__(message, "FACE_DETECTION_FAILED", 500, details)


class StorageError(PicUrException):
    """MinIO operation failed."""
    
    def __init__(self, message: str = "Storage operation failed", details: Optional[Dict[str, Any]] = None):
        super().__init__(message, "STORAGE_ERROR", 500, details)


class DatabaseError(PicUrException):
    """PostgreSQL operation failed."""
    
    def __init__(self, message: str = "Database operation failed", details: Optional[Dict[str, Any]] = None):
        super().__init__(message, "DATABASE_ERROR", 500, details)
