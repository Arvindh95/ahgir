"""Global error handler and logging configuration for PicUr API."""

import logging
import traceback
from typing import Union
from fastapi import Request, status
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from sqlalchemy.exc import SQLAlchemyError
from minio.error import S3Error

from app.exceptions import PicUrException, RateLimitExceededError

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)


def create_error_response(
    code: str,
    message: str,
    status_code: int,
    details: dict = None,
    request: Request = None
) -> JSONResponse:
    """
    Create a standardized error response.
    
    Args:
        code: Error code (e.g., "INVALID_TOKEN")
        message: Human-readable error message
        status_code: HTTP status code
        details: Additional error context
        request: FastAPI request object for logging
    
    Returns:
        JSONResponse with standardized error format
    """
    error_response = {
        "error": {
            "code": code,
            "message": message
        },
        "detail": message  # For backward compatibility with tests
    }
    
    if details:
        error_response["error"]["details"] = details
    
    # Log error with context
    log_context = {
        "code": code,
        "status_code": status_code,
        "message": message
    }
    
    if request:
        log_context.update({
            "method": request.method,
            "url": str(request.url),
            "client": request.client.host if request.client else None
        })
    
    # Log without extra to avoid conflicts with logging system reserved keys
    if status_code >= 500:
        logger.error(f"Server error: {log_context}")
    elif status_code >= 400:
        logger.warning(f"Client error: {log_context}")
    
    return JSONResponse(
        status_code=status_code,
        content=error_response
    )


async def picur_exception_handler(request: Request, exc: PicUrException) -> JSONResponse:
    """
    Handle custom PicUr exceptions.
    
    Args:
        request: FastAPI request object
        exc: PicUrException instance
    
    Returns:
        JSONResponse with error details
    """
    response = create_error_response(
        code=exc.code,
        message=exc.message,
        status_code=exc.status_code,
        details=exc.details,
        request=request
    )
    
    # Add Retry-After header for rate limit errors
    if isinstance(exc, RateLimitExceededError):
        response.headers["Retry-After"] = str(exc.retry_after)
    
    return response


async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """
    Handle FastAPI validation errors.
    
    Args:
        request: FastAPI request object
        exc: RequestValidationError instance
    
    Returns:
        JSONResponse with validation error details
    """
    # Extract field errors
    errors = []
    for error in exc.errors():
        field = ".".join(str(loc) for loc in error["loc"])
        errors.append({
            "field": field,
            "message": error["msg"],
            "type": error["type"]
        })
    
    return create_error_response(
        code="VALIDATION_ERROR",
        message="Request validation failed",
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        details={"errors": errors},
        request=request
    )


async def sqlalchemy_exception_handler(request: Request, exc: SQLAlchemyError) -> JSONResponse:
    """
    Handle SQLAlchemy database errors.
    
    Args:
        request: FastAPI request object
        exc: SQLAlchemyError instance
    
    Returns:
        JSONResponse with database error details
    """
    logger.error(
        f"Database error: {str(exc)}",
        extra={
            "method": request.method,
            "url": str(request.url),
            "error_type": type(exc).__name__,
            "traceback": traceback.format_exc()
        }
    )
    
    return create_error_response(
        code="DATABASE_ERROR",
        message="Database operation failed",
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        details={"error_type": type(exc).__name__},
        request=request
    )


async def s3_exception_handler(request: Request, exc: S3Error) -> JSONResponse:
    """
    Handle MinIO S3 errors.
    
    Args:
        request: FastAPI request object
        exc: S3Error instance
    
    Returns:
        JSONResponse with storage error details
    """
    logger.error(
        f"Storage error: {str(exc)}",
        extra={
            "method": request.method,
            "url": str(request.url),
            "error_code": exc.code,
            "traceback": traceback.format_exc()
        }
    )
    
    return create_error_response(
        code="STORAGE_ERROR",
        message="Storage operation failed",
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        details={"error_code": exc.code},
        request=request
    )


async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """
    Handle all other unhandled exceptions.
    
    Args:
        request: FastAPI request object
        exc: Exception instance
    
    Returns:
        JSONResponse with generic error message
    """
    logger.error(
        f"Unhandled exception: {str(exc)}",
        extra={
            "method": request.method,
            "url": str(request.url),
            "error_type": type(exc).__name__,
            "traceback": traceback.format_exc()
        },
        exc_info=True
    )
    
    return create_error_response(
        code="INTERNAL_SERVER_ERROR",
        message="An unexpected error occurred",
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        details={"error_type": type(exc).__name__},
        request=request
    )


def register_error_handlers(app):
    """
    Register all error handlers with the FastAPI application.
    
    Args:
        app: FastAPI application instance
    """
    app.add_exception_handler(PicUrException, picur_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(SQLAlchemyError, sqlalchemy_exception_handler)
    app.add_exception_handler(S3Error, s3_exception_handler)
    app.add_exception_handler(Exception, generic_exception_handler)
    
    logger.info("Error handlers registered successfully")
