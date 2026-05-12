"""
Integration tests for rate limiting through the API.

Tests rate limiting enforcement on the /scan endpoint.
"""

import pytest
import base64
import uuid
from datetime import datetime, timedelta
from app.models import User, Event, Image, Face, GuestSession
from app.auth import hash_password, create_event_token
from app.rate_limiter import rate_limiter
import numpy as np


# The integration tests assume a 10-scan-per-hour budget so they finish quickly
# without bumping into production's 30/hour ceiling.
_TEST_SCAN_LIMIT = 10


@pytest.fixture(autouse=True)
def scan_limit_override():
    """Pin scan_rate_limiter to a small, deterministic budget for these tests."""
    original_limit = rate_limiter.limit
    original_window = rate_limiter.window_hours
    rate_limiter.limit = _TEST_SCAN_LIMIT
    rate_limiter.window_hours = 1
    try:
        yield
    finally:
        rate_limiter.limit = original_limit
        rate_limiter.window_hours = original_window


@pytest.fixture
def admin_user(test_db):
    """Create an admin user for testing."""
    user = User(
        email=f"admin_{uuid.uuid4()}@test.com",
        password_hash=hash_password("password123"),
    )
    test_db.add(user)
    test_db.commit()
    test_db.refresh(user)
    return user


@pytest.fixture
def test_event(test_db, admin_user):
    """Create a test event."""
    event = Event(
        owner_user_id=admin_user.id,
        slug=f"test-event-rate-{uuid.uuid4().hex[:8]}",
        name="Test Event",
        allow_downloads=True,
        retention_days=90,
    )
    test_db.add(event)
    test_db.commit()
    test_db.refresh(event)
    return event


@pytest.fixture
def guest_session(test_db, test_event):
    """Create a guest session for testing."""
    session_id = uuid.uuid4()
    event_token = create_event_token(test_event.id, session_id)
    
    session = GuestSession(
        id=session_id,
        event_id=test_event.id,
        session_token=event_token,
        expires_at=datetime.utcnow() + timedelta(hours=1)
    )
    test_db.add(session)
    test_db.commit()
    test_db.refresh(session)
    
    # Reset rate limit for this session
    rate_limiter.reset_limit(str(session_id), "scan")
    
    return session


@pytest.fixture
def test_image_with_face(test_db, test_event):
    """Create a test image with a face for matching."""
    image = Image(
        event_id=test_event.id,
        filename="test.jpg",
        file_hash=f"hash_{uuid.uuid4().hex}",
        size_bytes=1024,
        status="indexed",
        face_count=1,
    )
    test_db.add(image)
    test_db.commit()
    test_db.refresh(image)

    face = Face(
        image_id=image.id,
        event_id=test_event.id,
        bbox=[100.0, 100.0, 200.0, 200.0],
        quality_score=0.95,
        embedding=[0.0] * 512,
        compreface_subject_id=f"{test_event.id}/{image.id}",
    )
    test_db.add(face)
    test_db.commit()

    return image


