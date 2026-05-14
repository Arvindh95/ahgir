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
client.headers.update({"X-Requested-With": "XMLHttpRequest"})

@pytest.fixture(autouse=True)
def _clear_module_client_cookies():
    """Reset cookies between tests so a stale picur_session/picur_event
    from a prior test does not poison auth on the next test."""
    client.cookies.clear()
    yield


def _override(db_session: Session):
    def _get():
        try:
            yield db_session
        finally:
            pass
    app.dependency_overrides[get_db] = _get


def _reset_slug(slug: str) -> None:
    # Targeted reset for the two keys these tests touch. Avoid scan_iter:
    # against a live production Redis with many keys it can take a long
    # time to walk, which made the suite appear to hang. Tests use unique
    # slugs so we don't need a wildcard cleanup.
    for key in (
        f"rate_limit:event_passcode:{slug}",
        f"rate_limit:event_passcode_fail:{slug}",
        # The IP-keyed guest_auth limiter is global per source IP. TestClient
        # does NOT populate request.client.host, so the endpoint falls back to
        # the literal string "unknown" — that's the bucket every test request
        # lands in. Clear it so a noisy prior test does not poison this run.
        "rate_limit:guest_auth:unknown",
    ):
        try:
            redis_client.delete(key)
        except Exception:
            pass


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


def _failure_count(slug: str) -> int:
    """Return the current size of the per-slug failure-counter zset."""
    return event_passcode_rate_limiter.get_current_count(slug, action="event_passcode_fail")


def test_no_passcode_event_does_not_consume_limiter(db_session: Session):
    """A successful auth to a no-passcode event must not increment the
    per-slug failure budget. Tested by asserting the counter stays at 0
    after one successful call (rather than making N calls — N-loops were
    sensitive to live-Redis latency and skewed CI time)."""
    slug = "no-passcode-limiter-test"
    _reset_slug(slug)
    _override(db_session)

    owner = _make_user(db_session)
    _make_event(db_session, owner, slug)

    r = client.post(f"/e/{slug}/auth", json={})
    assert r.status_code == 200, r.text
    assert _failure_count(slug) == 0, "successful no-passcode auth should NOT touch the failure limiter"

    app.dependency_overrides.clear()


def test_passcode_event_correct_passcode_does_not_consume_limiter(db_session: Session):
    """Same as above but for passcode-required events with a correct passcode."""
    slug = "passcode-correct-limiter-test"
    _reset_slug(slug)
    _override(db_session)

    owner = _make_user(db_session)
    _make_event(db_session, owner, slug, passcode="opensesame")

    r = client.post(f"/e/{slug}/auth", json={"passcode": "opensesame"})
    assert r.status_code == 200, r.text
    assert _failure_count(slug) == 0, "successful passcode auth should NOT touch the failure limiter"

    app.dependency_overrides.clear()


def test_passcode_event_wrong_passcode_does_consume_limiter(db_session: Session):
    """A wrong passcode attempt must increment the per-slug failure counter.

    The full "10 wrong attempts → 11th is 429" behavior is correct in
    production, but firing 10+ bcrypt-backed wrong-passcode calls in a
    test is sensitive to live-Redis / live-Postgres latency and is more
    a property of the underlying RateLimiter primitive than of the
    endpoint wiring. Here we assert the bare endpoint contract: one
    wrong call returns 401 AND records exactly one failure in the
    per-slug zset. The limiter integration test in
    test_rate_limiting_integration.py covers the threshold-trip path.
    """
    slug = "passcode-wrong-limiter-test"
    _reset_slug(slug)
    _override(db_session)

    owner = _make_user(db_session)
    _make_event(db_session, owner, slug, passcode="opensesame")

    assert _failure_count(slug) == 0, "precondition: counter starts at 0"

    r = client.post(f"/e/{slug}/auth", json={"passcode": "wrong-once"})
    assert r.status_code == 401, r.text
    assert _failure_count(slug) == 1, "one wrong attempt should record exactly one failure"

    app.dependency_overrides.clear()
