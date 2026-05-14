import logging
import uuid as uuid_module
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, Request, status

logger = logging.getLogger(__name__)
from pydantic import BaseModel, EmailStr, ValidationError, field_validator
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app.auth import (
    UserRegister, UserLogin, TokenResponse, UserResponse,
    hash_password, verify_password, create_access_token, get_current_user,
    create_verification_token, create_password_reset_token, decode_token
)
from app.database import get_db
from app.models import User, UserTier
from app.tiers import TIER_CONFIG
from app.config import settings
from app.exceptions import DuplicateEmailError, InvalidCredentialsError, EmailNotVerifiedError, InvalidTokenError
from app.queue import enqueue_email, enqueue_password_reset_email
from app.rate_limiter import auth_rate_limiter

router = APIRouter(prefix="/auth", tags=["authentication"])


class VerifyRequest(BaseModel):
    token: str


def _normalize_email(v: str) -> str:
    return v.strip().lower()


class ResendVerifyRequest(BaseModel):
    email: EmailStr

    @field_validator("email", mode="after")
    @classmethod
    def _norm(cls, v: str) -> str:
        return _normalize_email(v)


class ForgotPasswordRequest(BaseModel):
    email: EmailStr

    @field_validator("email", mode="after")
    @classmethod
    def _norm(cls, v: str) -> str:
        return _normalize_email(v)


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str


class MessageResponse(BaseModel):
    message: str


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(user_data: UserRegister, request: Request, db: Session = Depends(get_db)):
    """
    Register a new Admin account

    - **email**: Valid email address
    - **password**: Password (will be hashed with bcrypt)

    Sends a verification email. User must verify before logging in.
    """
    client_ip = request.client.host if request.client else "unknown"
    auth_rate_limiter.enforce_rate_limit(client_ip, action="register")

    password_hash = hash_password(user_data.password)

    new_user = User(
        email=user_data.email,
        password_hash=password_hash,
        is_verified=False
    )

    try:
        db.add(new_user)
        db.commit()
        db.refresh(new_user)
    except IntegrityError:
        db.rollback()
        raise DuplicateEmailError()

    # Eagerly create the free UserTier row so first-event flow does not race
    # to INSERT it under concurrent requests. create_event() still defends
    # against the missing row for legacy pre-tier accounts, but new accounts
    # will always find an existing row when they create their first event.
    free_cfg = TIER_CONFIG["free"]
    user_tier_row = UserTier(
        user_id=new_user.id,
        tier_name="free",
        max_events=free_cfg["max_events"],
        max_photos_per_event=free_cfg["max_photos_per_event"],
        price_cents=0,
        is_active=True,
        activated_at=datetime.utcnow(),
    )
    try:
        db.add(user_tier_row)
        db.commit()
    except IntegrityError:
        # Another path beat us to it (shouldn't happen mid-register, but treat
        # as harmless idempotency).
        db.rollback()

    # Queue verification email in background, with a synchronous fallback
    # if Redis / RQ is unreachable. Pre-fix the handler logged the
    # enqueue failure and still returned 201 with "check your email" —
    # the user got a confirmation but no email ever arrived. The dual
    # strategy keeps the happy path fast (background queue) while making
    # the failure mode either deliver via sync send or surface a clean
    # 503 so the client can retry.
    token = create_verification_token(new_user.id)
    verify_url = f"{settings.frontend_url}/admin/verify?token={token}"
    delivered = False
    try:
        enqueue_email(new_user.email, verify_url)
        delivered = True
    except Exception as e:
        logger.error(f"Failed to enqueue verification email: {e}")
        try:
            from app.email import send_verification_email
            send_verification_email(new_user.email, verify_url)
            delivered = True
            logger.warning(
                f"Verification email for {new_user.email} fell back to synchronous send "
                f"(enqueue path unavailable)"
            )
        except Exception as sync_e:
            logger.error(
                f"Synchronous verification-email fallback also failed for {new_user.email}: {sync_e}"
            )

    if not delivered:
        # The user row is committed, so they CAN log in via /resend-verify
        # once email delivery is back. 503 signals a transient problem
        # rather than a permanent registration failure.
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Account created but the verification email could not be sent. "
                "Please use 'Resend verification email' shortly."
            ),
        )

    return UserResponse(
        user_id=str(new_user.id),
        email=new_user.email,
        created_at=new_user.created_at
    )


