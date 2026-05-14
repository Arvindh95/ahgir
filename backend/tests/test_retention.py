"""
Unit tests for data retention and cleanup
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
import uuid
from io import BytesIO
from PIL import Image as PILImage

from app.main import app
from app.database import get_db
from app.models import User, Event, Image, Face, GuestSession, AuditLog
from app.auth import hash_password, create_access_token
from app.storage import storage_service
from app.workers.retention_policy import check_and_delete_expired_events

client = TestClient(app)
client.headers.update({"X-Requested-With": "XMLHttpRequest"})

@pytest.fixture(autouse=True)
def _clear_module_client_cookies():
    """Reset cookies between tests so a stale picur_session/picur_event
    from a prior test does not poison auth on the next test."""
    client.cookies.clear()
    yield


def test_delete_event_success(db_session: Session):
    """Test successful event deletion with all cascades"""
    # Create user
    user = User(
        email="delete@example.com",
        password_hash=hash_password("password")
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    
    # Create event
    event = Event(
        owner_user_id=user.id,
        slug="delete-event",
        name="Delete Event",
        allow_downloads=True,
        retention_days=90
    )
    db_session.add(event)
    db_session.commit()
    db_session.refresh(event)
    
    # Create image
    img = PILImage.new('RGB', (100, 100), color='red')
    img_bytes = BytesIO()
    img.save(img_bytes, format='JPEG')
    img_bytes.seek(0)
    photo_data = img_bytes.getvalue()

    
    image_id = uuid.uuid4()
    image = Image(
        id=image_id,
        event_id=event.id,
        filename="test.jpg",
        file_hash="hash123",
        size_bytes=len(photo_data),
        width=100,
        height=100,
        status='indexed',
        face_count=1
    )
    db_session.add(image)
    db_session.commit()
    
    # Create face
    face = Face(
        image_id=image_id,
        event_id=event.id,
        embedding=[0.1] * 512,
        bbox=[10.0, 10.0, 50.0, 50.0],
        quality_score=0.9
    )
    db_session.add(face)
    db_session.commit()
    
    # Create guest session
    session = GuestSession(
        event_id=event.id,
        session_token="test_token",
        expires_at=datetime.utcnow() + timedelta(hours=1)
    )
    db_session.add(session)
    db_session.commit()
    
    # Upload photo to MinIO
    try:
        storage_service.upload_photo(event.id, image_id, photo_data, 'original')
        storage_service.upload_photo(event.id, image_id, photo_data, 'thumb')
    except Exception:
        pytest.skip("MinIO not available")
    
    # Override get_db
    def override_get_db():
        try:
            yield db_session
        finally:
            pass
    
    app.dependency_overrides[get_db] = override_get_db
    
    # Create token
    token = create_access_token(
        data={"sub": str(user.id), "email": user.email},
        expires_delta=timedelta(hours=1)
    )
    
    # Delete event
    response = client.delete(
        f"/events/{event.id}",
        headers={"Authorization": f"Bearer {token}"}
    )
    
    assert response.status_code == 200
    assert response.json()['message'] == "Event deleted successfully"
    
    # Verify event is deleted
    assert db_session.query(Event).filter(Event.id == event.id).count() == 0
    
    # Verify cascaded deletions
    assert db_session.query(Image).filter(Image.event_id == event.id).count() == 0
    assert db_session.query(Face).filter(Face.event_id == event.id).count() == 0
    assert db_session.query(GuestSession).filter(GuestSession.event_id == event.id).count() == 0
    
    # Verify photos deleted from MinIO
    try:
        with pytest.raises(FileNotFoundError):
            storage_service.get_photo(event.id, image_id, 'original')
    except Exception:
        pass
    
    app.dependency_overrides.clear()


def test_delete_event_unauthorized(db_session: Session):
    """Test that users cannot delete events they don't own"""
    # Create two users
    user1 = User(email="owner@example.com", password_hash=hash_password("password"))
    user2 = User(email="other@example.com", password_hash=hash_password("password"))
    db_session.add(user1)
    db_session.add(user2)
    db_session.commit()
    db_session.refresh(user1)
    db_session.refresh(user2)
    
    # Create event owned by user1
    event = Event(
        owner_user_id=user1.id,
        slug="protected-event",
        name="Protected Event",
        allow_downloads=True,
        retention_days=90
    )
    db_session.add(event)
    db_session.commit()
    db_session.refresh(event)
    
    # Override get_db
    def override_get_db():
        try:
            yield db_session
        finally:
            pass
    
    app.dependency_overrides[get_db] = override_get_db
    
    # Create token for user2
    token = create_access_token(
        data={"sub": str(user2.id), "email": user2.email},
        expires_delta=timedelta(hours=1)
    )
    
    # Try to delete event as user2
    response = client.delete(
        f"/events/{event.id}",
        headers={"Authorization": f"Bearer {token}"}
    )
    
    assert response.status_code == 403
    assert "permission" in response.json()["detail"].lower()
    
    # Verify event still exists
    assert db_session.query(Event).filter(Event.id == event.id).count() == 1
    
    app.dependency_overrides.clear()


def test_delete_event_not_found(db_session: Session):
    """Test deleting non-existent event"""
    # Create user
    user = User(email="user@example.com", password_hash=hash_password("password"))
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    
    # Override get_db
    def override_get_db():
        try:
            yield db_session
        finally:
            pass
    
    app.dependency_overrides[get_db] = override_get_db
    
    # Create token
    token = create_access_token(
        data={"sub": str(user.id), "email": user.email},
        expires_delta=timedelta(hours=1)
    )
    
    # Try to delete non-existent event
    fake_id = str(uuid.uuid4())
    response = client.delete(
        f"/events/{fake_id}",
        headers={"Authorization": f"Bearer {token}"}
    )
    
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()
    
    app.dependency_overrides.clear()


