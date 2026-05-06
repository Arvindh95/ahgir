import logging
import uuid as _uuid
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from app.routers import admin, auth, events, guest, health, payments, photos
from app.error_handler import register_error_handlers
from app.config import settings, validate_production_secrets

# Run prod-secret validation only in the API process (workers import config but
# don't need Stripe/CORS). Raises RuntimeError on insecure config.
validate_production_secrets()

logger = logging.getLogger(__name__)

app = FastAPI(title="PicUr API", version="1.0.0")

# Register error handlers
register_error_handlers(app)


class RequestIdMiddleware(BaseHTTPMiddleware):
    """Propagate X-Request-ID. Use client-provided value if present (Caddy may set one),
    else generate. Echoed back on response so logs and clients can correlate."""

    async def dispatch(self, request: Request, call_next):
        rid = request.headers.get("x-request-id") or _uuid.uuid4().hex
        request.state.request_id = rid
        response = await call_next(request)
        response.headers["x-request-id"] = rid
        return response


app.add_middleware(RequestIdMiddleware)

# CORS configuration
origins = [o.strip() for o in settings.cors_origins.split(",")]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["x-request-id"],
)

# Include routers
app.include_router(admin.router)
app.include_router(auth.router)
app.include_router(events.router)
app.include_router(guest.router)
app.include_router(health.router)
app.include_router(payments.router)
app.include_router(photos.router)