@router.post("/login", response_model=TokenResponse)
async def login(credentials: UserLogin, request: Request, db: Session = Depends(get_db)):
    """
    Login with email and password

    - **email**: Registered email address
    - **password**: User password

    Returns a JWT access token. Requires verified email.
    """
    client_ip = request.client.host if request.client else "unknown"
    # IP-keyed limit catches a single source mashing the endpoint. The email-keyed
    # limit catches a distributed credential-stuffing attempt that targets one
    # account from many IPs — IP-only protection misses that case. Enforce both;
    # whichever trips first short-circuits with 429 before the bcrypt check runs.
    auth_rate_limiter.enforce_rate_limit(client_ip, action="login_ip")
    auth_rate_limiter.enforce_rate_limit(credentials.email, action="login_email")

    user = db.query(User).filter(User.email == credentials.email).first()

    if not user or not verify_password(credentials.password, user.password_hash):
        raise InvalidCredentialsError()

    if not user.is_verified:
        raise EmailNotVerifiedError()

    if user.is_disabled:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account has been disabled. Contact an administrator."
        )

    access_token_expires = timedelta(hours=settings.jwt_expiration_hours)
    access_token = create_access_token(
        data={"sub": str(user.id), "email": user.email},
        expires_delta=access_token_expires
    )

    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        expires_in=settings.jwt_expiration_hours * 3600
    )


@router.post("/verify", response_model=MessageResponse)
async def verify_email(request: VerifyRequest, db: Session = Depends(get_db)):
    """
    Verify email address using token from verification link.
    """
    try:
        payload = decode_token(request.token)
    except Exception:
        raise InvalidTokenError("Invalid or expired verification link")

    if payload.get("type") != "email_verify":
        raise InvalidTokenError("Invalid verification token")

    user_id = payload.get("sub")
    if not user_id:
        raise InvalidTokenError("Invalid verification token")

    # JWT contents are signature-trusted but not type-validated. Parse the
    # UUID before querying so a malformed `sub` returns 400 (InvalidToken)
    # instead of bubbling up as 500 from a Postgres UUID coercion error.
    try:
        user_uuid = uuid_module.UUID(user_id)
    except (ValueError, TypeError):
        raise InvalidTokenError("Invalid verification token")

    user = db.query(User).filter(User.id == user_uuid).first()
    if not user:
        raise InvalidTokenError("User not found")

    if user.is_verified:
        return MessageResponse(message="Email already verified")

    user.is_verified = True
    db.commit()

    return MessageResponse(message="Email verified successfully")


@router.post("/resend-verify", response_model=MessageResponse)
async def resend_verification(
    request: ResendVerifyRequest,
    http_request: Request,
    db: Session = Depends(get_db),
):
    """
    Resend verification email.

    Always returns the same generic response regardless of whether the email
    is registered, unverified, or already verified — otherwise the differing
    responses leak account state to attackers. Rate-limited per IP and per
    email so the endpoint can't be used as a free spam relay.
    """
    GENERIC = MessageResponse(message="If the email is unverified, a new verification link has been sent")

    client_ip = http_request.client.host if http_request.client else "unknown"
    auth_rate_limiter.enforce_rate_limit(client_ip, action="resend_verify_ip")
    # Pydantic field validator already lowered the email at the schema boundary.
    auth_rate_limiter.enforce_rate_limit(request.email, action="resend_verify_email")

    user = db.query(User).filter(User.email == request.email).first()
    if not user or user.is_verified:
        return GENERIC

    token = create_verification_token(user.id)
    verify_url = f"{settings.frontend_url}/admin/verify?token={token}"
    delivered = False
    try:
        enqueue_email(user.email, verify_url)
        delivered = True
    except Exception as e:
        logger.error(f"Failed to enqueue verification email: {e}")
        try:
            from app.email import send_verification_email
            send_verification_email(user.email, verify_url)
            delivered = True
            logger.warning(
                f"Resend-verify for {user.email} fell back to synchronous send"
            )
        except Exception as sync_e:
            logger.error(
                f"Synchronous resend-verify fallback also failed for {user.email}: {sync_e}"
            )

    if not delivered:
        # The user explicitly clicked Resend — they're entitled to a
        # clear failure signal if delivery isn't happening, rather than
        # the misleading GENERIC "we sent it" response.
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Email service temporarily unavailable. Please try again in a moment.",
        )

    return GENERIC


