"""
Endpoint coverage for POST /auth/reset-password.

The security review flagged the original suite for missing:
- reset-token type discrimination (an access token must not unlock reset)
- token expiry handling
- single-use enforcement (replay protection)
- old access-token invalidation after a password reset
- the read/check/write race when two concurrent requests share one token

These tests close those gaps.
"""
import time
import uuid
from datetime import datetime, timedelta
from threading import Thread

import pytest
from jose import jwt
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.auth import (
    hash_password,
    verify_password,
    create_access_token,
    create_password_reset_token,
    create_verification_token,
    get_current_user,
)
from app.config import settings
from app.database import get_db
from app.main import app
from app.models import User


client = TestClient(app)
client.headers.update({"X-Requested-With": "XMLHttpRequest"})

@pytest.fixture(autouse=True)
def _clear_module_client_cookies():
    """Reset cookies between tests so a stale picur_session/picur_event
    from a prior test does not poison auth on the next test."""
    client.cookies.clear()
    yield

VALID_PASSWORD = "SecurePass1!"
NEW_PASSWORD = "BrandNewPass2@"


def _override_db(db_session: Session):
    def _get():
        try:
            yield db_session
        finally:
            pass
    app.dependency_overrides[get_db] = _get


def _make_user(db_session: Session, email: str = "reset@example.com") -> User:
    u = User(email=email, password_hash=hash_password(VALID_PASSWORD), is_verified=True)
    db_session.add(u)
    db_session.commit()
    db_session.refresh(u)
    return u


def test_reset_password_success(db_session: Session):
    """A fresh, well-typed reset token successfully rotates the password."""
    user = _make_user(db_session)
    _override_db(db_session)

    token = create_password_reset_token(user.id)
    response = client.post(
        "/auth/reset-password",
        json={"token": token, "new_password": NEW_PASSWORD},
    )

    assert response.status_code == 200, response.text
    db_session.refresh(user)
    assert verify_password(NEW_PASSWORD, user.password_hash)
    assert user.password_changed_at is not None

    app.dependency_overrides.clear()


def test_reset_password_rejects_access_token(db_session: Session):
    """An access token must NOT be usable as a reset token (type discrimination)."""
    user = _make_user(db_session, email="reset-access@example.com")
    _override_db(db_session)

    # Forge by issuing an access token for this user. type='access', not 'password_reset'.
    access_token = create_access_token({"sub": str(user.id), "email": user.email})
    response = client.post(
        "/auth/reset-password",
        json={"token": access_token, "new_password": NEW_PASSWORD},
    )

    assert response.status_code == 401, response.text
    db_session.refresh(user)
    # Password must be untouched.
    assert verify_password(VALID_PASSWORD, user.password_hash)

    app.dependency_overrides.clear()


def test_reset_password_rejects_verify_token(db_session: Session):
    """A verification token must not be usable as a reset token."""
    user = _make_user(db_session, email="reset-verify@example.com")
    _override_db(db_session)

    verify_token = create_verification_token(user.id)
    response = client.post(
        "/auth/reset-password",
        json={"token": verify_token, "new_password": NEW_PASSWORD},
    )

    assert response.status_code == 401, response.text
    app.dependency_overrides.clear()


def test_reset_password_rejects_expired_token(db_session: Session):
    """An expired reset token must be rejected with 401."""
    user = _make_user(db_session, email="reset-expired@example.com")
    _override_db(db_session)

    # Hand-craft an already-expired reset token.
    payload = {
        "sub": str(user.id),
        "type": "password_reset",
        "iat": datetime.utcnow() - timedelta(hours=2),
        "exp": datetime.utcnow() - timedelta(hours=1),
    }
    expired_token = jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)

    response = client.post(
        "/auth/reset-password",
        json={"token": expired_token, "new_password": NEW_PASSWORD},
    )

    assert response.status_code == 401, response.text
    db_session.refresh(user)
    assert verify_password(VALID_PASSWORD, user.password_hash)

    app.dependency_overrides.clear()


def test_reset_password_single_use_replay_rejected(db_session: Session):
    """Reusing a reset token that already succeeded must be rejected as single-use."""
    user = _make_user(db_session, email="reset-replay@example.com")
    _override_db(db_session)

    token = create_password_reset_token(user.id)
    # First use should succeed.
    first = client.post(
        "/auth/reset-password",
        json={"token": token, "new_password": NEW_PASSWORD},
    )
    assert first.status_code == 200, first.text

    # Sleep 1s so the second-attempt's "now" is strictly after the first reset's
    # password_changed_at, even on filesystems with 1s-granularity clocks.
    time.sleep(1.1)

    # Replay with the same token — must be rejected because token_iat predates
    # the freshly-written password_changed_at.
    second = client.post(
        "/auth/reset-password",
        json={"token": token, "new_password": "AnotherPass3#"},
    )
    assert second.status_code == 401, second.text

    db_session.refresh(user)
    assert verify_password(NEW_PASSWORD, user.password_hash)
    assert not verify_password("AnotherPass3#", user.password_hash)

    app.dependency_overrides.clear()


