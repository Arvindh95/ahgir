"""
Unit tests for Event management service
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from datetime import date
import uuid

from app.main import app
from app.database import get_db
from app.models import User, Event, UserTier
from app.auth import hash_password, create_access_token
from app.routers.events import normalize_public_slug

client = TestClient(app)
client.headers.update({"X-Requested-With": "XMLHttpRequest"})

@pytest.fixture(autouse=True)
def _clear_module_client_cookies():
    """Reset cookies between tests so a stale picur_session/picur_event
    from a prior test does not poison auth on the next test."""
    client.cookies.clear()
    yield


def test_normalize_public_slug_rejects_route_breaking_values():
    """Slug normalization keeps public event URLs route-safe."""
    assert normalize_public_slug("  Smith Wedding 2026  ") == "smith-wedding-2026"
    assert normalize_public_slug("Cafe Reception") == "cafe-reception"

    with pytest.raises(ValueError):
        normalize_public_slug("***")

    with pytest.raises(ValueError):
        normalize_public_slug("a" * 256)


def _attach_pro_tier(db_session, user):
    """Helper: give a test user a Pro UserTier so they can create multiple
    events with longer retention than the free tier permits.

    Free tier caps active_events=1, retention=30 days. Tests creating 2+
    events or asserting retention >= 90 days need a paid tier.
    """
    db_session.add(UserTier(
        user_id=user.id,
        tier_name="pro",
        max_events=20,
        max_photos_per_event=2000,
        retention_days=365,
        price_cents=9900,
        is_active=True,
    ))
    db_session.commit()

def test_create_event_success(db_session: Session):
    """Test successful event creation with all fields"""
    # Create a user
    user = User(
        email="eventowner@example.com",
        password_hash=hash_password("password")
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    _attach_pro_tier(db_session, user)

    # Override the get_db dependency
    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db

    # Generate token
    token = create_access_token(
        data={"sub": str(user.id), "email": user.email}
    )

    # Create event
    response = client.post(
        "/events",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "name": "Smith Wedding",
            "date": "2024-06-15",
            "passcode": "secret123",
            "allow_downloads": True,
            "retention_days": 90
        }
    )
    
    assert response.status_code == 201
    data = response.json()
    assert "event_id" in data
    assert "slug" in data
    assert data["name"] == "Smith Wedding"
    assert data["date"] == "2024-06-15"
    assert "guest_link" in data
    assert "qr_code_url" in data
    assert data["owner_user_id"] == str(user.id)
    assert data["allow_downloads"] is True
    assert data["retention_days"] == 90
    
    # Verify event was created in database
    event = db_session.query(Event).filter(Event.slug == data["slug"]).first()
    assert event is not None
    assert event.name == "Smith Wedding"
    assert event.owner_user_id == user.id
    assert event.passcode_hash is not None  # Passcode should be hashed
    
    app.dependency_overrides.clear()

def test_create_event_minimal_fields(db_session: Session):
    """Test event creation with only required fields"""
    # Create a user
    user = User(
        email="minimal@example.com",
        password_hash=hash_password("password")
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    _attach_pro_tier(db_session, user)

    # Override the get_db dependency
    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db

    # Generate token
    token = create_access_token(
        data={"sub": str(user.id), "email": user.email}
    )

    # Create event with minimal fields
    response = client.post(
        "/events",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "name": "Simple Event"
        }
    )
    
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Simple Event"
    assert data["date"] is None
    assert data["allow_downloads"] is True  # Default value
    assert data["retention_days"] == 90  # Default value
    
    app.dependency_overrides.clear()

def test_create_event_slug_uniqueness(db_session: Session):
    """Test that slugs are unique even for events with same name"""
    # Create a user
    user = User(
        email="slugtest@example.com",
        password_hash=hash_password("password")
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    _attach_pro_tier(db_session, user)

    # Override the get_db dependency
    def override_get_db():
        try:
            yield db_session
        finally:
            pass
    
    app.dependency_overrides[get_db] = override_get_db
    
    # Generate token
    token = create_access_token(
        data={"sub": str(user.id), "email": user.email}
    )
    
    # Create first event
    response1 = client.post(
        "/events",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "Duplicate Name"}
    )
    
    # Create second event with same name
    response2 = client.post(
        "/events",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "Duplicate Name"}
    )
    
    assert response1.status_code == 201
    assert response2.status_code == 201
    
    slug1 = response1.json()["slug"]
    slug2 = response2.json()["slug"]
    
    # Slugs should be different
    assert slug1 != slug2
    
    app.dependency_overrides.clear()

def test_create_event_no_auth(db_session: Session):
    """Test event creation without authentication"""
    # Override the get_db dependency
    def override_get_db():
        try:
            yield db_session
        finally:
            pass
    
    app.dependency_overrides[get_db] = override_get_db
    
    # Try to create event without token
    response = client.post(
        "/events",
        json={"name": "Unauthorized Event"}
    )
    
    # Cookie-auth dependency raises InvalidTokenError(401) for missing creds.
    # Previously HTTPBearer's auto-error returned 403; this is the correct
    # HTTP semantic.
    assert response.status_code == 401
    
    app.dependency_overrides.clear()

def test_list_events_ownership_filtering(db_session: Session):
    """Test that list events only returns events owned by the current user"""
    # Create two users
    user1 = User(
        email="user1@example.com",
        password_hash=hash_password("password")
    )
    user2 = User(
        email="user2@example.com",
        password_hash=hash_password("password")
    )
    db_session.add(user1)
    db_session.add(user2)
    db_session.commit()
    db_session.refresh(user1)
    db_session.refresh(user2)
    
    # Create events for user1
    event1 = Event(
        owner_user_id=user1.id,
        slug=f"user1-event1-{uuid.uuid4().hex[:6]}",
        name="User 1 Event 1",
        allow_downloads=True,
        retention_days=90
    )
    event2 = Event(
        owner_user_id=user1.id,
        slug=f"user1-event2-{uuid.uuid4().hex[:6]}",
        name="User 1 Event 2",
        allow_downloads=True,
        retention_days=90
    )
    
    # Create event for user2
    event3 = Event(
        owner_user_id=user2.id,
        slug=f"user2-event1-{uuid.uuid4().hex[:6]}",
        name="User 2 Event 1",
        allow_downloads=True,
        retention_days=90
    )
    
    db_session.add(event1)
    db_session.add(event2)
    db_session.add(event3)
    db_session.commit()
    
    # Override the get_db dependency
    def override_get_db():
        try:
            yield db_session
        finally:
            pass
    
    app.dependency_overrides[get_db] = override_get_db
    
    # Generate token for user1
    token1 = create_access_token(
        data={"sub": str(user1.id), "email": user1.email}
    )
    
    # List events as user1
    response = client.get(
        "/events",
        headers={"Authorization": f"Bearer {token1}"}
    )
    
    assert response.status_code == 200
    data = response.json()
    event_ids = [e["event_id"] for e in data["events"]]
    
    # Should only see user1's events
    assert str(event1.id) in event_ids
    assert str(event2.id) in event_ids
    assert str(event3.id) not in event_ids
    assert len(data["events"]) == 2
    
    app.dependency_overrides.clear()

def test_get_event_success(db_session: Session):
    """Test getting event details with ownership validation"""
    # Create a user
    user = User(
        email="getevent@example.com",
        password_hash=hash_password("password")
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    
    # Create an event
    event = Event(
        owner_user_id=user.id,
        slug=f"test-event-{uuid.uuid4().hex[:6]}",
        name="Test Event",
        date=date(2024, 6, 15),
        allow_downloads=True,
        retention_days=90
    )
    db_session.add(event)
    db_session.commit()
    db_session.refresh(event)
    
    # Override the get_db dependency
    def override_get_db():
        try:
            yield db_session
        finally:
            pass
    
    app.dependency_overrides[get_db] = override_get_db
    
    # Generate token
    token = create_access_token(
        data={"sub": str(user.id), "email": user.email}
    )
    
    # Get event details
    response = client.get(
        f"/events/{event.id}",
        headers={"Authorization": f"Bearer {token}"}
    )
    
    assert response.status_code == 200
    data = response.json()
    assert data["event_id"] == str(event.id)
    assert data["name"] == "Test Event"
    assert data["slug"] == event.slug
    assert data["date"] == "2024-06-15"
    assert "status" in data
    assert data["status"]["total_photos"] == 0  # No photos yet
    
    app.dependency_overrides.clear()

def test_get_event_not_owned(db_session: Session):
    """Test that users cannot access events they don't own"""
    # Create two users
    user1 = User(
        email="owner@example.com",
        password_hash=hash_password("password")
    )
    user2 = User(
        email="notowner@example.com",
        password_hash=hash_password("password")
    )
    db_session.add(user1)
    db_session.add(user2)
    db_session.commit()
    db_session.refresh(user1)
    db_session.refresh(user2)
    
    # Create event owned by user1
    event = Event(
        owner_user_id=user1.id,
        slug=f"private-event-{uuid.uuid4().hex[:6]}",
        name="Private Event",
        allow_downloads=True,
        retention_days=90
    )
    db_session.add(event)
    db_session.commit()
    db_session.refresh(event)
    
    # Override the get_db dependency
    def override_get_db():
        try:
            yield db_session
        finally:
            pass
    
    app.dependency_overrides[get_db] = override_get_db
    
    # Generate token for user2
    token2 = create_access_token(
        data={"sub": str(user2.id), "email": user2.email}
    )
    
    # Try to access user1's event as user2
    response = client.get(
        f"/events/{event.id}",
        headers={"Authorization": f"Bearer {token2}"}
    )
    
    assert response.status_code == 403
    assert "permission" in response.json()["detail"].lower()
    
    app.dependency_overrides.clear()

