import base64
import hashlib
from datetime import datetime, timedelta
from typing import Optional
from fastapi import Depends, HTTPException, Request, Response
from jose import JWTError, jwt
import bcrypt
from sqlalchemy.orm import Session
from pydantic import BaseModel, EmailStr, field_validator
import re
import uuid

from app.config import settings
from app.database import get_db
from app.models import User

# Cookie names. Kept short + namespaced so they don't collide with anything
# else served from picur.my (CSAI-OCR, future apps).
SESSION_COOKIE = "picur_session"   # admin / event-owner JWT
EVENT_COOKIE = "picur_event"       # guest event JWT
# Short-lived CSRF guard for the Google OAuth handshake. Holds the random
# `state` value while the user is away at Google's consent screen.
OAUTH_STATE_COOKIE = "picur_oauth_state"


def _cookie_kwargs(max_age: int, samesite: str = "strict") -> dict:
    """Shared HttpOnly cookie settings.

    httponly: not readable from JS — kills the XSS-exfil class.
    secure: only sent over HTTPS in prod. Disabled in dev so localhost works.
    samesite=strict: not sent on cross-site navigations; prevents CSRF. The
      OAuth state cookie overrides this to "lax" — Strict would be dropped on
      Google's cross-site redirect back to /auth/google/callback, breaking the
      state check. Lax still withholds the cookie from embedded/POST cross-site
      requests, which is all the state guard needs.
    """
    secure = settings.environment == "production"
    return dict(
        max_age=max_age,
        httponly=True,
        secure=secure,
        samesite=samesite,
        path="/",
    )