def test_reset_password_invalidates_old_access_token(db_session: Session):
    """Access tokens issued BEFORE the password reset must stop authenticating."""
    user = _make_user(db_session, email="reset-invalidate@example.com")
    _override_db(db_session)

    # Issue an access token now, then sleep so the subsequent reset has a
    # strictly-later password_changed_at.
    old_access = create_access_token({"sub": str(user.id), "email": user.email})
    time.sleep(1.1)

    reset_token = create_password_reset_token(user.id)
    r1 = client.post(
        "/auth/reset-password",
        json={"token": reset_token, "new_password": NEW_PASSWORD},
    )
    assert r1.status_code == 200, r1.text

    # /auth/me must reject the pre-reset access token. The exact status depends on
    # how invalid-token errors surface in this codebase — accept anything in the
    # 401/403 family.
    me = client.get("/auth/me", headers={"Authorization": f"Bearer {old_access}"})
    assert me.status_code in (401, 403), me.text

    app.dependency_overrides.clear()


def test_reset_password_invalid_signature(db_session: Session):
    """A token with the right shape but wrong signature must be rejected."""
    user = _make_user(db_session, email="reset-bad-sig@example.com")
    _override_db(db_session)

    payload = {
        "sub": str(user.id),
        "type": "password_reset",
        "iat": datetime.utcnow(),
        "exp": datetime.utcnow() + timedelta(hours=1),
    }
    bogus_token = jwt.encode(payload, "wrong-secret-not-the-real-one", algorithm=settings.jwt_algorithm)
    response = client.post(
        "/auth/reset-password",
        json={"token": bogus_token, "new_password": NEW_PASSWORD},
    )
    assert response.status_code == 401, response.text

    app.dependency_overrides.clear()


def test_reset_password_concurrent_uses_serialize(engine, tables):
    """Two parallel reset attempts with the same valid token must produce one
    success and one rejection — not two successes.

    This guards the race fix where the user row is SELECT ... FOR UPDATE-locked
    before the password_changed_at check. Without the lock, both transactions
    can pass the check before either commits, so the second password would
    overwrite the first.

    NB: This test does NOT use the shared db_session fixture, because that
    fixture wraps everything in a single rollback-on-teardown transaction —
    SELECT FOR UPDATE within one transaction is a no-op against itself, so
    the race becomes unobservable. Instead we create a fresh sessionmaker
    bound to the real engine and override get_db to hand each request its
    own session/transaction. We also clean up the test user manually.
    """
    from sqlalchemy.orm import sessionmaker
    TestSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    # Seed the user via its own session and commit.
    setup_session = TestSession()
    try:
        existing = setup_session.query(User).filter(User.email == "reset-race@example.com").first()
        if existing:
            setup_session.delete(existing)
            setup_session.commit()
        user = User(
            email="reset-race@example.com",
            password_hash=hash_password(VALID_PASSWORD),
            is_verified=True,
        )
        setup_session.add(user)
        setup_session.commit()
        setup_session.refresh(user)
        user_id = user.id
    finally:
        setup_session.close()

    # Per-request session so each /auth/reset-password call gets its own tx.
    def per_request_get_db():
        s = TestSession()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = per_request_get_db

    try:
        token = create_password_reset_token(user_id)
        results = []

        def attempt(pw: str):
            r = client.post(
                "/auth/reset-password",
                json={"token": token, "new_password": pw},
            )
            results.append((r.status_code, pw))

        t1 = Thread(target=attempt, args=("FirstWinPass1!",))
        t2 = Thread(target=attempt, args=("SecondWinPass2@",))
        t1.start(); t2.start(); t1.join(); t2.join()

        successes = [s for s in results if s[0] == 200]
        rejections = [s for s in results if s[0] != 200]
        assert len(successes) == 1, f"expected exactly 1 success, got {results}"
        assert len(rejections) == 1, f"expected exactly 1 rejection, got {results}"

        verify_session = TestSession()
        try:
            after = verify_session.query(User).filter(User.id == user_id).first()
            winning_pw = successes[0][1]
            assert verify_password(winning_pw, after.password_hash)
        finally:
            verify_session.close()
    finally:
        # Hand-roll cleanup so this test does not leak the test user into
        # subsequent runs (we are bypassing the rollback-wrapped fixture).
        cleanup_session = TestSession()
        try:
            row = cleanup_session.query(User).filter(User.id == user_id).first()
            if row:
                cleanup_session.delete(row)
                cleanup_session.commit()
        finally:
            cleanup_session.close()

        app.dependency_overrides.clear()


def test_reset_password_weak_password_rejected(db_session: Session):
    """The reset endpoint must enforce the same password policy as register."""
    user = _make_user(db_session, email="reset-weak@example.com")
    _override_db(db_session)

    token = create_password_reset_token(user.id)
    response = client.post(
        "/auth/reset-password",
        json={"token": token, "new_password": "weak"},
    )
    assert response.status_code == 400, response.text
    # Original password must still work.
    db_session.refresh(user)
    assert verify_password(VALID_PASSWORD, user.password_hash)

    app.dependency_overrides.clear()
