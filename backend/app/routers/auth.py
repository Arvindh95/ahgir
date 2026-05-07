import logging
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, Request, status

logger = logging.getLogger(__name__)
from pydantic import BaseModel, EmailStr, field_validator
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app.auth import (
    UserRegister, UserLogin, TokenResponse, UserResponse,
    hash_password, verify_password, create_access_token, get_current_user,
    create_verification_token, create_password_reset_token, decode_token
)
from app.database import get_db
from app.models import User
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

    # Queue verification email in background
    token = create_verification_token(new_user.id)
    verify_url = f"{settings.frontend_url}/admin/verify?token={token}"
    try:
        enqueue_email(new_user.email, verify_url)
    except Exception as e:
        # Log but don't fail registration
        logger.error(f"Failed to enqueue verification email: {e}")

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
    auth_rate_limiter.enforce_rate_limit(client_ip, action="login")

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

    user = db.query(User).filter(User.id == user_id).first()
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
    try:
        enqueue_email(user.email, verify_url)
    except Exception as e:
        logger.error(f"Failed to enqueue verification email: {e}")

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

    user = db.query(User).filter(User.id == user_id).first()
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
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
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
