from datetime import datetime, timedelta
from typing import Optional
from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
import bcrypt
from sqlalchemy.orm import Session
from pydantic import BaseModel, EmailStr, field_validator
import re
import uuid

from app.config import settings
from app.database import get_db
from app.models import User

# HTTP Bearer token scheme
security = HTTPBearer()

# Pydantic models
class UserRegister(BaseModel):
    email: EmailStr
    password: str

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

# Helper functions
def hash_password(password: str) -> str:
    """Hash a password using bcrypt"""
    # Bcrypt has a 72-byte limit, truncate if necessary
    password_bytes = password.encode('utf-8')[:72]
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password_bytes, salt)
    return hashed.decode('utf-8')

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against a hash"""
    password_bytes = plain_password.encode('utf-8')[:72]
    hashed_bytes = hashed_password.encode('utf-8')
    return bcrypt.checkpw(password_bytes, hashed_bytes)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Create a JWT access token"""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(hours=settings.jwt_expiration_hours)
    
    to_encode.update({
        "exp": expire,
        "iat": datetime.utcnow()
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
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
) -> User:
    """Extract and validate JWT token, return current user"""
    from app.exceptions import InvalidTokenError, UserNotFoundError
    
    token = credentials.credentials
    
    try:
        payload = decode_token(token)
        user_id: str = payload.get("sub")
        if user_id is None:
            raise InvalidTokenError()
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

    return user

# Dependency for validating event tokens
async def get_event_from_token(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> EventTokenPayload:
    """Extract and validate Event_Token, return event_id and session_id"""
    from app.exceptions import InvalidTokenError
    
    token = credentials.credentials
    
    try:
        payload = decode_token(token)
        event_id: str = payload.get("event_id")
        session_id: str = payload.get("session_id")
        
        if event_id is None or session_id is None:
            raise InvalidTokenError()
        
        return EventTokenPayload(event_id=event_id, session_id=session_id)
    except JWTError:
        raise InvalidTokenError()