def set_session_cookie(response: Response, token: str) -> None:
    """Attach the admin JWT as an HttpOnly cookie on the outgoing response."""
    response.set_cookie(
        key=SESSION_COOKIE,
        value=token,
        **_cookie_kwargs(max_age=settings.jwt_expiration_hours * 3600),
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(key=SESSION_COOKIE, path="/")


def set_event_cookie(response: Response, token: str, max_age_seconds: int) -> None:
    """Attach the guest event JWT as an HttpOnly cookie."""
    response.set_cookie(
        key=EVENT_COOKIE,
        value=token,
        **_cookie_kwargs(max_age=max_age_seconds),
    )


def clear_event_cookie(response: Response) -> None:
    response.delete_cookie(key=EVENT_COOKIE, path="/")


def set_oauth_state_cookie(response: Response, state: str, max_age_seconds: int = 600) -> None:
    """Store the OAuth `state` while the user is at Google's consent screen.

    SameSite=Lax (not Strict) so the browser still sends it on the top-level
    GET redirect Google issues back to our callback. 10-minute TTL bounds how
    long a handshake can stay open.
    """
    response.set_cookie(
        key=OAUTH_STATE_COOKIE,
        value=state,
        **_cookie_kwargs(max_age=max_age_seconds, samesite="lax"),
    )


def clear_oauth_state_cookie(response: Response) -> None:
    response.delete_cookie(key=OAUTH_STATE_COOKIE, path="/")


def _bearer_from_header(request: Request) -> Optional[str]:
    auth_header = request.headers.get("authorization") or ""
    if auth_header.lower().startswith("bearer "):
        return auth_header[7:].strip() or None
    return None


def _read_session_token(request: Request) -> Optional[str]:
    """Cookie is the production auth. Authorization Bearer header is a
    test/integration fallback — kept so the existing pytest suite (and
    future server-to-server clients) keep working without rewrite.

    Bearer is checked FIRST when present so a test can override a stale
    cookie left over from a previous test on the same module-level
    TestClient. In production the frontend never sets a Bearer header,
    so the cookie path is what runs.

    The XSS-exfil concern that motivated the cookie migration is a
    FRONTEND issue: an attacker can't extract a Bearer token from the
    real app because the frontend no longer stores one anywhere reachable
    from JS. Whether the backend additionally accepts Bearer or not is
    independent of that property.
    """
    bearer = _bearer_from_header(request)
    if bearer is not None:
        return bearer
    return request.cookies.get(SESSION_COOKIE)


def _read_event_token(request: Request) -> Optional[str]:
    """Bearer-first / cookie-fallback. Same rationale as _read_session_token."""
    bearer = _bearer_from_header(request)
    if bearer is not None:
        return bearer
    return request.cookies.get(EVENT_COOKIE)

# Pydantic models
def _normalize_email(v: str) -> str:
    """Lowercase + strip the email at the schema boundary so User@x and user@x
    cannot create duplicate accounts and so login/reset/verify lookups don't
    mismatch on casing. Most mail providers treat the local-part as
    case-insensitive in practice, so this matches user expectation."""
    return v.strip().lower()


class UserRegister(BaseModel):
    email: EmailStr
    password: str

    @field_validator("email", mode="after")
    @classmethod
    def _normalize_email(cls, v: str) -> str:
        return _normalize_email(v)

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        if not re.search(r"[A-Z]", v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not re.search(r"[a-z]", v):
            raise ValueError("Password must contain at least one lowercase letter")
        if not re.search(r"\d", v):
            raise ValueError("Password must contain at least one digit")
        if not re.search(r"[!@#$%^&*(),.?\":{}|<>]", v):
            raise ValueError("Password must contain at least one special character")
        return v

class UserLogin(BaseModel):
    email: EmailStr
    password: str

    @field_validator("email", mode="after")
    @classmethod
    def _normalize_email(cls, v: str) -> str:
        return _normalize_email(v)

class TokenResponse(BaseModel):
    access_token: str
    token_type: str
    expires_in: int

class UserResponse(BaseModel):
    user_id: str
    email: str
    is_superadmin: bool = False
    created_at: datetime

class EventTokenPayload(BaseModel):
    event_id: str
    session_id: str

# Bcrypt has a 72-byte input limit and silently truncates beyond that — two distinct
# long passwords would hash identically. Pre-hashing with SHA256 (32 bytes) avoids the
# truncation surprise entirely while keeping long passwords first-class.
def _prehash_for_bcrypt(password: str) -> bytes:
    digest = hashlib.sha256(password.encode("utf-8")).digest()
    # base64 to keep bytes printable; output is 44 bytes (well under 72)
    return base64.b64encode(digest)


def hash_password(password: str) -> str:
    """Hash a password using bcrypt over a SHA256 pre-hash."""
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(_prehash_for_bcrypt(password), salt)
    return hashed.decode('utf-8')


def verify_password(plain_password: str, hashed_password: Optional[str]) -> bool:
    """Verify a password. Falls back to legacy 72-byte truncated form for users who
    registered before the pre-hash change so existing logins keep working.

    A NULL/empty hash means the account has no password (Google-OAuth-only).
    Such accounts can never authenticate via /auth/login — return False rather
    than raising, so the login handler reports invalid-credentials normally."""
    if not hashed_password:
        return False
    hashed_bytes = hashed_password.encode('utf-8')
    if bcrypt.checkpw(_prehash_for_bcrypt(plain_password), hashed_bytes):
        return True
    # Legacy verification path — accept old truncated hashes
    legacy_input = plain_password.encode('utf-8')[:72]
    return bcrypt.checkpw(legacy_input, hashed_bytes)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Create a JWT access token (Bearer for admin API)."""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(hours=settings.jwt_expiration_hours)

    to_encode.update({
        "exp": expire,
        "iat": datetime.utcnow(),
        "type": "access",
    })

    encoded_jwt = jwt.encode(to_encode, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)
    return encoded_jwt

def create_verification_token(user_id: uuid.UUID) -> str:
    """Create a JWT token for email verification (expires in 1 hour)"""
    to_encode = {
        "sub": str(user_id),
        "type": "email_verify"
    }
    expire = datetime.utcnow() + timedelta(hours=1)
    to_encode.update({"exp": expire, "iat": datetime.utcnow()})
    return jwt.encode(to_encode, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def create_password_reset_token(user_id: uuid.UUID) -> str:
    """Create a JWT token for password reset (expires in 1 hour)"""
    to_encode = {
        "sub": str(user_id),
        "type": "password_reset"
    }
    expire = datetime.utcnow() + timedelta(hours=1)
    to_encode.update({"exp": expire, "iat": datetime.utcnow()})
    return jwt.encode(to_encode, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def create_event_token(event_id: uuid.UUID, session_id: uuid.UUID, expires_delta: Optional[timedelta] = None) -> str:
    """Create a JWT token scoped to a specific event"""
    to_encode = {
        "event_id": str(event_id),
        "session_id": str(session_id)
    }
    
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(hours=1)  # Event tokens expire in 1 hour
    
    to_encode.update({
        "exp": expire,
        "iat": datetime.utcnow()
    })
    
    encoded_jwt = jwt.encode(to_encode, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)
    return encoded_jwt

def decode_token(token: str) -> dict:
    """Decode and validate a JWT token"""
    from app.exceptions import InvalidTokenError
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
        return payload
    except JWTError:
        raise InvalidTokenError()

# Dependency for getting current user from JWT
async def get_current_user(
    request: Request,
    db: Session = Depends(get_db),
) -> User:
    """Extract and validate JWT token from the picur_session cookie.

    Token used to ride in the Authorization: Bearer header, with the
    same JWT mirrored to localStorage by the frontend — readable by any
    XSS payload on picur.my. The cookie variant is HttpOnly + Secure +
    SameSite=Strict, so JS can't read it and the browser refuses to send
    it on cross-site requests. CSRF is closed by the same SameSite=Strict
    plus the X-Requested-With middleware check.
    """
    from app.exceptions import InvalidTokenError, UserNotFoundError

    token = _read_session_token(request)
    if not token:
        raise InvalidTokenError()

    try:
        payload = decode_token(token)
        user_id: str = payload.get("sub")
        if user_id is None:
            raise InvalidTokenError()
        # Reject email_verify / password_reset tokens — they share `sub` with
        # access tokens but should not authorize protected admin endpoints.
        token_type = payload.get("type")
        if token_type != "access":
            raise InvalidTokenError()
        token_iat = payload.get("iat")
    except JWTError:
        raise InvalidTokenError()

    user = db.query(User).filter(User.id == uuid.UUID(user_id)).first()
    if user is None:
        raise UserNotFoundError()

    if user.is_disabled:
        raise HTTPException(
            status_code=403,
            detail="Account has been disabled"
        )

    # Reject tokens issued before the most recent password change. Stops
    # outstanding sessions from surviving a password reset or rotation.
    if user.password_changed_at and token_iat is not None:
        if datetime.utcfromtimestamp(int(token_iat)) < user.password_changed_at:
            raise InvalidTokenError()

    return user

# Dependency for validating event tokens
async def get_event_from_token(
    request: Request,
    db: Session = Depends(get_db),
) -> EventTokenPayload:
    """Extract and validate Event_Token from the picur_event cookie.

    See get_current_user docstring for the same cookie/CSRF rationale.
    Still verifies the JWT signature/expiry AND looks up the GuestSession
    row so a revoked/deleted session takes effect immediately rather than
    waiting for the JWT to expire on its own.
    """
    from app.exceptions import InvalidTokenError
    from app.models import GuestSession
    from datetime import datetime
    import uuid as _uuid

    token = _read_event_token(request)
    if not token:
        raise InvalidTokenError()

    try:
        payload = decode_token(token)
        event_id: str = payload.get("event_id")
        session_id: str = payload.get("session_id")

        if event_id is None or session_id is None:
            raise InvalidTokenError()
    except JWTError:
        raise InvalidTokenError()

    # Validate the session row exists, belongs to the claimed event, and
    # hasn't been revoked/expired in the database.
    try:
        session_uuid = _uuid.UUID(session_id)
        event_uuid = _uuid.UUID(event_id)
    except ValueError:
        raise InvalidTokenError()

    session = (
        db.query(GuestSession)
        .filter(GuestSession.id == session_uuid)
        .first()
    )
    if session is None:
        raise InvalidTokenError()
    if session.event_id != event_uuid:
        raise InvalidTokenError()
    if session.expires_at and session.expires_at < datetime.utcnow():
        raise InvalidTokenError()

    # Reject guest access to frozen/expired events. Frozen events are read-only
    # from the photographer's side, but without this check existing guest JWTs
    # could continue scanning and downloading until natural expiry.
    from app.models import Event as _Event
    event = db.query(_Event).filter(_Event.id == event_uuid).first()
    if event is None or event.status != 'active':
        raise InvalidTokenError()

    return EventTokenPayload(event_id=event_id, session_id=session_id)

