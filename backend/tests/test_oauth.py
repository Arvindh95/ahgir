"""Tests for Google OAuth sign-in (app/routers/oauth.py).

The Google network calls (code→token exchange, id_token verification) are
monkeypatched — these tests cover OUR logic: state/CSRF handling, find-or-create
with auto-link, the disabled-account block, and the verify_password NULL guard.
Emails/subs are unique per test so committed rows can't collide across tests.
"""
import uuid

import pytest
from sqlalchemy.orm import Session

from app.routers import oauth
from app.config import settings
from app.models import User, UserTier
from app.auth import verify_password, hash_password, OAUTH_STATE_COOKIE, SESSION_COOKIE

VALID_PASSWORD = "SecurePass1!"


def _uniq_email() -> str:
    return f"oauth-{uuid.uuid4().hex}@example.com"


def _uniq_sub() -> str:
    return f"sub-{uuid.uuid4().hex}"


@pytest.fixture
def enabled_oauth(monkeypatch):
    """Flip Google OAuth on by giving settings a client id + secret."""
    monkeypatch.setattr(settings, "google_client_id", "test-client-id.apps.googleusercontent.com")
    monkeypatch.setattr(settings, "google_client_secret", "test-secret")
    return settings


def _patch_google(monkeypatch, *, sub: str, email: str, email_verified: bool = True):
    """Stub the token exchange + id_token verification for a callback test."""
    class _FakeResp:
        def raise_for_status(self):
            return None

        def json(self):
            return {"id_token": "fake.jwt.token", "access_token": "fake-access"}

    monkeypatch.setattr(oauth.httpx, "post", lambda *a, **k: _FakeResp())
    monkeypatch.setattr(
        oauth.google_id_token,
        "verify_oauth2_token",
        lambda *a, **k: {"sub": sub, "email": email, "email_verified": email_verified},
    )


# ---------------------------------------------------------------------------
# verify_password NULL guard (OAuth-only accounts have no password)
# ---------------------------------------------------------------------------
def test_verify_password_none_returns_false():
    assert verify_password("anything", None) is False
    assert verify_password("anything", "") is False
    # Sanity: a real hash still verifies.
    assert verify_password(VALID_PASSWORD, hash_password(VALID_PASSWORD)) is True


# ---------------------------------------------------------------------------
# _find_or_create_oauth_user
# ---------------------------------------------------------------------------
def test_find_or_create_new_user_creates_free_tier(db_session: Session):
    email, sub = _uniq_email(), _uniq_sub()
    user = oauth._find_or_create_oauth_user(db_session, google_sub=sub, email=email)

    assert user.email == email
    assert user.google_sub == sub
    assert user.is_verified is True
    assert user.password_hash is None  # no password for an OAuth-only account

    tier = db_session.query(UserTier).filter(UserTier.user_id == user.id).first()
    assert tier is not None and tier.tier_name == "free"


def test_find_or_create_returns_existing_by_google_sub(db_session: Session):
    email, sub = _uniq_email(), _uniq_sub()
    first = oauth._find_or_create_oauth_user(db_session, google_sub=sub, email=email)
    # Same sub, even with a different email claim, resolves to the same row.
    again = oauth._find_or_create_oauth_user(db_session, google_sub=sub, email=_uniq_email())
    assert again.id == first.id


def test_find_or_create_links_existing_email_and_verifies(db_session: Session):
    """An existing (even unverified) password account is auto-linked: google_sub
    is back-filled and the account is marked verified."""
    email = _uniq_email()
    existing = User(email=email, password_hash=hash_password(VALID_PASSWORD), is_verified=False)
    db_session.add(existing)
    db_session.commit()

    sub = _uniq_sub()
    linked = oauth._find_or_create_oauth_user(db_session, google_sub=sub, email=email)

    assert linked.id == existing.id
    assert linked.google_sub == sub
    assert linked.is_verified is True
    # Password is preserved — the user can still log in either way.
    assert linked.password_hash is not None


