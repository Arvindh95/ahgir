"""
Behavior-change test for the per-event passcode rate-limiter (P2 fix).

Before the fix, the limiter consumed budget on EVERY /e/{slug}/auth call —
including successful entries to a passcode-required event and any entry to
a no-passcode event. That meant a busy event could legitimately exhaust
10/hr and lock out real guests.

After the fix the limiter only counts FAILED passcode attempts on events
that actually require a passcode.

Tests:
1. No-passcode event: many successful auths in a row don't trip the limiter.
2. Passcode event, correct passcode: many successful auths in a row don't
   trip the limiter.
3. Passcode event, wrong passcode: limiter trips after the configured budget.
"""
from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.auth import hash_password
from app.database import get_db
from app.main import app
from app.models import Event, User
from app.rate_limiter import event_passcode_rate_limiter, redis_client


client = TestClient(app)


def _override(db_session: Session):
    def _get():
        try:
            yield db_session
        finally:
            pass
    app.dependency_overrides[get_db] = _get


def _reset_slug(slug: str) -> None:
    # Clear EVERY rate-limit key so a noisy prior run can't make these tests
    # flake. We're testing the per-slug limiter specifically but the same
    # endpoint also touches the IP-keyed guest_auth limiter, so wipe both.
    for key in redis_client.scan_iter("rate_limit:*"):
        redis_client.delete(key)


def _make_user(db_session: Session) -> User:
    import uuid as _uuid
    u = User(
        email=f"owner-{_uuid.uuid4().hex[:8]}@example.com",
        password_hash=hash_password("StrongPass1!"),
        is_verified=True,
    )
    db_session.add(u)
    db_session.commit()
    db_session.refresh(u)
    return u


def _make_event(db_session: Session, owner: User, slug: str, *, passcode: str = None) -> Event:
    e = Event(
        name="Limiter Test Event",
        slug=slug,
        date=date(2026, 6, 1),
        owner_user_id=owner.id,
        retention_days=90,
        status="active",
        passcode_hash=hash_password(passcode) if passcode else None,
    )
    db_session.add(e)
    db_session.commit()
    db_session.refresh(e)
    return e


def test_no_passcode_event_does_not_consume_limiter(db_session: Session):
    """A no-passcode event must allow more than `limit` consecutive auths."""
    slug = "no-passcode-limiter-test"
    _reset_slug(slug)
    _override(db_session)

    owner = _make_user(db_session)
    _make_event(db_session, owner, slug)

    # Hit the endpoint limit+2 times to be sure we'd exceed any budget.
    n_calls = event_passcode_rate_limiter.limit + 2
    statuses = []
    for _ in range(n_calls):
        r = client.post(f"/e/{slug}/auth", json={"passcode": None})
        statuses.append(r.status_code)

    # All should be 200 — none rate-limited (429).
    assert all(s == 200 for s in statuses), f"unexpected: {statuses}"

    app.dependency_overrides.clear()


def test_passcode_event_correct_passcode_does_not_consume_limiter(db_session: Session):
    """A passcode-required event must allow more than `limit` *correct* auths."""
    slug = "passcode-correct-limiter-test"
    _reset_slug(slug)
    _override(db_session)

    owner = _make_user(db_session)
    _make_event(db_session, owner, slug, passcode="opensesame")

    n_calls = event_passcode_rate_limiter.limit + 2
    statuses = []
    for _ in range(n_calls):
        r = client.post(f"/e/{slug}/auth", json={"passcode": "opensesame"})
        statuses.append(r.status_code)

    assert all(s == 200 for s in statuses), f"unexpected: {statuses}"

    app.dependency_overrides.clear()


def test_passcode_event_wrong_passcode_does_consume_limiter(db_session: Session):
    """Wrong passcodes must count toward the per-slug failure budget.

    After `limit` wrong attempts the next attempt must be 429, not 401.
    """
    slug = "passcode-wrong-limiter-test"
    _reset_slug(slug)
    _override(db_session)

    owner = _make_user(db_session)
    _make_event(db_session, owner, slug, passcode="opensesame")

    # Fire `limit` wrong attempts — every one of them should 401.
    limit = event_passcode_rate_limiter.limit
    for i in range(limit):
        r = client.post(f"/e/{slug}/auth", json={"passcode": f"wrong-{i}"})
        assert r.status_code == 401, f"attempt {i+1} returned {r.status_code}: {r.text}"

    # The next attempt must be 429 — limiter has tripped.
    over = client.post(f"/e/{slug}/auth", json={"passcode": "still-wrong"})
    assert over.status_code == 429, f"expected 429 after {limit} wrong attempts, got {over.status_code}: {over.text}"

    # And even a CORRECT passcode now is blocked (limiter check runs first).
    correct_after_lockout = client.post(f"/e/{slug}/auth", json={"passcode": "opensesame"})
    assert correct_after_lockout.status_code == 429, correct_after_lockout.text

    app.dependency_overrides.clear()
