"""
Unit tests for Guest access service
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
import uuid

from app.main import app
from app.database import get_db
from app.models import User, Event
from app.auth import hash_password, decode_token

client = TestClient(app)


def test_get_event_by_valid_slug(db_session: Session):
    """
    Test Event access with valid slug
    
    Requirements: 5.1
    """
    # Override the get_db dependency
    def override_get_db():
        try:
            yield db_session
        finally:
            pass
    
    app.dependency_overrides[get_db] = override_get_db
    
    try:
        # Create an admin user
        admin = User(
            email=f"admin_{uuid.uuid4()}@example.com",
            password_hash=hash_password("password")
        )
        db_session.add(admin)
        db_session.commit()
        db_session.refresh(admin)
        
        # Create an event without passcode
        event = Event(
            owner_user_id=admin.id,
            slug="test-wedding-2024",
            name="Test Wedding",
            allow_downloads=True,
            retention_days=90
        )
        db_session.add(event)
        db_session.commit()
        db_session.refresh(event)
        
        # Access event by slug
        response = client.get(f"/e/{event.slug}")
        
        assert response.status_code == 200
        data = response.json()
        assert data["event_id"] == str(event.id)
        assert data["name"] == "Test Wedding"
        assert data["date"] is None
        assert data["requires_passcode"] is False
    
    finally:
        app.dependency_overrides.clear()


def test_get_event_by_invalid_slug(db_session: Session):
    """
    Test Event access with invalid slug
    
    Requirements: 5.1
    """
    # Override the get_db dependency
    def override_get_db():
        try:
            yield db_session
        finally:
            pass
    
    app.dependency_overrides[get_db] = override_get_db
    
    try:
        # Try to access non-existent event
        response = client.get("/e/non-existent-slug")
        
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()
    
    finally:
        app.dependency_overrides.clear()


def test_passcode_verification_success(db_session: Session):
    """
    Test passcode verification success
    
    Requirements: 5.2, 5.3
    """
    # Override the get_db dependency
    def override_get_db():
        try:
            yield db_session
        finally:
            pass
    
    app.dependency_overrides[get_db] = override_get_db
    
    try:
        # Create an admin user
        admin = User(
            email=f"admin_{uuid.uuid4()}@example.com",
            password_hash=hash_password("password")
        )
        db_session.add(admin)
        db_session.commit()
        db_session.refresh(admin)
        
        # Create an event with passcode
        passcode = "secret123"
        event = Event(
            owner_user_id=admin.id,
            slug="protected-wedding",
            name="Protected Wedding",
            passcode_hash=hash_password(passcode),
            allow_downloads=True,
            retention_days=90
        )
        db_session.add(event)
        db_session.commit()
        db_session.refresh(event)
        
        # Authenticate with correct passcode
        response = client.post(
            f"/e/{event.slug}/auth",
            json={"passcode": passcode}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "event_token" in data
        assert data["event_id"] == str(event.id)
        assert data["event_name"] == "Protected Wedding"
        assert data["allow_downloads"] is True
        assert data["expires_in"] == 3600
        
        # Verify token is valid
        payload = decode_token(data["event_token"])
        assert payload["event_id"] == str(event.id)
        assert "session_id" in payload
    
    finally:
        app.dependency_overrides.clear()


def test_passcode_verification_failure(db_session: Session):
    """
    Test passcode verification failure
    
    Requirements: 5.2, 5.3
    """
    # Override the get_db dependency
    def override_get_db():
        try:
            yield db_session
        finally:
            pass
    
    app.dependency_overrides[get_db] = override_get_db
    
    try:
        # Create an admin user
        admin = User(
            email=f"admin_{uuid.uuid4()}@example.com",
            password_hash=hash_password("password")
        )
        db_session.add(admin)
        db_session.commit()
        db_session.refresh(admin)
        
        # Create an event with passcode
        passcode = "secret123"
        event = Event(
            owner_user_id=admin.id,
            slug="protected-wedding-2",
            name="Protected Wedding 2",
            passcode_hash=hash_password(passcode),
            allow_downloads=True,
            retention_days=90
        )
        db_session.add(event)
        db_session.commit()
        db_session.refresh(event)
        
        # Try to authenticate with wrong passcode
        response = client.post(
            f"/e/{event.slug}/auth",
            json={"passcode": "wrongpasscode"}
        )
        
        assert response.status_code == 401
        assert "invalid" in response.json()["detail"].lower()
        
        # Try to authenticate without passcode
        response = client.post(
            f"/e/{event.slug}/auth",
            json={}
        )
        
        assert response.status_code == 401
        assert "required" in response.json()["detail"].lower()
    
    finally:
        app.dependency_overrides.clear()


def test_event_token_generation(db_session: Session):
    """
    Test Event_Token generation
    
    Requirements: 5.4
    """
    # Override the get_db dependency
    def override_get_db():
        try:
            yield db_session
        finally:
            pass
    
    app.dependency_overrides[get_db] = override_get_db
    
    try:
        # Create an admin user
        admin = User(
            email=f"admin_{uuid.uuid4()}@example.com",
            password_hash=hash_password("password")
        )
        db_session.add(admin)
        db_session.commit()
        db_session.refresh(admin)
        
        # Create an event without passcode
        event = Event(
            owner_user_id=admin.id,
            slug="open-wedding",
            name="Open Wedding",
            allow_downloads=False,
            retention_days=90
        )
        db_session.add(event)
        db_session.commit()
        db_session.refresh(event)
        
        # Authenticate without passcode
        response = client.post(
            f"/e/{event.slug}/auth",
            json={}
        )
        
        assert response.status_code == 200
        data = response.json()
        
        # Verify token structure
        assert "event_token" in data
        assert data["event_id"] == str(event.id)
        assert data["event_name"] == "Open Wedding"
        assert data["allow_downloads"] is False
        assert data["expires_in"] == 3600
        
        # Decode and verify token payload
        payload = decode_token(data["event_token"])
        assert payload["event_id"] == str(event.id)
        assert "session_id" in payload
        assert "exp" in payload
        assert "iat" in payload
        
        # Verify session was created in database
        from app.models import GuestSession
        session = db_session.query(GuestSession).filter(
            GuestSession.session_token == data["event_token"]
        ).first()
        
        assert session is not None
        assert session.event_id == event.id
        assert str(session.id) == payload["session_id"]
    
    finally:
        app.dependency_overrides.clear()


def test_event_with_passcode_requires_passcode_flag(db_session: Session):
    """
    Test that events with passcode have requires_passcode flag set correctly
    
    Requirements: 5.1, 5.2
    """
    # Override the get_db dependency
    def override_get_db():
        try:
            yield db_session
        finally:
            pass
    
    app.dependency_overrides[get_db] = override_get_db
    
    try:
        # Create an admin user
        admin = User(
            email=f"admin_{uuid.uuid4()}@example.com",
            password_hash=hash_password("password")
        )
        db_session.add(admin)
        db_session.commit()
        db_session.refresh(admin)
        
        # Create an event with passcode
        event = Event(
            owner_user_id=admin.id,
            slug="protected-event",
            name="Protected Event",
            passcode_hash=hash_password("mypasscode"),
            allow_downloads=True,
            retention_days=90
        )
        db_session.add(event)
        db_session.commit()
        db_session.refresh(event)
        
        # Access event info
        response = client.get(f"/e/{event.slug}")
        
        assert response.status_code == 200
        data = response.json()
        assert data["requires_passcode"] is True
    
    finally:
        app.dependency_overrides.clear()
