"""
Regression tests for the guest scan-flow security review:

P1 — CompreFace failures must NOT be hidden as "no matches."
    - 200 with empty result list  -> 400 no_face (legit but tells the user)
    - 5xx / network / auth failure -> 502 upstream_error

P2 — Every scan attempt must produce one AuditLog row so analytics
    counts real activity, not just successful matches.

P2 — The scan rate limiter must also key on event_id + client IP so a
    guest cannot reset their budget by re-authenticating to get a new
    session token.
"""
import base64
import uuid
from datetime import datetime, timedelta
from io import BytesIO
from unittest.mock import AsyncMock, patch

import pytest
from PIL import Image as PILImage
from sqlalchemy.orm import Session

from app.auth import create_event_token, hash_password
from app.database import get_db
from app.main import app
from app.models import (
    AuditLog,
    Event,
    Face,
    GuestSession,
    Image,
    User,
)
from app.rate_limiter import rate_limiter
from app.routers import guest as guest_router


# ─── helpers ────────────────────────────────────────────────────────────────

def _jpeg_b64() -> str:
    img = PILImage.new("RGB", (50, 50), (200, 200, 200))
    buf = BytesIO()
    img.save(buf, format="JPEG")
    return base64.b64encode(buf.getvalue()).decode("ascii")


def _compreface_one_match(event_id, image_id, similarity: float = 0.95):
    return [
        {
            "box": {"x_min": 10, "y_min": 10, "x_max": 60, "y_max": 60, "probability": 0.99},
            "subjects": [
                {"subject": f"{event_id}/{image_id}", "similarity": similarity}
            ],
        }
    ]


@pytest.fixture(autouse=True)
def _reset_scan_buckets():
    """Flush both the per-session and the per-IP scan budgets between tests
    so order doesn't matter.

    The IP-keyed limiter uses keys of the form `f"{event_id}:{client_ip}"`,
    which we can't know without an event — but TestClient always presents
    'testclient' as the client host, so we'll target known patterns via
    the helper inside each test.
    """
    rate_limiter.reset_limit("testclient", "scan")
    yield


@pytest.fixture
def scan_setup(db_session: Session):
    """Owner + active event + one indexed image + one Face row + a valid
    guest session + token. Same shape as test_face_matching but with one
    image since these tests don't care about ranking.
    """
    owner = User(
        email=f"owner-{uuid.uuid4().hex}@example.com",
        password_hash=hash_password("x"),
        is_verified=True,
    )
    db_session.add(owner)
    db_session.commit()
    db_session.refresh(owner)

    event = Event(
        owner_user_id=owner.id,
        slug=f"e-{uuid.uuid4().hex[:8]}",
        name="Failure-mode test event",
        retention_days=30,
        status="active",
        allow_downloads=True,
    )
    db_session.add(event)
    db_session.commit()
    db_session.refresh(event)

    image = Image(
        event_id=event.id,
        filename="i.jpg",
        file_hash=uuid.uuid4().hex + uuid.uuid4().hex,
        size_bytes=100,
        width=100,
        height=100,
        status="indexed",
        face_count=1,
    )
    db_session.add(image)
    db_session.commit()
    db_session.refresh(image)

    face = Face(
        image_id=image.id,
        event_id=event.id,
        bbox=[10.0, 10.0, 60.0, 60.0],
        quality_score=0.9,
        embedding=[0.0] * 512,
        compreface_subject_id=f"{event.id}/{image.id}",
    )
    db_session.add(face)
    db_session.commit()

    session_id = uuid.uuid4()
    token = create_event_token(event.id, session_id)
    guest_session = GuestSession(
        id=session_id,
        event_id=event.id,
        session_token=token,
        expires_at=datetime.utcnow() + timedelta(hours=1),
    )
    db_session.add(guest_session)
    db_session.commit()

    # Reset the IP-bucket for this event so a prior test run doesn't
    # poison a fresh test's budget.
    rate_limiter.reset_limit(f"{event.id}:testclient", "scan_ip")

    return {"event": event, "image": image, "session_id": session_id, "token": token}


