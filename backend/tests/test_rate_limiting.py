"""
Unit tests for rate limiting service.

Tests scan count tracking, limit enforcement, and window reset behavior.
"""

import pytest
from datetime import datetime, timedelta
import uuid
import os
import redis
from fastapi import HTTPException
from app.rate_limiter import RateLimiter
from app.config import settings

# Test Redis URL - use environment variable for host
REDIS_HOST = os.getenv("REDIS_HOST", "redis")
REDIS_PORT = os.getenv("REDIS_PORT", "6379")
TEST_REDIS_URL = f"redis://{REDIS_HOST}:{REDIS_PORT}/1"  # Use database 1 for tests
test_redis_client = redis.from_url(TEST_REDIS_URL, decode_responses=True)


@pytest.fixture
def rate_limiter():
    """Create a rate limiter instance for testing."""
    limiter = RateLimiter(
        redis_client=test_redis_client,
        limit=10,
        window_hours=1
    )
    yield limiter
    # Cleanup: flush test database
    test_redis_client.flushdb()


@pytest.fixture
def session_id():
    """Generate a test session ID."""
    return str(uuid.uuid4())


def test_scan_count_tracking(rate_limiter, session_id):
    """
    Test that scan counts are tracked correctly.
    
    Requirements: 10.1, 10.2
    """
    # Initially, count should be 0
    assert rate_limiter.get_current_count(session_id, "scan") == 0
    
    # Perform 5 scans
    for i in range(5):
        allowed, retry_after = rate_limiter.check_rate_limit(session_id, "scan")
        assert allowed is True
        assert retry_after is None
        assert rate_limiter.get_current_count(session_id, "scan") == i + 1
    
    # Count should be 5
    assert rate_limiter.get_current_count(session_id, "scan") == 5


def test_limit_enforcement(rate_limiter, session_id):
    """
    Test that rate limit is enforced at 10 scans per hour.
    
    Requirements: 10.1, 10.2
    """
    # Perform 10 scans (should all be allowed)
    for i in range(10):
        allowed, retry_after = rate_limiter.check_rate_limit(session_id, "scan")
        assert allowed is True
        assert retry_after is None
    
    # 11th scan should be denied
    allowed, retry_after = rate_limiter.check_rate_limit(session_id, "scan")
    assert allowed is False
    assert retry_after is not None
    assert retry_after > 0
    
    # Count should still be 10
    assert rate_limiter.get_current_count(session_id, "scan") == 10


def test_enforce_rate_limit_raises_exception(rate_limiter, session_id):
    """
    Test that enforce_rate_limit raises HTTPException when limit exceeded.
    
    Requirements: 10.1, 10.2
    """
    # Perform 10 scans
    for _ in range(10):
        rate_limiter.enforce_rate_limit(session_id, "scan")
    
    # 11th scan should raise HTTPException with 429 status
    with pytest.raises(HTTPException) as exc_info:
        rate_limiter.enforce_rate_limit(session_id, "scan")
    
    assert exc_info.value.status_code == 429
    assert "Rate limit exceeded" in exc_info.value.detail
    assert "Retry-After" in exc_info.value.headers
    
    # Verify Retry-After header is a positive integer
    retry_after = int(exc_info.value.headers["Retry-After"])
    assert retry_after > 0


def test_window_reset_behavior(rate_limiter, session_id):
    """
    Test that rate limit window resets correctly.
    
    Requirements: 10.1, 10.2
    """
    # Perform 10 scans
    for _ in range(10):
        allowed, _ = rate_limiter.check_rate_limit(session_id, "scan")
        assert allowed
    
    # Verify limit is reached
    allowed, retry_after = rate_limiter.check_rate_limit(session_id, "scan")
    assert not allowed
    assert retry_after is not None
    
    # Manually reset the limit (simulating window expiry)
    rate_limiter.reset_limit(session_id, "scan")
    
    # Now scans should be allowed again
    allowed, _ = rate_limiter.check_rate_limit(session_id, "scan")
    assert allowed
    
    # Count should be 1
    assert rate_limiter.get_current_count(session_id, "scan") == 1


