"""
Unit tests for authentication service
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
import uuid

from app.main import app
from app.database import get_db
from app.models import User
from app.auth import hash_password

client = TestClient(app)

# Password that satisfies the UserRegister validator:
# >=8 chars, upper, lower, digit, special.
VALID_PASSWORD = "SecurePass1!"


def test_register_success(db_session: Session):
    """Test successful user registration"""
    # Override the get_db dependency
    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db

    response = client.post(
        "/auth/register",
        json={
            "email": "test@example.com",
            "password": VALID_PASSWORD
        }
    )

    assert response.status_code == 201
    data = response.json()
    assert "user_id" in data
    assert data["email"] == "test@example.com"
    assert "created_at" in data

    # Verify user was created in database
    user = db_session.query(User).filter(User.email == "test@example.com").first()
    assert user is not None
    assert user.email == "test@example.com"

    app.dependency_overrides.clear()

def test_register_duplicate_email(db_session: Session):
    """Test registration with duplicate email"""
    # Create a user first
    existing_user = User(
        email="duplicate@example.com",
        password_hash=hash_password(VALID_PASSWORD)
    )
    db_session.add(existing_user)
    db_session.commit()

    # Override the get_db dependency
    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db

    # Try to register with same email
    response = client.post(
        "/auth/register",
        json={
            "email": "duplicate@example.com",
            "password": VALID_PASSWORD
        }
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "DUPLICATE_EMAIL"
    assert "Email already registered" in response.json()["error"]["message"]

    app.dependency_overrides.clear()

def test_login_success(db_session: Session):
    """Test successful login"""
    # Create a user (verified — register flow now requires email verification
    # before login succeeds).
    user = User(
        email="login@example.com",
        password_hash=hash_password(VALID_PASSWORD),
        is_verified=True,
    )
    db_session.add(user)
    db_session.commit()

    # Override the get_db dependency
    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db

    # Login
    response = client.post(
        "/auth/login",
        json={
            "email": "login@example.com",
            "password": VALID_PASSWORD
        }
    )

    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"
    assert "expires_in" in data

    app.dependency_overrides.clear()

def test_login_invalid_email(db_session: Session):
    """Test login with invalid email"""
    # Override the get_db dependency
    def override_get_db():
        try:
            yield db_session
        finally:
            pass
    
    app.dependency_overrides[get_db] = override_get_db
    
    response = client.post(
        "/auth/login",
        json={
            "email": "nonexistent@example.com",
            "password": "password"
        }
    )
    
    assert response.status_code == 401
    assert "Invalid credentials" in response.json()["detail"]
    
    app.dependency_overrides.clear()

def test_login_invalid_password(db_session: Session):
    """Test login with invalid password"""
    # Create a user
    user = User(
        email="wrongpass@example.com",
        password_hash=hash_password(VALID_PASSWORD),
        is_verified=True,
    )
    db_session.add(user)
    db_session.commit()
    
    # Override the get_db dependency
    def override_get_db():
        try:
            yield db_session
        finally:
            pass
    
    app.dependency_overrides[get_db] = override_get_db
    
    # Try to login with wrong password
    response = client.post(
        "/auth/login",
        json={
            "email": "wrongpass@example.com",
            "password": "WrongPass1!"
        }
    )

    assert response.status_code == 401
    assert "Invalid credentials" in response.json()["detail"]
    
    app.dependency_overrides.clear()

def test_get_me_success(db_session: Session):
    """Test getting current user with valid token"""
    # Create a user
    user = User(
        email="getme@example.com",
        password_hash=hash_password(VALID_PASSWORD),
        is_verified=True,
    )
    db_session.add(user)
    db_session.commit()

    # Override the get_db dependency
    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db

    # Login to get token
    login_response = client.post(
        "/auth/login",
        json={
            "email": "getme@example.com",
            "password": VALID_PASSWORD
        }
    )
    token = login_response.json()["access_token"]
    
    # Get current user
    response = client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {token}"}
    )
    
    assert response.status_code == 200
    data = response.json()
    assert data["email"] == "getme@example.com"
    assert "user_id" in data
    assert "created_at" in data
    
    app.dependency_overrides.clear()

def test_get_me_no_token(db_session: Session):
    """Test getting current user without token"""
    # Override the get_db dependency
    def override_get_db():
        try:
            yield db_session
        finally:
            pass
    
    app.dependency_overrides[get_db] = override_get_db
    
    response = client.get("/auth/me")
    
    assert response.status_code == 403  # FastAPI returns 403 for missing credentials
    
    app.dependency_overrides.clear()

def test_get_me_invalid_token(db_session: Session):
    """Test getting current user with malformed token"""
    # Override the get_db dependency
    def override_get_db():
        try:
            yield db_session
        finally:
            pass
    
    app.dependency_overrides[get_db] = override_get_db
    
    response = client.get(
        "/auth/me",
        headers={"Authorization": "Bearer invalid_token_string"}
    )
    
    assert response.status_code == 401
    
    app.dependency_overrides.clear()

def test_get_me_expired_token(db_session: Session):
    """Test getting current user with expired token"""
    from datetime import datetime, timedelta
    from jose import jwt
    from app.config import settings
    
    # Create a user
    user = User(
        email="expired@example.com",
        password_hash=hash_password("password")
    )
    db_session.add(user)
    db_session.commit()
    
    # Create an expired token
    expired_payload = {
        "sub": str(user.id),
        "email": user.email,
        "exp": datetime.utcnow() - timedelta(hours=1),  # Expired 1 hour ago
        "iat": datetime.utcnow() - timedelta(hours=2)
    }
    expired_token = jwt.encode(expired_payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)
    
    # Override the get_db dependency
    def override_get_db():
        try:
            yield db_session
        finally:
            pass
    
    app.dependency_overrides[get_db] = override_get_db
    
    response = client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {expired_token}"}
    )
    
    assert response.status_code == 401
    
    app.dependency_overrides.clear()