# ─── P1: upstream-error path ────────────────────────────────────────────────

def test_compreface_upstream_error_returns_502_not_empty_matches(
    client, db_session: Session, scan_setup
):
    """If every frame raises CompreFaceUpstreamError, the endpoint must
    return 502, not pretend the scan succeeded with zero matches.
    """
    headers = {"Authorization": f"Bearer {scan_setup['token']}"}

    mock_frame = AsyncMock(
        side_effect=guest_router.CompreFaceUpstreamError("simulated 503")
    )
    with patch("app.routers.guest._recognize_single_frame", mock_frame):
        response = client.post("/scan", json={"image": _jpeg_b64()}, headers=headers)

    assert response.status_code == 502, response.text
    assert "unavailable" in response.json()["detail"].lower()


def test_compreface_no_face_returns_400_not_empty_matches(
    client, db_session: Session, scan_setup
):
    """If CompreFace says no usable face was found in any frame, the
    endpoint must return 400 (so the frontend's "no face detected"
    branch triggers) rather than a 200 / 0 matches.
    """
    headers = {"Authorization": f"Bearer {scan_setup['token']}"}

    # _recognize_single_frame returns [] when CompreFace 400'd internally.
    mock_frame = AsyncMock(return_value=[])
    with patch("app.routers.guest._recognize_single_frame", mock_frame):
        response = client.post("/scan", json={"image": _jpeg_b64()}, headers=headers)

    assert response.status_code == 400, response.text
    assert "no face" in response.json()["detail"].lower()


# ─── P2: analytics — every scan logged ──────────────────────────────────────

def _scan_audit_rows_for(db: Session, event_id: uuid.UUID) -> list[AuditLog]:
    return (
        db.query(AuditLog)
        .filter(AuditLog.event_id == event_id, AuditLog.action == "scan")
        .all()
    )


def test_no_face_scan_is_audit_logged(client, db_session: Session, scan_setup):
    """A 'no face detected' result must still create one AuditLog row so
    analytics doesn't undercount scan attempts.
    """
    headers = {"Authorization": f"Bearer {scan_setup['token']}"}
    event = scan_setup["event"]

    with patch("app.routers.guest._recognize_single_frame", AsyncMock(return_value=[])):
        client.post("/scan", json={"image": _jpeg_b64()}, headers=headers)

    rows = _scan_audit_rows_for(db_session, event.id)
    assert len(rows) == 1, f"expected 1 scan row, got {len(rows)}"
    assert rows[0].metadata_.get("outcome") == "no_face"


def test_upstream_error_scan_is_audit_logged(
    client, db_session: Session, scan_setup
):
    """An upstream-error scan attempt must still leave an audit row so
    ops can spot recognizer outages in the analytics view.
    """
    headers = {"Authorization": f"Bearer {scan_setup['token']}"}
    event = scan_setup["event"]

    mock_frame = AsyncMock(
        side_effect=guest_router.CompreFaceUpstreamError("simulated outage")
    )
    with patch("app.routers.guest._recognize_single_frame", mock_frame):
        client.post("/scan", json={"image": _jpeg_b64()}, headers=headers)

    rows = _scan_audit_rows_for(db_session, event.id)
    assert len(rows) == 1
    assert rows[0].metadata_.get("outcome") == "upstream_error"


