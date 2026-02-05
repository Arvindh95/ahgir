"""
Property-based tests for authentication service
"""
import pytest
from hypothesis import given, strategies as st, settings, HealthCheck
from datetime import datetime, timedelta
from jose import jwt, JWTError
import uuid

from app.auth import create_access_token, create_event_token, decode_token
from app.config import settings as app_settings

# Feature: picur, Property 6: JWT Token Expiration
@given(
    user_id=st.uuids(),
    email=st.emails(),
    expiration_seconds=st.integers(min_value=-3600, max_value=-1)  # Expired tokens (strictly past time)
)
@settings(max_examples=20, suppress_health_check=[HealthCheck.too_slow])
@pytest.mark.property_test
def test_jwt_token_expiration_admin(user_id, email, expiration_seconds):
    """
    Property 6: JWT Token Expiration
    
    For any JWT token (Admin or Event_Token), when the current time exceeds 
    the token's expiration time, the system SHALL reject the token and return 
    an authentication error.
    
    Validates: Requirements 1.3, 5.6
    """
    # Create an expired token by setting expiration in the past
    expires_delta = timedelta(seconds=expiration_seconds)
    
    # Manually create an expired token
    to_encode = {
        "sub": str(user_id),
        "email": email,
        "exp": datetime.utcnow() + expires_delta,
        "iat": datetime.utcnow() + expires_delta - timedelta(hours=1)
    }
    
    expired_token = jwt.encode(to_encode, app_settings.jwt_secret_key, algorithm=app_settings.jwt_algorithm)
    
    # Attempt to decode the expired token
    with pytest.raises(Exception) as exc_info:
        decode_token(expired_token)
    
    # Verify that an authentication error is raised
    assert exc_info.value.status_code == 401
    assert "invalid" in exc_info.value.message.lower()

# Feature: picur, Property 6: JWT Token Expiration (Event Tokens)
@given(
    event_id=st.uuids(),
    session_id=st.uuids(),
    expiration_seconds=st.integers(min_value=-3600, max_value=-1)  # Expired tokens (strictly past time)
)
@settings(max_examples=20, suppress_health_check=[HealthCheck.too_slow])
@pytest.mark.property_test
def test_event_token_expiration(event_id, session_id, expiration_seconds):
    """
    Property 6: JWT Token Expiration (Event Tokens)
    
    For any Event_Token, when the current time exceeds the token's expiration time,
    the system SHALL reject the token and return an authentication error.
    
    Validates: Requirements 1.3, 5.6
    """
    # Create an expired event token
    expires_delta = timedelta(seconds=expiration_seconds)
    
    # Manually create an expired event token
    to_encode = {
        "event_id": str(event_id),
        "session_id": str(session_id),
        "exp": datetime.utcnow() + expires_delta,
        "iat": datetime.utcnow() + expires_delta - timedelta(hours=1)
    }
    
    expired_token = jwt.encode(to_encode, app_settings.jwt_secret_key, algorithm=app_settings.jwt_algorithm)
    
    # Attempt to decode the expired token
    with pytest.raises(Exception) as exc_info:
        decode_token(expired_token)
    
    # Verify that an authentication error is raised
    assert exc_info.value.status_code == 401
    assert "invalid" in exc_info.value.message.lower()

# Additional property test: Valid tokens should not be rejected
@given(
    user_id=st.uuids(),
    email=st.emails(),
    expiration_hours=st.integers(min_value=1, max_value=48)  # Valid future expiration
)
@settings(max_examples=20, suppress_health_check=[HealthCheck.too_slow])
@pytest.mark.property_test
def test_valid_token_not_rejected(user_id, email, expiration_hours):
    """
    Property: Valid tokens with future expiration should be accepted
    
    For any JWT token with expiration time in the future, the system SHALL
    successfully decode and validate the token.
    """
    # Create a valid token with future expiration
    expires_delta = timedelta(hours=expiration_hours)
    token = create_access_token(
        data={"sub": str(user_id), "email": email},
        expires_delta=expires_delta
    )
    
    # Decode should succeed without raising an exception
    payload = decode_token(token)
    
    # Verify the payload contains expected data
    assert payload["sub"] == str(user_id)
    assert payload["email"] == email
    assert "exp" in payload
    assert "iat" in payload
