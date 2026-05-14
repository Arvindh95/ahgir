"""Global error handler and logging configuration for PicUr API."""

import logging
import traceback
from typing import Union
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse
from fastapi import HTTPException, Request, status
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from sqlalchemy.exc import SQLAlchemyError
from minio.error import S3Error
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.exceptions import PicUrException, RateLimitExceededError

# Query-string keys that carry bearer credentials and must be scrubbed
# before any URL appears in logs. ``sig`` + ``expires`` are the HMAC
# pieces of the signed photo URL (see app.storage.generate_signed_url);
# ``token`` and ``access_token`` cover any future query-token paths.
# Logging the full URL of a 403/404 on /photos/... would otherwise hand
# anyone with log access a still-valid signed download link.
_REDACT_QUERY_KEYS = {"sig", "expires", "token", "access_token", "passcode"}


def _redact_url(raw: str) -> str:
    """Strip credential-bearing query params from a URL before logging.

    Keeps the path + non-sensitive query keys so logs stay useful
    (we can see which endpoint failed, which image_id was requested)
    without leaking the credentials that made the request authorized.
    """
    try:
        parsed = urlparse(raw)
        if not parsed.query:
            return raw
        kept = []
        for k, v in parse_qsl(parsed.query, keep_blank_values=True):
            if k.lower() in _REDACT_QUERY_KEYS:
                kept.append((k, "REDACTED"))
            else:
                kept.append((k, v))
        return urlunparse(parsed._replace(query=urlencode(kept)))
    except Exception:
        # If the URL is too malformed to parse, return a hard-stripped
        # version rather than risk leaking the original.
        return raw.split("?", 1)[0]


# Map HTTP status codes to stable error codes so the frontend has a
# machine-readable hook in addition to the human message. New codes
# can be added without breaking older clients — they still see the
# generic `error.message` field.
_HTTP_STATUS_TO_CODE = {
    400: "BAD_REQUEST",
    401: "UNAUTHORIZED",
    403: "FORBIDDEN",
    404: "NOT_FOUND",
    405: "METHOD_NOT_ALLOWED",
    409: "CONFLICT",
    410: "GONE",
    413: "PAYLOAD_TOO_LARGE",
    415: "UNSUPPORTED_MEDIA_TYPE",
    422: "VALIDATION_ERROR",
    429: "RATE_LIMITED",
    500: "INTERNAL_SERVER_ERROR",
    502: "BAD_GATEWAY",
    503: "SERVICE_UNAVAILABLE",
    504: "GATEWAY_TIMEOUT",
}

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
            "url": _redact_url(str(request.url)),
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
            "url": _redact_url(str(request.url)),
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
            "url": _redact_url(str(request.url)),
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


async def http_exception_handler(
    request: Request, exc: StarletteHTTPException
) -> JSONResponse:
    """Wrap FastAPI / Starlette HTTPException into the standard
    {error: {code, message}} response shape.

    Pre-fix, the global error contract was only enforced for
    PicUrException / RequestValidationError / SQLAlchemyError, but
    routers raise direct HTTPException heavily. Those flowed through
    the default Starlette handler which only emits {"detail": "..."}.
    The frontend errors.ts parser reads err.response.data.error.message
    and falls back to a generic "Failed to X" string, so the actionable
    backend message was lost on every direct-HTTPException path.

    detail may be either a string (the common case) or a dict (some
    routers return structured detail like
    {"code": "EVENT_NOT_ACTIVE", "message": "...", "event_status": ...}).
    For dicts we surface the inner code/message if present, otherwise
    serialise the dict as the message.
    """
    code = _HTTP_STATUS_TO_CODE.get(exc.status_code, "HTTP_ERROR")
    details = None
    if isinstance(exc.detail, dict):
        # Structured detail — surface its own code/message if present.
        inner_code = exc.detail.get("code")
        message = exc.detail.get("message") or str(exc.detail)
        if inner_code:
            code = str(inner_code)
        # Pass remaining keys through as details for clients that want them.
        details = {k: v for k, v in exc.detail.items() if k not in ("code", "message")}
        if not details:
            details = None
    elif exc.detail is None:
        message = "An error occurred"
    else:
        message = str(exc.detail)

    response = create_error_response(
        code=code,
        message=message,
        status_code=exc.status_code,
        details=details,
        request=request,
    )
    # Preserve any headers the original exception set (e.g., Retry-After).
    if getattr(exc, "headers", None):
        for k, v in exc.headers.items():
            response.headers[k] = v
    return response


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
            "url": _redact_url(str(request.url)),
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
    # Wrap Starlette's HTTPException (which FastAPI's HTTPException
    # inherits from) so router-raised HTTPExceptions get the same
    # {error: {code, message}} envelope the rest of the system uses.
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(Exception, generic_exception_handler)

    logger.info("Error handlers registered successfully")
