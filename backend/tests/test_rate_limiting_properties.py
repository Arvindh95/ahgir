"""
Property-based tests for rate limiting service.

Tests Property 8: Rate Limit Enforcement
"""

import pytest
from hypothesis import given, strategies as st, settings, assume
from datetime import datetime, timedelta
import uuid
import redis
import os
from app.rate_limiter import RateLimiter
from app.config import settings as app_settings

# Test Redis client - use environment variables or default to Docker container names
REDIS_HOST = os.getenv("REDIS_HOST", "redis")
REDIS_PORT = os.getenv("REDIS_PORT", "6379")
TEST_REDIS_URL = f"redis://{REDIS_HOST}:{REDIS_PORT}/1"


@pytest.fixture
def rate_limiter():
    """Create a rate limiter instance for testing."""
    # Create Redis client lazily to avoid connection issues at module load
    redis_client = redis.from_url(TEST_REDIS_URL, decode_responses=True)
    limiter = RateLimiter(
        redis_client=redis_client,
        limit=10,
        window_hours=1
    )
    yield limiter
    # Cleanup: flush test database
    redis_client.flushdb()
    redis_client.close()


# Feature: picur, Property 8: Rate Limit Enforcement
@given(
    scan_count=st.integers(min_value=1, max_value=20),
    session_id=st.uuids()
)
@settings(max_examples=20, deadline=None)
@pytest.mark.property_test
def test_rate_limit_enforcement_property(rate_limiter, scan_count, session_id):
    """
    Property 8: Rate Limit Enforcement
    
    For any Guest session, when the number of face scans within a 1-hour window 
    exceeds 10, the system SHALL reject subsequent scan requests with a 429 error 
    until the window resets.
    
    Validates: Requirements 10.1, 10.2
    """
    # Reset rate limit for this session
    rate_limiter.reset_limit(str(session_id), action="scan")
    
    # Perform scans up to scan_count
    allowed_count = 0
    denied_count = 0
    
    for i in range(scan_count):
        allowed, retry_after = rate_limiter.check_rate_limit(str(session_id), action="scan")
        
        if allowed:
            allowed_count += 1
        else:
            denied_count += 1
            # Verify retry_after is provided when denied
            assert retry_after is not None
            assert retry_after > 0
    
    # Property: If scan_count <= 10, all should be allowed
    if scan_count <= 10:
        assert allowed_count == scan_count
        assert denied_count == 0
    
    # Property: If scan_count > 10, exactly 10 should be allowed, rest denied
    if scan_count > 10:
        assert allowed_count == 10
        assert denied_count == scan_count - 10
    
    # Verify current count matches allowed count
    current_count = rate_limiter.get_current_count(str(session_id), action="scan")
    assert current_count == min(scan_count, 10)
    
    # Cleanup
    rate_limiter.reset_limit(str(session_id), action="scan")


@given(
    session_id_1=st.uuids(),
    session_id_2=st.uuids(),
    scans_1=st.integers(min_value=1, max_value=15),
    scans_2=st.integers(min_value=1, max_value=15)
)
@settings(max_examples=20, deadline=None)
@pytest.mark.property_test
def test_rate_limit_isolation_property(rate_limiter, session_id_1, session_id_2, scans_1, scans_2):
    """
    Property: Rate limits are isolated per session.
    
    For any two different sessions, the rate limit of one session SHALL NOT 
    affect the rate limit of another session.
    """
    # Ensure sessions are different
    assume(session_id_1 != session_id_2)
    
    # Reset both sessions
    rate_limiter.reset_limit(str(session_id_1), action="scan")
    rate_limiter.reset_limit(str(session_id_2), action="scan")
    
    # Perform scans for session 1
    for _ in range(min(scans_1, 10)):
        allowed, _ = rate_limiter.check_rate_limit(str(session_id_1), action="scan")
        assert allowed
    
    # Perform scans for session 2
    for _ in range(min(scans_2, 10)):
        allowed, _ = rate_limiter.check_rate_limit(str(session_id_2), action="scan")
        assert allowed
    
    # Verify counts are independent
    count_1 = rate_limiter.get_current_count(str(session_id_1), action="scan")
    count_2 = rate_limiter.get_current_count(str(session_id_2), action="scan")
    
    assert count_1 == min(scans_1, 10)
    assert count_2 == min(scans_2, 10)
    
    # Cleanup
    rate_limiter.reset_limit(str(session_id_1), action="scan")
    rate_limiter.reset_limit(str(session_id_2), action="scan")


@given(
    session_id=st.uuids()
)
@settings(max_examples=20, deadline=None)
@pytest.mark.property_test
def test_rate_limit_window_reset_property(rate_limiter, session_id):
    """
    Property: Rate limit window resets after expiry.
    
    When timestamps older than the window are removed, the count SHALL decrease 
    accordingly, allowing new scans.
    """
    # Reset session
    rate_limiter.reset_limit(str(session_id), action="scan")
    
    # Fill up the rate limit (10 scans)
    for _ in range(10):
        allowed, _ = rate_limiter.check_rate_limit(str(session_id), action="scan")
        assert allowed
    
    # Verify limit is reached
    allowed, retry_after = rate_limiter.check_rate_limit(str(session_id), action="scan")
    assert not allowed
    assert retry_after is not None
    
    # Manually manipulate Redis to simulate time passing
    # Remove all timestamps (simulating window expiry)
    key = rate_limiter._get_key(str(session_id), "scan")
    rate_limiter.redis.delete(key)
    
    # Now scans should be allowed again
    allowed, _ = rate_limiter.check_rate_limit(str(session_id), action="scan")
    assert allowed
    
    # Cleanup
    rate_limiter.reset_limit(str(session_id), action="scan")