def test_rate_limit_on_scan_endpoint(client, guest_session, test_image_with_face):
    """
    Test that rate limiting is enforced on the /scan endpoint.
    
    Requirements: 10.1, 10.2
    """
    # Create a dummy base64 image (1x1 pixel)
    dummy_image = base64.b64encode(b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89').decode()
    
    headers = {"Authorization": f"Bearer {guest_session.session_token}"}
    
    # Perform 10 scans (should all succeed or fail with face detection, but not rate limit)
    for i in range(10):
        response = client.post(
            "/scan",
            json={"image": dummy_image},
            headers=headers
        )
        # Should not be rate limited (status 200 or 400 for face detection, but not 429)
        assert response.status_code in [200, 400], f"Scan {i+1} failed with unexpected status: {response.status_code}"
    
    # 11th scan should be rate limited
    response = client.post(
        "/scan",
        json={"image": dummy_image},
        headers=headers
    )
    
    assert response.status_code == 429
    assert "Rate limit exceeded" in response.json()["detail"]
    assert "Retry-After" in response.headers
    
    # Verify Retry-After header
    retry_after = int(response.headers["Retry-After"])
    assert retry_after > 0


def test_rate_limit_reset_allows_new_scans(client, guest_session, test_image_with_face):
    """
    Test that resetting rate limit allows new scans.
    
    Requirements: 10.1, 10.2
    """
    dummy_image = base64.b64encode(b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89').decode()
    headers = {"Authorization": f"Bearer {guest_session.session_token}"}
    
    # Fill up rate limit
    for _ in range(10):
        client.post("/scan", json={"image": dummy_image}, headers=headers)
    
    # Verify rate limit is reached
    response = client.post("/scan", json={"image": dummy_image}, headers=headers)
    assert response.status_code == 429
    
    # Reset rate limit
    rate_limiter.reset_limit(str(guest_session.id), "scan")
    
    # Now scan should work again
    response = client.post("/scan", json={"image": dummy_image}, headers=headers)
    assert response.status_code in [200, 400]  # Not rate limited


def test_different_sessions_have_separate_limits(client, test_db, test_event, test_image_with_face):
    """
    Test that different guest sessions have separate rate limits.
    
    Requirements: 10.1, 10.2
    """
    # Create two guest sessions
    session_1_id = uuid.uuid4()
    session_2_id = uuid.uuid4()
    
    token_1 = create_event_token(test_event.id, session_1_id)
    token_2 = create_event_token(test_event.id, session_2_id)
    
    session_1 = GuestSession(
        id=session_1_id,
        event_id=test_event.id,
        session_token=token_1,
        expires_at=datetime.utcnow() + timedelta(hours=1)
    )
    session_2 = GuestSession(
        id=session_2_id,
        event_id=test_event.id,
        session_token=token_2,
        expires_at=datetime.utcnow() + timedelta(hours=1)
    )
    
    test_db.add(session_1)
    test_db.add(session_2)
    test_db.commit()
    
    # Reset rate limits
    rate_limiter.reset_limit(str(session_1_id), "scan")
    rate_limiter.reset_limit(str(session_2_id), "scan")
    
    dummy_image = base64.b64encode(b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89').decode()
    
    # Fill up session 1
    headers_1 = {"Authorization": f"Bearer {token_1}"}
    for _ in range(10):
        client.post("/scan", json={"image": dummy_image}, headers=headers_1)
    
    # Session 1 should be rate limited
    response = client.post("/scan", json={"image": dummy_image}, headers=headers_1)
    assert response.status_code == 429
    
    # Session 2 should still be able to scan
    headers_2 = {"Authorization": f"Bearer {token_2}"}
    response = client.post("/scan", json={"image": dummy_image}, headers=headers_2)
    assert response.status_code in [200, 400]  # Not rate limited


def test_rate_limit_error_message_format(client, guest_session):
    """
    Test that rate limit error message has correct format.
    
    Requirements: 10.2
    """
    dummy_image = base64.b64encode(b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89').decode()
    headers = {"Authorization": f"Bearer {guest_session.session_token}"}
    
    # Fill up rate limit
    for _ in range(10):
        client.post("/scan", json={"image": dummy_image}, headers=headers)
    
    # Get rate limit error
    response = client.post("/scan", json={"image": dummy_image}, headers=headers)
    
    assert response.status_code == 429
    
    # Check error format
    error_data = response.json()
    assert "detail" in error_data
    assert "Rate limit exceeded" in error_data["detail"]
    assert "10" in error_data["detail"]  # Mentions the limit
    assert "hour" in error_data["detail"].lower()  # Mentions the window
    
    # Check Retry-After header
    assert "Retry-After" in response.headers
    retry_after = int(response.headers["Retry-After"])
    assert 0 < retry_after <= 3600  # Should be within 1 hour
