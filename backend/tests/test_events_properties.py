"""
Property-based tests for Event management service
"""
import pytest
from hypothesis import given, strategies as st, settings, HealthCheck
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
import uuid

from app.main import app
from app.database import get_db
from app.models import User, Event
from app.auth import hash_password, create_access_token

client = TestClient(app)
client.headers.update({"X-Requested-With": "XMLHttpRequest"})

@pytest.fixture(autouse=True)
def _clear_module_client_cookies():
    """Reset cookies between tests so a stale picur_session/picur_event
    from a prior test does not poison auth on the next test."""
    client.cookies.clear()
    yield

# Feature: picur, Property 1: Admin Isolation
@given(
    event_count_a=st.integers(min_value=1, max_value=5),
    event_count_b=st.integers(min_value=1, max_value=5)
)
@settings(max_examples=20, suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture], deadline=1000)
@pytest.mark.property_test
def test_admin_isolation(db_session: Session, event_count_a, event_count_b):
    """
    Property 1: Admin Isolation
    
    For any two Admin accounts with different user_ids, when Admin A queries 
    their Events, the results SHALL NOT include any Events owned by Admin B.
    
    Validates: Requirements 1.4, 1.5, 7.5
    """
    # Override the get_db dependency
    def override_get_db():
        try:
            yield db_session
        finally:
            pass
    
    app.dependency_overrides[get_db] = override_get_db
    
    try:
        # Create two different admin users
        admin_a = User(
            email=f"admin_a_{uuid.uuid4()}@example.com",
            password_hash=hash_password("password")
        )
        admin_b = User(
            email=f"admin_b_{uuid.uuid4()}@example.com",
            password_hash=hash_password("password")
        )
        db_session.add(admin_a)
        db_session.add(admin_b)
        db_session.commit()
        db_session.refresh(admin_a)
        db_session.refresh(admin_b)
        
        # Create events for Admin A
        events_a = []
        for i in range(event_count_a):
            event = Event(
                owner_user_id=admin_a.id,
                slug=f"event-a-{uuid.uuid4().hex[:8]}",
                name=f"Event A {i}",
                allow_downloads=True,
                retention_days=90
            )
            db_session.add(event)
            events_a.append(event)
        
        # Create events for Admin B
        events_b = []
        for i in range(event_count_b):
            event = Event(
                owner_user_id=admin_b.id,
                slug=f"event-b-{uuid.uuid4().hex[:8]}",
                name=f"Event B {i}",
                allow_downloads=True,
                retention_days=90
            )
            db_session.add(event)
            events_b.append(event)
        
        db_session.commit()
        
        # Refresh all events to get their IDs
        for event in events_a + events_b:
            db_session.refresh(event)
        
        # Generate JWT token for Admin A
        token_a = create_access_token(
            data={"sub": str(admin_a.id), "email": admin_a.email}
        )
        
        # Query events as Admin A
        response = client.get(
            "/events",
            headers={"Authorization": f"Bearer {token_a}"}
        )
        
        assert response.status_code == 200
        data = response.json()
        returned_event_ids = [e["event_id"] for e in data["events"]]
        
        # Verify Admin A only sees their events
        for event in events_a:
            assert str(event.id) in returned_event_ids, \
                f"Admin A should see their own event {event.id}"
        
        # Verify Admin A does NOT see Admin B's events
        for event in events_b:
            assert str(event.id) not in returned_event_ids, \
                f"Admin A should NOT see Admin B's event {event.id}"
        
        # Verify the count matches
        assert len(returned_event_ids) == event_count_a, \
            f"Admin A should see exactly {event_count_a} events, got {len(returned_event_ids)}"
        
        # Also test that Admin A cannot access Admin B's event details
        if events_b:
            event_b_id = str(events_b[0].id)
            response = client.get(
                f"/events/{event_b_id}",
                headers={"Authorization": f"Bearer {token_a}"}
            )
            
            # Should return 403 Forbidden
            assert response.status_code == 403, \
                "Admin A should not be able to access Admin B's event details"
            assert "permission" in response.json()["detail"].lower()
    
    finally:
        app.dependency_overrides.clear()