@router.post("/forgot-password", response_model=MessageResponse)
async def forgot_password(request_data: ForgotPasswordRequest, request: Request, db: Session = Depends(get_db)):
    """
    Request a password reset link. Always returns success to prevent email enumeration.
    """
    client_ip = request.client.host if request.client else "unknown"
    auth_rate_limiter.enforce_rate_limit(client_ip, action="forgot_password_ip")
    auth_rate_limiter.enforce_rate_limit(request_data.email, action="forgot_password_email")

    user = db.query(User).filter(User.email == request_data.email).first()

    # Only send if user exists and is verified
    if user and user.is_verified:
        token = create_password_reset_token(user.id)
        reset_url = f"{settings.frontend_url}/admin/reset-password?token={token}"
        try:
            enqueue_password_reset_email(user.email, reset_url)
        except Exception as e:
            logger.error(f"Failed to enqueue password reset email: {e}")
            # Synchronous fallback so a Redis outage doesn't silently
            # withhold reset links. Unlike /register and /resend-verify,
            # we do NOT raise 503 even if BOTH paths fail — that would
            # leak whether the email exists (enumeration). We log
            # alerting-loud instead so ops can intervene.
            try:
                from app.email import send_password_reset_email
                send_password_reset_email(user.email, reset_url)
                logger.warning(
                    f"Forgot-password for {user.email} fell back to synchronous send"
                )
            except Exception as sync_e:
                logger.critical(
                    f"BOTH async + sync password-reset delivery failed for "
                    f"{user.email}: enqueue={e}; sync={sync_e}. User cannot "
                    f"recover their account without manual intervention."
                )

    return MessageResponse(message="If the email is registered, a password reset link has been sent")


@router.post("/reset-password", response_model=MessageResponse)
async def reset_password(request_data: ResetPasswordRequest, db: Session = Depends(get_db)):
    """
    Reset password using a token from the reset email.

    A reset link is single-use: the moment we change the password we update
    `password_changed_at`, and the same handler rejects any token whose `iat`
    is older than that timestamp. So a leaked or replayed reset URL stops
    working as soon as the first valid use completes.
    """
    try:
        payload = decode_token(request_data.token)
    except Exception:
        raise InvalidTokenError("Invalid or expired reset link")

    if payload.get("type") != "password_reset":
        raise InvalidTokenError("Invalid reset token")

    user_id = payload.get("sub")
    token_iat = payload.get("iat")
    if not user_id:
        raise InvalidTokenError("Invalid reset token")

    try:
        user_uuid = uuid_module.UUID(user_id)
    except (ValueError, TypeError):
        raise InvalidTokenError("Invalid reset token")

    # Lock the user row for the read-check-write sequence below. Without
    # SELECT ... FOR UPDATE two parallel requests using the same valid reset
    # token can both pass the password_changed_at check before either has
    # committed, allowing the second password (e.g. an attacker-supplied one)
    # to overwrite the legitimate user's. The row lock serialises the two
    # transactions so the second one sees the freshly-written password_changed_at
    # and is rejected with "Reset link has already been used".
    user = (
        db.query(User)
        .filter(User.id == user_uuid)
        .with_for_update()
        .first()
    )
    if not user:
        raise InvalidTokenError("User not found")

    # Reject tokens issued before the user's most recent password change.
    # First successful reset sets password_changed_at; any later attempt with
    # the same (now-stale) JWT is rejected here.
    if user.password_changed_at and token_iat is not None:
        if datetime.utcfromtimestamp(int(token_iat)) < user.password_changed_at:
            raise InvalidTokenError("Reset link has already been used")

    # Validate password strength using the same rules as registration
    try:
        UserRegister.model_validate({"email": user.email, "password": request_data.new_password})
    except ValidationError as e:
        first_msg = e.errors()[0].get("msg", "Invalid password") if e.errors() else "Invalid password"
        # Pydantic v2 prefixes user messages with "Value error, " — strip it.
        if first_msg.startswith("Value error, "):
            first_msg = first_msg[len("Value error, "):]
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=first_msg
        )

    user.password_hash = hash_password(request_data.new_password)
    user.password_changed_at = datetime.utcnow()
    db.commit()

    return MessageResponse(message="Password reset successfully")


@router.get("/me", response_model=UserResponse)
async def get_me(current_user: User = Depends(get_current_user)):
    """
    Get current user information from JWT token

    Requires valid JWT token in Authorization header
    """
    return UserResponse(
        user_id=str(current_user.id),
        email=current_user.email,
        is_superadmin=current_user.is_superadmin,
        created_at=current_user.created_at
    )
