import logging
import uuid as _uuid
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from app.auth import SESSION_COOKIE, EVENT_COOKIE
from app.routers import abuse_reports, admin, auth, events, guest, guest_accuracy, health, payments, photos
from app.error_handler import register_error_handlers
from app.config import settings, validate_production_secrets

# Run prod-secret validation only in the API process (workers import config but
# don't need Stripe/CORS). Raises RuntimeError on insecure config.
validate_production_secrets()

logger = logging.getLogger(__name__)

# Disable interactive docs + OpenAPI schema in production. The whole app is
# proxied at /api/* by Caddy, so /api/docs and /api/openapi.json would
# otherwise be reachable from the public internet — leaking the full route
# inventory + payload shapes + auth requirements to scanners.
_is_prod = settings.environment.lower() == "production"
app = FastAPI(
    title="PicUr API",
    version="1.0.0",
    docs_url=None if _is_prod else "/docs",
    redoc_url=None if _is_prod else "/redoc",
    openapi_url=None if _is_prod else "/openapi.json",
)

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


# CSRF defense for cookie-auth: any state-changing request that arrives with
# a session/event cookie attached MUST also carry the X-Requested-With
# header. Browsers will never set that header on a vanilla form post or
# <img>-style attacker-triggered request, so this rejects classic CSRF.
# SameSite=Strict on the cookies is the primary defense; this is belt &
# braces in case a browser ever ships with a buggier interpretation.
_CSRF_EXEMPT_PREFIXES = ("/payments/webhook", "/stripe/webhook", "/health")


class CsrfMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.method in ("GET", "HEAD", "OPTIONS"):
            return await call_next(request)
        path = request.url.path
        if any(path.startswith(p) for p in _CSRF_EXEMPT_PREFIXES):
            return await call_next(request)
        # Only enforce on cookie-bearing requests. A pure Bearer client (e.g.
        # an external integration that doesn't have the cookie) is not vulnerable
        # to CSRF — the attacker can't make the browser attach a Bearer header.
        # Today we only have first-party callers, but keeping the gate
        # cookie-scoped means we don't break a future API-key integration.
        has_auth_cookie = SESSION_COOKIE in request.cookies or EVENT_COOKIE in request.cookies
        if not has_auth_cookie:
            return await call_next(request)
        if request.headers.get("x-requested-with") != "XMLHttpRequest":
            return JSONResponse(
                status_code=403,
                content={"detail": "CSRF check failed: missing X-Requested-With"},
            )
        return await call_next(request)


app.add_middleware(CsrfMiddleware)
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

# Include routers. guest_accuracy must be registered before guest because both
# define POST /scan; FastAPI resolves routes in registration order.
app.include_router(abuse_reports.router)
app.include_router(admin.router)
app.include_router(auth.router)
app.include_router(events.router)
app.include_router(guest_accuracy.router)
app.include_router(guest.router)
app.include_router(health.router)
app.include_router(payments.router)
app.include_router(photos.router)
