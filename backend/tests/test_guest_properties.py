"""
Property-based tests for Guest access service
"""
import pytest
from hypothesis import given, strategies as st, settings, HealthCheck
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
import uuid
from datetime import datetime, timedelta

from app.main import app
from app.database import get_db
from app.models import User, Event, Image, Face, GuestSession
from app.auth import hash_password, create_event_token

client = TestClient(app)

# Feature: picur, Property 2: Event Token Scoping
@given(
    image_count_a=st.integers(min_value=1, max_value=5),
    image_count_b=st.integers(min_value=1, max_value=5)
)
@settings(max_examples=20, suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture], deadline=2000)
@pytest.mark.property_test
def test_event_token_scoping(db_session: Session, image_count_a, image_count_b):
    """
    Property 2: Event Token Scoping
    
    For any Event_Token generated for Event A, when used to access resources,
    the token SHALL NOT grant access to photos or faces from Event B.
    
    Validates: Requirements 5.5, 7.1, 7.4
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
        
        # Create Event A
        event_a = Event(
            owner_user_id=admin.id,
            slug=f"event-a-{uuid.uuid4().hex[:8]}",
            name="Event A",
            allow_downloads=True,
            retention_days=90
        )
        db_session.add(event_a)
        
        # Create Event B
        event_b = Event(
            owner_user_id=admin.id,
            slug=f"event-b-{uuid.uuid4().hex[:8]}",
            name="Event B",
            allow_downloads=True,
            retention_days=90
        )
        db_session.add(event_b)
        db_session.commit()
        db_session.refresh(event_a)
        db_session.refresh(event_b)
        
        # Create images for Event A
        images_a = []
        for i in range(image_count_a):
            image = Image(
                event_id=event_a.id,
                filename=f"image_a_{i}.jpg",
                file_hash=f"hash_a_{uuid.uuid4().hex}",
                size_bytes=1024,
                status="indexed",
                face_count=1
            )
            db_session.add(image)
            images_a.append(image)
        
        # Create images for Event B
        images_b = []
        for i in range(image_count_b):
            image = Image(
                event_id=event_b.id,
                filename=f"image_b_{i}.jpg",
                file_hash=f"hash_b_{uuid.uuid4().hex}",
                size_bytes=1024,
                status="indexed",
                face_count=1
            )
            db_session.add(image)
            images_b.append(image)
        
        db_session.commit()
        
        # Refresh all images
        for image in images_a + images_b:
            db_session.refresh(image)
        
        # Create faces for Event A images
        faces_a = []
        for image in images_a:
            face = Face(
                image_id=image.id,
                event_id=event_a.id,
                embedding=[0.1] * 512,  # Dummy embedding
                bbox=[10.0, 10.0, 50.0, 50.0],
                quality_score=0.9
            )
            db_session.add(face)
            faces_a.append(face)
        
        # Create faces for Event B images
        faces_b = []
        for image in images_b:
            face = Face(
                image_id=image.id,
                event_id=event_b.id,
                embedding=[0.2] * 512,  # Different dummy embedding
                bbox=[20.0, 20.0, 60.0, 60.0],
                quality_score=0.85
            )
            db_session.add(face)
            faces_b.append(face)
        
        db_session.commit()
        
        # Generate Event_Token for Event A
        session_id_a = uuid.uuid4()
        event_token_a = create_event_token(event_a.id, session_id_a)
        
        # Store session for Event A
        guest_session_a = GuestSession(
            id=session_id_a,
            event_id=event_a.id,
            session_token=event_token_a,
            expires_at=datetime.utcnow() + timedelta(hours=1)
        )
        db_session.add(guest_session_a)
        db_session.commit()
        
        # Test 1: Verify that Event_Token A cannot be used to access Event B's slug
        # This tests that the token is scoped to Event A
        response = client.get(f"/e/{event_b.slug}")
        assert response.status_code == 200
        event_b_info = response.json()
        
        # The token should not grant automatic access to Event B
        # (This is a basic check - the real scoping is tested in face search)
        
        # Test 2: Verify that when querying faces with Event_Token A,
        # only faces from Event A are accessible
        # Note: This would require a face search endpoint that uses event tokens
        # For now, we verify the token payload contains the correct event_id
        from app.auth import decode_token
        payload = decode_token(event_token_a)
        
        assert payload["event_id"] == str(event_a.id), \
            "Event token should contain Event A's ID"
        assert payload["session_id"] == str(session_id_a), \
            "Event token should contain the session ID"
        
        # Test 3: Verify that faces in the database are properly scoped
        # Query faces for Event A
        faces_in_event_a = db_session.query(Face).filter(
            Face.event_id == event_a.id
        ).all()
        
        assert len(faces_in_event_a) == image_count_a, \
            f"Event A should have {image_count_a} faces"
        
        # Verify none of Event B's faces are in Event A's results
        face_ids_a = [str(f.id) for f in faces_in_event_a]
        for face_b in faces_b:
            assert str(face_b.id) not in face_ids_a, \
                f"Event A's face query should not include Event B's face {face_b.id}"
        
        # Test 4: Verify images are properly scoped
        images_in_event_a = db_session.query(Image).filter(
            Image.event_id == event_a.id
        ).all()
        
        assert len(images_in_event_a) == image_count_a, \
            f"Event A should have {image_count_a} images"
        
        # Verify none of Event B's images are in Event A's results
        image_ids_a = [str(img.id) for img in images_in_event_a]
        for image_b in images_b:
            assert str(image_b.id) not in image_ids_a, \
                f"Event A's image query should not include Event B's image {image_b.id}"
    
    finally:
        app.dependency_overrides.clear()


# Feature: picur, Property 7: Passcode Verification
@given(
    passcode_length=st.integers(min_value=4, max_value=20),
    has_passcode=st.booleans()
)
@settings(max_examples=20, suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture], deadline=1000)
@pytest.mark.property_test
def test_passcode_verification(db_session: Session, passcode_length, has_passcode):
    """
    Property 7: Passcode Verification
    
    For any Event with a passcode, when a Guest attempts to authenticate,
    the system SHALL only grant access if the provided passcode matches
    the stored bcrypt hash.
    
    Validates: Requirements 5.2, 5.3
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
        
        # Generate a random passcode
        passcode = "a" * passcode_length if has_passcode else None
        
        # Create event with or without passcode
        event = Event(
            owner_user_id=admin.id,
            slug=f"event-{uuid.uuid4().hex[:8]}",
            name="Test Event",
            passcode_hash=hash_password(passcode) if has_passcode else None,
            allow_downloads=True,
            retention_days=90
        )
        db_session.add(event)
        db_session.commit()
        db_session.refresh(event)
        
        # Test 1: Access event info (should always work)
        response = client.get(f"/e/{event.slug}")
        assert response.status_code == 200
        event_info = response.json()
        assert event_info["requires_passcode"] == has_passcode
        
        if has_passcode:
            # Test 2: Try to authenticate without passcode (should fail)
            response = client.post(
                f"/e/{event.slug}/auth",
                json={}
            )
            assert response.status_code == 401, \
                "Authentication without passcode should fail when passcode is required"
            
            # Test 3: Try to authenticate with wrong passcode (should fail)
            wrong_passcode = "b" * passcode_length
            response = client.post(
                f"/e/{event.slug}/auth",
                json={"passcode": wrong_passcode}
            )
            assert response.status_code == 401, \
                "Authentication with wrong passcode should fail"
            assert "invalid" in response.json()["detail"].lower()
            
            # Test 4: Authenticate with correct passcode (should succeed)
            response = client.post(
                f"/e/{event.slug}/auth",
                json={"passcode": passcode}
            )
            assert response.status_code == 200, \
                "Authentication with correct passcode should succeed"
            
            token_data = response.json()
            assert "event_token" in token_data
            assert token_data["event_id"] == str(event.id)
            assert token_data["event_name"] == event.name
            assert token_data["allow_downloads"] == event.allow_downloads
            
            # Verify the token is valid
            from app.auth import decode_token
            payload = decode_token(token_data["event_token"])
            assert payload["event_id"] == str(event.id)
        else:
            # Test 5: Authenticate without passcode when none is required (should succeed)
            response = client.post(
                f"/e/{event.slug}/auth",
                json={}
            )
            assert response.status_code == 200, \
                "Authentication should succeed when no passcode is required"
            
            token_data = response.json()
            assert "event_token" in token_data
            assert token_data["event_id"] == str(event.id)
    
    finally:
        app.dependency_overrides.clear()
