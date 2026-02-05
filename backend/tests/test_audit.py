"""
Unit tests for audit logging service
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
import uuid

from app.main import app
from app.database import get_db
from app.models import User, Event, AuditLog
from app.auth import hash_password, create_access_token
from app.audit import log_action
from datetime import timedelta

client = TestClient(app)


def test_log_action_admin(db_session: Session):
    """Test creating audit log for admin action"""
    # Create user and event
    user = User(
        email="admin@example.com",
        password_hash=hash_password("password")
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    
    event = Event(
        owner_user_id=user.id,
        slug="test-event",
        name="Test Event",
        allow_downloads=True,
        retention_days=90
    )
    db_session.add(event)
    db_session.commit()
    db_session.refresh(event)
    
    # Create audit log
    log = log_action(
        db=db_session,
        event_id=event.id,
        actor_type='admin',
        actor_id=user.id,
        action='upload',
        metadata={'photo_count': 5}
    )
    
    assert log.id is not None
    assert log.event_id == event.id
    assert log.actor_type == 'admin'
    assert log.actor_id == user.id
    assert log.action == 'upload'
    assert log.metadata_['photo_count'] == 5
    assert log.timestamp is not None


def test_log_action_guest(db_session: Session):
    """Test creating audit log for guest action"""
    # Create user and event
    user = User(
        email="owner@example.com",
        password_hash=hash_password("password")
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    
    event = Event(
        owner_user_id=user.id,
        slug="guest-event",
        name="Guest Event",
        allow_downloads=True,
        retention_days=90
    )
    db_session.add(event)
    db_session.commit()
    db_session.refresh(event)
    
    # Create audit log for guest
    session_id = uuid.uuid4()
    log = log_action(
        db=db_session,
        event_id=event.id,
        actor_type='guest',
        actor_id=session_id,
        action='scan',
        metadata={'match_count': 10, 'similarity_avg': 0.85}
    )
    
    assert log.id is not None
    assert log.event_id == event.id
    assert log.actor_type == 'guest'
    assert log.actor_id == session_id
    assert log.action == 'scan'
    assert log.metadata_['match_count'] == 10
    assert log.metadata_['similarity_avg'] == 0.85


def test_log_action_invalid_actor_type(db_session: Session):
    """Test that invalid actor_type raises error"""
    # Create user and event
    user = User(
        email="test@example.com",
        password_hash=hash_password("password")
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    
    event = Event(
        owner_user_id=user.id,
        slug="test-event",
        name="Test Event",
        allow_downloads=True,
        retention_days=90
    )
    db_session.add(event)
    db_session.commit()
    db_session.refresh(event)
    
    # Try to create log with invalid actor_type
    with pytest.raises(ValueError) as exc_info:
        log_action(
            db=db_session,
            event_id=event.id,
            actor_type='invalid',
            actor_id=user.id,
            action='test',
            metadata={}
        )
    
    assert "Invalid actor_type" in str(exc_info.value)


def test_query_audit_logs_success(db_session: Session):
    """Test querying audit logs for an event"""
    # Create user and event
    user = User(
        email="query@example.com",
        password_hash=hash_password("password")
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    
    event = Event(
        owner_user_id=user.id,
        slug="query-event",
        name="Query Event",
        allow_downloads=True,
        retention_days=90
    )
    db_session.add(event)
    db_session.commit()
    db_session.refresh(event)
    
    # Create multiple audit logs
    for i in range(5):
        log_action(
            db=db_session,
            event_id=event.id,
            actor_type='admin',
            actor_id=user.id,
            action='upload',
            metadata={'iteration': i}
        )
    
    # Override the get_db dependency
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
    
    # Query logs
    response = client.get(
        f"/events/{event.id}/logs",
        headers={"Authorization": f"Bearer {token}"}
    )
    
    assert response.status_code == 200
    data = response.json()
    assert data['total'] == 5
    assert len(data['logs']) == 5
    assert data['page'] == 1
    assert data['limit'] == 50
    
    # Verify log structure
    log = data['logs'][0]
    assert 'log_id' in log
    assert 'event_id' in log
    assert log['actor_type'] == 'admin'
    assert log['action'] == 'upload'
    assert 'metadata' in log
    assert 'timestamp' in log
    
    app.dependency_overrides.clear()


def test_query_audit_logs_with_filter(db_session: Session):
    """Test querying audit logs with action filter"""
    # Create user and event
    user = User(
        email="filter@example.com",
        password_hash=hash_password("password")
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    
    event = Event(
        owner_user_id=user.id,
        slug="filter-event",
        name="Filter Event",
        allow_downloads=True,
        retention_days=90
    )
    db_session.add(event)
    db_session.commit()
    db_session.refresh(event)
    
    # Create logs with different actions
    log_action(db=db_session, event_id=event.id, actor_type='admin', actor_id=user.id, action='upload', metadata={})
    log_action(db=db_session, event_id=event.id, actor_type='admin', actor_id=user.id, action='upload', metadata={})
    log_action(db=db_session, event_id=event.id, actor_type='admin', actor_id=user.id, action='reindex', metadata={})
    log_action(db=db_session, event_id=event.id, actor_type='guest', actor_id=uuid.uuid4(), action='scan', metadata={})
    
    # Override the get_db dependency
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
    
    # Query logs with filter
    response = client.get(
        f"/events/{event.id}/logs?action=upload",
        headers={"Authorization": f"Bearer {token}"}
    )
    
    assert response.status_code == 200
    data = response.json()
    assert data['total'] == 2
    assert len(data['logs']) == 2
    
    # Verify all returned logs have action='upload'
    for log in data['logs']:
        assert log['action'] == 'upload'
    
    app.dependency_overrides.clear()


def test_query_audit_logs_pagination(db_session: Session):
    """Test audit log pagination"""
    # Create user and event
    user = User(
        email="page@example.com",
        password_hash=hash_password("password")
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    
    event = Event(
        owner_user_id=user.id,
        slug="page-event",
        name="Page Event",
        allow_downloads=True,
        retention_days=90
    )
    db_session.add(event)
    db_session.commit()
    db_session.refresh(event)
    
    # Create 15 audit logs
    for i in range(15):
        log_action(
            db=db_session,
            event_id=event.id,
            actor_type='admin',
            actor_id=user.id,
            action='upload',
            metadata={'iteration': i}
        )
    
    # Override the get_db dependency
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
    
    # Query first page with limit 10
    response = client.get(
        f"/events/{event.id}/logs?page=1&limit=10",
        headers={"Authorization": f"Bearer {token}"}
    )
    
    assert response.status_code == 200
    data = response.json()
    assert data['total'] == 15
    assert len(data['logs']) == 10
    assert data['page'] == 1
    assert data['limit'] == 10
    
    # Query second page
    response = client.get(
        f"/events/{event.id}/logs?page=2&limit=10",
        headers={"Authorization": f"Bearer {token}"}
    )
    
    assert response.status_code == 200
    data = response.json()
    assert data['total'] == 15
    assert len(data['logs']) == 5
    assert data['page'] == 2
    
    app.dependency_overrides.clear()


def test_query_audit_logs_cross_tenant_prevention(db_session: Session):
    """Test that admins cannot access logs from other admins' events"""
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
    
    # Create event for user1
    event1 = Event(
        owner_user_id=user1.id,
        slug="user1-event",
        name="User1 Event",
        allow_downloads=True,
        retention_days=90
    )
    db_session.add(event1)
    db_session.commit()
    db_session.refresh(event1)
    
    # Create audit log for event1
    log_action(
        db=db_session,
        event_id=event1.id,
        actor_type='admin',
        actor_id=user1.id,
        action='upload',
        metadata={}
    )
    
    # Override the get_db dependency
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
    
    # Try to query logs for event1 as user2
    response = client.get(
        f"/events/{event1.id}/logs",
        headers={"Authorization": f"Bearer {token}"}
    )
    
    # Should return 403 Forbidden
    assert response.status_code == 403
    assert "permission" in response.json()["detail"].lower()
    
    app.dependency_overrides.clear()


