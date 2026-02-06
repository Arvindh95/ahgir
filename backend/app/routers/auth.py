from datetime import timedelta
from fastapi import APIRouter, Depends, Request, status
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app.auth import (
    UserRegister, UserLogin, TokenResponse, UserResponse,
    hash_password, verify_password, create_access_token, get_current_user,
    create_verification_token, decode_token
)
from app.database import get_db
from app.models import User
from app.config import settings
from app.exceptions import DuplicateEmailError, InvalidCredentialsError, EmailNotVerifiedError, InvalidTokenError
from app.email import send_verification_email
from app.rate_limiter import auth_rate_limiter

router = APIRouter(prefix="/auth", tags=["authentication"])


class VerifyRequest(BaseModel):
    token: str


class ResendVerifyRequest(BaseModel):
    email: EmailStr


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

    # Send verification email
    token = create_verification_token(new_user.id)
    verify_url = f"{settings.frontend_url}/admin/verify?token={token}"
    try:
        send_verification_email(new_user.email, verify_url)
    except Exception as e:
        # Log but don't fail registration
        print(f"Failed to send verification email: {e}")

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
async def resend_verification(request: ResendVerifyRequest, db: Session = Depends(get_db)):
    """
    Resend verification email to registered email address.
    """
    user = db.query(User).filter(User.email == request.email).first()

    # Don't reveal if email exists or not
    if not user:
        return MessageResponse(message="If the email is registered, a verification link has been sent")

    if user.is_verified:
        return MessageResponse(message="Email is already verified")

    token = create_verification_token(user.id)
    verify_url = f"{settings.frontend_url}/admin/verify?token={token}"
    try:
        send_verification_email(user.email, verify_url)
    except Exception as e:
        print(f"Failed to send verification email: {e}")

    return MessageResponse(message="If the email is registered, a verification link has been sent")


@router.get("/me", response_model=UserResponse)
async def get_me(current_user: User = Depends(get_current_user)):
    """
    Get current user information from JWT token

    Requires valid JWT token in Authorization header
    """
    return UserResponse(
        user_id=str(current_user.id),
        email=current_user.email,
        created_at=current_user.created_at
    )