def test_get_event_not_found(db_session: Session):
    """Test getting non-existent event"""
    # Create a user
    user = User(
        email="notfound@example.com",
        password_hash=hash_password("password")
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    
    # Override the get_db dependency
    def override_get_db():
        try:
            yield db_session
        finally:
            pass
    
    app.dependency_overrides[get_db] = override_get_db
    
    # Generate token
    token = create_access_token(
        data={"sub": str(user.id), "email": user.email}
    )
    
    # Try to get non-existent event
    fake_id = str(uuid.uuid4())
    response = client.get(
        f"/events/{fake_id}",
        headers={"Authorization": f"Bearer {token}"}
    )
    
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()
    
    app.dependency_overrides.clear()

def test_get_qr_code_success(db_session: Session):
    """Test getting QR code for event"""
    # Create a user
    user = User(
        email="qrcode@example.com",
        password_hash=hash_password("password")
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    
    # Create an event
    event = Event(
        owner_user_id=user.id,
        slug=f"qr-event-{uuid.uuid4().hex[:6]}",
        name="QR Event",
        allow_downloads=True,
        retention_days=90
    )
    db_session.add(event)
    db_session.commit()
    db_session.refresh(event)
    
    # Override the get_db dependency
    def override_get_db():
        try:
            yield db_session
        finally:
            pass
    
    app.dependency_overrides[get_db] = override_get_db
    
    # Generate token
    token = create_access_token(
        data={"sub": str(user.id), "email": user.email}
    )
    
    # Get QR code
    response = client.get(
        f"/events/{event.id}/qr",
        headers={"Authorization": f"Bearer {token}"}
    )
    
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"
    assert len(response.content) > 0  # Should have image data
    
    app.dependency_overrides.clear()

def test_get_qr_code_not_owned(db_session: Session):
    """Test that users cannot get QR code for events they don't own"""
    # Create two users
    user1 = User(
        email="qrowner@example.com",
        password_hash=hash_password("password")
    )
    user2 = User(
        email="qrnotowner@example.com",
        password_hash=hash_password("password")
    )
    db_session.add(user1)
    db_session.add(user2)
    db_session.commit()
    db_session.refresh(user1)
    db_session.refresh(user2)
    
    # Create event owned by user1
    event = Event(
        owner_user_id=user1.id,
        slug=f"qr-private-{uuid.uuid4().hex[:6]}",
        name="QR Private Event",
        allow_downloads=True,
        retention_days=90
    )
    db_session.add(event)
    db_session.commit()
    db_session.refresh(event)
    
    # Override the get_db dependency
    def override_get_db():
        try:
            yield db_session
        finally:
            pass
    
    app.dependency_overrides[get_db] = override_get_db
    
    # Generate token for user2
    token2 = create_access_token(
        data={"sub": str(user2.id), "email": user2.email}
    )
    
    # Try to get QR code for user1's event as user2
    response = client.get(
        f"/events/{event.id}/qr",
        headers={"Authorization": f"Bearer {token2}"}
    )
    
    assert response.status_code == 403
    assert "permission" in response.json()["detail"].lower()
    
    app.dependency_overrides.clear()