def test_query_audit_logs_event_not_found(db_session: Session):
    """Test querying logs for non-existent event"""
    # Create user
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
    
    # Create token
    token = create_access_token(
        data={"sub": str(user.id), "email": user.email},
        expires_delta=timedelta(hours=1)
    )
    
    # Try to query logs for non-existent event
    fake_event_id = str(uuid.uuid4())
    response = client.get(
        f"/events/{fake_event_id}/logs",
        headers={"Authorization": f"Bearer {token}"}
    )
    
    # Should return 404 Not Found
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()
    
    app.dependency_overrides.clear()


def test_audit_log_created_on_event_creation(db_session: Session):
    """Test that audit log is created when event is created"""
    # Create user
    user = User(
        email="eventcreate@example.com",
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
    
    # Create token
    token = create_access_token(
        data={"sub": str(user.id), "email": user.email},
        expires_delta=timedelta(hours=1)
    )
    
    # Create event
    response = client.post(
        "/events",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "name": "Test Event",
            "allow_downloads": True,
            "retention_days": 90
        }
    )
    
    assert response.status_code == 201
    event_id = response.json()['event_id']
    
    # Check that audit log was created
    logs = db_session.query(AuditLog).filter(
        AuditLog.event_id == uuid.UUID(event_id),
        AuditLog.action == 'create_event'
    ).all()
    
    assert len(logs) == 1
    assert logs[0].actor_type == 'admin'
    assert logs[0].actor_id == user.id
    
    app.dependency_overrides.clear()
