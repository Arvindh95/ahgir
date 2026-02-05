from datetime import timedelta
from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app.auth import (
    UserRegister, UserLogin, TokenResponse, UserResponse,
    hash_password, verify_password, create_access_token, get_current_user
)
from app.database import get_db
from app.models import User
from app.config import settings
from app.exceptions import DuplicateEmailError, InvalidCredentialsError

router = APIRouter(prefix="/auth", tags=["authentication"])

@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(user_data: UserRegister, db: Session = Depends(get_db)):
    """
    Register a new Admin account
    
    - **email**: Valid email address
    - **password**: Password (will be hashed with bcrypt)
    
    Returns the created user information
    """
    # Hash the password
    password_hash = hash_password(user_data.password)
    
    # Create new user
    new_user = User(
        email=user_data.email,
        password_hash=password_hash
    )
    
    try:
        db.add(new_user)
        db.commit()
        db.refresh(new_user)
    except IntegrityError:
        db.rollback()
        raise DuplicateEmailError()
    
    return UserResponse(
        user_id=str(new_user.id),
        email=new_user.email,
        created_at=new_user.created_at
    )

@router.post("/login", response_model=TokenResponse)
async def login(credentials: UserLogin, db: Session = Depends(get_db)):
    """
    Login with email and password
    
    - **email**: Registered email address
    - **password**: User password
    
    Returns a JWT access token
    """
    # Find user by email
    user = db.query(User).filter(User.email == credentials.email).first()
    
    if not user or not verify_password(credentials.password, user.password_hash):
        raise InvalidCredentialsError()
    
    # Create access token
    access_token_expires = timedelta(hours=settings.jwt_expiration_hours)
    access_token = create_access_token(
        data={"sub": str(user.id), "email": user.email},
        expires_delta=access_token_expires
    )
    
    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        expires_in=settings.jwt_expiration_hours * 3600  # Convert to seconds
    )

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