def test_find_or_create_conflict_on_mismatched_sub(db_session: Session):
    """Same email already linked to a DIFFERENT Google identity → refuse."""
    email = _uniq_email()
    existing = User(email=email, password_hash=None, google_sub=_uniq_sub(), is_verified=True)
    db_session.add(existing)
    db_session.commit()

    with pytest.raises(oauth._OAuthAccountConflict):
        oauth._find_or_create_oauth_user(db_session, google_sub=_uniq_sub(), email=email)


# ---------------------------------------------------------------------------
# GET /auth/google/login
# ---------------------------------------------------------------------------
def test_google_login_disabled_redirects_to_error(client):
    # No credentials configured by default → feature off.
    resp = client.get("/auth/google/login", follow_redirects=False)
    assert resp.status_code == 302
    assert "/admin/login?error=oauth_unavailable" in resp.headers["location"]


def test_google_login_enabled_redirects_to_google(client, enabled_oauth):
    resp = client.get("/auth/google/login", follow_redirects=False)
    assert resp.status_code == 302
    assert resp.headers["location"].startswith("https://accounts.google.com/o/oauth2/v2/auth?")
    # A state cookie must be set so the callback can verify it.
    assert resp.cookies.get(OAUTH_STATE_COOKIE)


# ---------------------------------------------------------------------------
# GET /auth/google/callback
# ---------------------------------------------------------------------------
def test_google_callback_user_cancelled(client, enabled_oauth):
    resp = client.get("/auth/google/callback?error=access_denied", follow_redirects=False)
    assert resp.status_code == 302
    assert "error=oauth_cancelled" in resp.headers["location"]


def test_google_callback_state_mismatch_rejected(client, enabled_oauth):
    client.cookies.set(OAUTH_STATE_COOKIE, "the-real-state")
    resp = client.get(
        "/auth/google/callback?code=abc&state=forged-state",
        follow_redirects=False,
    )
    assert resp.status_code == 302
    assert "error=oauth_state" in resp.headers["location"]
    # No session must be issued on a failed state check.
    assert not resp.cookies.get(SESSION_COOKIE)


def test_google_callback_success_signs_in(client, db_session, enabled_oauth, monkeypatch):
    email, sub = _uniq_email(), _uniq_sub()
    _patch_google(monkeypatch, sub=sub, email=email)

    client.cookies.set(OAUTH_STATE_COOKIE, "state-123")
    resp = client.get(
        "/auth/google/callback?code=good-code&state=state-123",
        follow_redirects=False,
    )

    assert resp.status_code == 302
    assert resp.headers["location"].endswith("/admin/events")
    assert resp.cookies.get(SESSION_COOKIE)  # session JWT issued

    user = db_session.query(User).filter(User.email == email).first()
    assert user is not None and user.google_sub == sub


def test_google_callback_blocks_disabled_account(client, db_session, enabled_oauth, monkeypatch):
    email, sub = _uniq_email(), _uniq_sub()
    disabled = User(email=email, password_hash=None, google_sub=sub, is_verified=True, is_disabled=True)
    db_session.add(disabled)
    db_session.commit()

    _patch_google(monkeypatch, sub=sub, email=email)
    client.cookies.set(OAUTH_STATE_COOKIE, "state-xyz")
    resp = client.get(
        "/auth/google/callback?code=good-code&state=state-xyz",
        follow_redirects=False,
    )

    assert resp.status_code == 302
    assert "error=account_disabled" in resp.headers["location"]
    assert not resp.cookies.get(SESSION_COOKIE)


def test_google_callback_rejects_unverified_email(client, enabled_oauth, monkeypatch):
    email, sub = _uniq_email(), _uniq_sub()
    _patch_google(monkeypatch, sub=sub, email=email, email_verified=False)

    client.cookies.set(OAUTH_STATE_COOKIE, "state-uv")
    resp = client.get(
        "/auth/google/callback?code=good-code&state=state-uv",
        follow_redirects=False,
    )
    assert resp.status_code == 302
    assert "error=oauth_unverified_email" in resp.headers["location"]