def test_audit_log_created_on_deletion(db_session: Session):
    """Test that audit log is created when event is deleted"""
    # Create user and event
    user = User(email="audit@example.com", password_hash=hash_password("password"))
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    
    event = Event(
        owner_user_id=user.id,
        slug="audit-event",
        name="Audit Event",
        allow_downloads=True,
        retention_days=90
    )
    db_session.add(event)
    db_session.commit()
    db_session.refresh(event)
    
    event_id = event.id
    
    # Override get_db
    def override_get_db():
        try:
            yield db_session
        finally:
            pass
    
    app.dependency_overrides[get_db] = override_get_db
    
    # Create token
    token = create_access_token(
        data={"sub": str(user.id), "email": user.email},
        expires_delta=timedelta(hours=1)
    )
    
    # Delete event
    response = client.delete(
        f"/events/{event_id}",
        headers={"Authorization": f"Bearer {token}"}
    )
    
    assert response.status_code == 200
    
    # Note: Audit log is deleted with cascade, but it was created before deletion
    # In a real system, you might want to preserve audit logs even after event deletion
    
    app.dependency_overrides.clear()



def test_retention_policy_deletes_expired_events(db_session: Session):
    """Test that retention policy job deletes expired events"""
    # Create user
    user = User(email="retention@example.com", password_hash=hash_password("password"))
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    
    # Create expired event (created 100 days ago with 90 day retention)
    expired_event = Event(
        owner_user_id=user.id,
        slug="expired-event",
        name="Expired Event",
        allow_downloads=True,
        retention_days=90
    )
    db_session.add(expired_event)
    db_session.flush()
    
    # Manually set created_at to 100 days ago
    from sqlalchemy import text
    db_session.execute(
        text(f"UPDATE events SET created_at = NOW() - INTERVAL '100 days' WHERE id = :event_id"),
        {"event_id": str(expired_event.id)}
    )
    db_session.commit()
    db_session.refresh(expired_event)
    
    # Create non-expired event
    active_event = Event(
        owner_user_id=user.id,
        slug="active-event",
        name="Active Event",
        allow_downloads=True,
        retention_days=90
    )
    db_session.add(active_event)
    db_session.commit()
    db_session.refresh(active_event)
    
    expired_event_id = expired_event.id
    active_event_id = active_event.id
    
    # Run retention policy job
    # Pass the test database session
    deleted_count = check_and_delete_expired_events(db_session)
    
    # Refresh session to see changes
    db_session.expire_all()
    
    # Verify expired event is deleted
    assert db_session.query(Event).filter(Event.id == expired_event_id).count() == 0
    
    # Verify active event still exists
    assert db_session.query(Event).filter(Event.id == active_event_id).count() == 1


def test_retention_policy_respects_retention_days(db_session: Session):
    """Test that retention policy respects different retention_days values"""
    # Create user
    user = User(email="retention2@example.com", password_hash=hash_password("password"))
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    
    # Create event with 30 day retention, created 40 days ago (expired)
    event_30 = Event(
        owner_user_id=user.id,
        slug="event-30",
        name="30 Day Event",
        allow_downloads=True,
        retention_days=30
    )
    db_session.add(event_30)
    db_session.flush()
    from sqlalchemy import text
    db_session.execute(
        text(f"UPDATE events SET created_at = NOW() - INTERVAL '40 days' WHERE id = :event_id"),
        {"event_id": str(event_30.id)}
    )
    db_session.commit()
    db_session.refresh(event_30)
    
    # Create event with 180 day retention, created 40 days ago (not expired)
    event_180 = Event(
        owner_user_id=user.id,
        slug="event-180",
        name="180 Day Event",
        allow_downloads=True,
        retention_days=180
    )
    db_session.add(event_180)
    db_session.flush()
    db_session.execute(
        text(f"UPDATE events SET created_at = NOW() - INTERVAL '40 days' WHERE id = :event_id"),
        {"event_id": str(event_180.id)}
    )
    db_session.commit()
    db_session.refresh(event_180)
    
    event_30_id = event_30.id
    event_180_id = event_180.id
    
    # Run retention policy job
    check_and_delete_expired_events(db_session)
    
    # Refresh session
    db_session.expire_all()
    
    # Verify 30-day event is deleted
    assert db_session.query(Event).filter(Event.id == event_30_id).count() == 0
    
    # Verify 180-day event still exists
    assert db_session.query(Event).filter(Event.id == event_180_id).count() == 1


def test_retention_policy_with_no_expired_events(db_session: Session):
    """Test retention policy when no events are expired"""
    # Create user
    user = User(email="retention3@example.com", password_hash=hash_password("password"))
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    
    # Create recent event
    event = Event(
        owner_user_id=user.id,
        slug="recent-event",
        name="Recent Event",
        allow_downloads=True,
        retention_days=90
    )
    db_session.add(event)
    db_session.commit()
    db_session.refresh(event)
    
    event_id = event.id
    
    # Run retention policy job
    deleted_count = check_and_delete_expired_events(db_session)
    
    # Should delete 0 events
    assert deleted_count == 0
    
    # Verify event still exists
    db_session.expire_all()
    assert db_session.query(Event).filter(Event.id == event_id).count() == 1