def test_multiple_sessions_isolated(rate_limiter):
    """
    Test that rate limits are isolated per session.
    
    Requirements: 10.1, 10.2
    """
    session_1 = str(uuid.uuid4())
    session_2 = str(uuid.uuid4())
    
    # Fill up session 1
    for _ in range(10):
        allowed, _ = rate_limiter.check_rate_limit(session_1, "scan")
        assert allowed
    
    # Session 1 should be at limit
    allowed, _ = rate_limiter.check_rate_limit(session_1, "scan")
    assert not allowed
    
    # Session 2 should still be able to scan
    for _ in range(10):
        allowed, _ = rate_limiter.check_rate_limit(session_2, "scan")
        assert allowed
    
    # Verify counts
    assert rate_limiter.get_current_count(session_1, "scan") == 10
    assert rate_limiter.get_current_count(session_2, "scan") == 10


def test_different_actions_isolated(rate_limiter, session_id):
    """
    Test that different actions have separate rate limits.
    """
    # Perform 10 scans
    for _ in range(10):
        allowed, _ = rate_limiter.check_rate_limit(session_id, "scan")
        assert allowed
    
    # Scan action should be at limit
    allowed, _ = rate_limiter.check_rate_limit(session_id, "scan")
    assert not allowed
    
    # Different action should still be allowed
    allowed, _ = rate_limiter.check_rate_limit(session_id, "other_action")
    assert allowed
    
    # Verify counts are separate
    assert rate_limiter.get_current_count(session_id, "scan") == 10
    assert rate_limiter.get_current_count(session_id, "other_action") == 1


def test_redis_key_format(rate_limiter, session_id):
    """
    Test that Redis keys are formatted correctly.
    """
    key = rate_limiter._get_key(session_id, "scan")
    assert key == f"rate_limit:scan:{session_id}"
    
    key = rate_limiter._get_key(session_id, "other")
    assert key == f"rate_limit:other:{session_id}"


def test_retry_after_calculation(rate_limiter, session_id):
    """
    Test that retry-after is calculated correctly based on oldest timestamp.
    
    Requirements: 10.2
    """
    # Perform 10 scans
    for _ in range(10):
        rate_limiter.check_rate_limit(session_id, "scan")
    
    # Try one more scan
    allowed, retry_after = rate_limiter.check_rate_limit(session_id, "scan")
    assert not allowed
    assert retry_after is not None
    
    # Retry-after should be close to 1 hour (3600 seconds)
    # Allow some margin for test execution time
    assert 3500 <= retry_after <= 3600


def test_reset_limit(rate_limiter, session_id):
    """
    Test that reset_limit clears the rate limit for a session.
    """
    # Perform some scans
    for _ in range(5):
        rate_limiter.check_rate_limit(session_id, "scan")
    
    assert rate_limiter.get_current_count(session_id, "scan") == 5
    
    # Reset the limit
    rate_limiter.reset_limit(session_id, "scan")
    
    # Count should be 0
    assert rate_limiter.get_current_count(session_id, "scan") == 0


def test_custom_limit_and_window(session_id):
    """
    Test that custom limit and window values work correctly.
    """
    # Create rate limiter with custom values
    custom_limiter = RateLimiter(
        redis_client=test_redis_client,
        limit=5,
        window_hours=2
    )
    
    # Perform 5 scans (should all be allowed)
    for _ in range(5):
        allowed, _ = custom_limiter.check_rate_limit(session_id, "scan")
        assert allowed
    
    # 6th scan should be denied
    allowed, retry_after = custom_limiter.check_rate_limit(session_id, "scan")
    assert not allowed
    assert retry_after is not None
    
    # Cleanup
    custom_limiter.reset_limit(session_id, "scan")


def test_concurrent_scans_within_limit(rate_limiter, session_id):
    """
    Test that concurrent scans within limit are all allowed.
    
    Requirements: 10.1
    """
    # Simulate concurrent scans by checking limit multiple times
    results = []
    for _ in range(10):
        allowed, _ = rate_limiter.check_rate_limit(session_id, "scan")
        results.append(allowed)
    
    # All 10 should be allowed
    assert all(results)
    assert rate_limiter.get_current_count(session_id, "scan") == 10