def test_no_matches_scan_is_audit_logged(client, db_session: Session, scan_setup):
    """A 'face found but no event photos matched' result must still
    create an AuditLog row. Previously the early-return at no-candidates
    skipped log_action, so this kind of scan was invisible to analytics.
    """
    headers = {"Authorization": f"Bearer {scan_setup['token']}"}
    event = scan_setup["event"]

    # Face detected, but the subject prefix points at a DIFFERENT event
    # so the candidate filter at parts[0] != event_id drops everything.
    other_event_id = uuid.uuid4()
    foreign_image_id = uuid.uuid4()
    mock_frame = AsyncMock(
        return_value=_compreface_one_match(other_event_id, foreign_image_id, 0.95)
    )
    with patch("app.routers.guest._recognize_single_frame", mock_frame):
        response = client.post("/scan", json={"image": _jpeg_b64()}, headers=headers)

    assert response.status_code == 200, response.text
    assert response.json()["total_matches"] == 0

    rows = _scan_audit_rows_for(db_session, event.id)
    assert len(rows) == 1
    assert rows[0].metadata_.get("outcome") == "no_matches"


def test_matched_scan_logs_outcome_matched(client, db_session: Session, scan_setup):
    """Sanity check: a successful match logs outcome='matched', not the
    old shape with just match_count."""
    headers = {"Authorization": f"Bearer {scan_setup['token']}"}
    event = scan_setup["event"]
    image = scan_setup["image"]

    mock_frame = AsyncMock(
        return_value=_compreface_one_match(event.id, image.id, 0.95)
    )
    with patch("app.routers.guest._recognize_single_frame", mock_frame):
        response = client.post("/scan", json={"image": _jpeg_b64()}, headers=headers)

    assert response.status_code == 200
    assert response.json()["total_matches"] == 1

    rows = _scan_audit_rows_for(db_session, event.id)
    assert len(rows) == 1
    assert rows[0].metadata_.get("outcome") == "matched"
    assert rows[0].metadata_.get("match_count") == 1


# ─── P2: re-auth doesn't reset the rate budget ──────────────────────────────

def test_reauthenticating_does_not_reset_scan_rate_budget(
    client, db_session: Session, scan_setup
):
    """The per-IP limiter (event_id + client_ip) must persist across a
    new guest auth. Without it, a malicious guest could re-auth in a
    loop to mint fresh session tokens and reset the per-session budget.

    We deliberately exhaust the per-IP bucket with a very small limit
    so the test doesn't have to spam 30 calls.
    """
    event = scan_setup["event"]
    headers = {"Authorization": f"Bearer {scan_setup['token']}"}

    mock_frame = AsyncMock(
        return_value=_compreface_one_match(event.id, scan_setup["image"].id, 0.95)
    )

    # Squeeze the per-IP limit way down for this test, then restore.
    original_limit = rate_limiter.limit
    rate_limiter.limit = 2
    try:
        with patch("app.routers.guest._recognize_single_frame", mock_frame):
            r1 = client.post("/scan", json={"image": _jpeg_b64()}, headers=headers)
            r2 = client.post("/scan", json={"image": _jpeg_b64()}, headers=headers)
            assert r1.status_code == 200
            assert r2.status_code == 200

            # Re-auth: mint a new session token + GuestSession against the
            # same event slug. This is what a malicious guest would do to
            # try to escape the per-session budget.
            new_session_id = uuid.uuid4()
            new_token = create_event_token(event.id, new_session_id)
            db_session.add(GuestSession(
                id=new_session_id,
                event_id=event.id,
                session_token=new_token,
                expires_at=datetime.utcnow() + timedelta(hours=1),
            ))
            db_session.commit()

            # New session_id = per-SESSION limiter starts fresh. But the
            # IP-keyed limiter must still be at 2/2 and reject the third
            # call.
            new_headers = {"Authorization": f"Bearer {new_token}"}
            r3 = client.post("/scan", json={"image": _jpeg_b64()}, headers=new_headers)
            assert r3.status_code == 429, (
                f"per-IP limiter failed to persist across re-auth — "
                f"new-session call returned {r3.status_code}"
            )
    finally:
        rate_limiter.limit = original_limit
        # Clean the IP bucket so other tests aren't affected.
        rate_limiter.reset_limit(f"{event.id}:testclient", "scan_ip")
