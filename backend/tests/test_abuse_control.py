"""
Regression tests for the abuse-control review:

P2 — download_zip per-(event_id, client_ip) limiter survives re-auth
     so a guest can't bypass the per-session download throttle by
     rolling guest sessions.

P3 — Passcode failure throttling is now two-tier. Per-IP-per-slug
     budget trips first when a SINGLE bad actor is brute-forcing, so
     other guests on different IPs aren't collaterally locked out.

P3 — FaceScanRequest and BulkDownloadRequest reject oversized payloads
     at Pydantic parse time (Field max_length / max_items) instead of
     deserialising arbitrary input and rejecting only inside route
     code.
"""
import base64
import uuid
from datetime import datetime, timedelta
from io import BytesIO

import pytest
from PIL import Image as PILImage
from sqlalchemy.orm import Session

from app.auth import create_event_token, hash_password
from app.config import settings
from app.models import Event, GuestSession, Image, User
from app.rate_limiter import (
    download_ip_rate_limiter,
    event_passcode_ip_rate_limiter,
    event_passcode_rate_limiter,
    rate_limiter,
)


def _jpeg_b64() -> str:
    img = PILImage.new("RGB", (50, 50), (200, 200, 200))
    buf = BytesIO()
    img.save(buf, format="JPEG")
    return base64.b64encode(buf.getvalue()).decode("ascii")


def _seed_event_with_passcode(db: Session, passcode_plain: str) -> Event:
    user = User(
        email=f"abuse-{uuid.uuid4().hex}@example.com",
        password_hash=hash_password("x"),
        is_verified=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    event = Event(
        owner_user_id=user.id,
        slug=f"abuse-{uuid.uuid4().hex[:8]}",
        name="Abuse-control test event",
        retention_days=30,
        status="active",
        passcode_hash=hash_password(passcode_plain),
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    return event


def _seed_event_with_photo(db: Session) -> tuple[Event, Image, str]:
    """Event + one image + a valid guest token."""
    user = User(
        email=f"abuse-{uuid.uuid4().hex}@example.com",
        password_hash=hash_password("x"),
        is_verified=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    event = Event(
        owner_user_id=user.id,
        slug=f"abuse-{uuid.uuid4().hex[:8]}",
        name="Abuse-control event",
        retention_days=30,
        status="active",
        allow_downloads=True,
    )
    db.add(event)
    db.commit()
    db.refresh(event)

    image = Image(
        event_id=event.id,
        filename="x.jpg",
        file_hash=uuid.uuid4().hex + uuid.uuid4().hex,
        size_bytes=100,
        width=100,
        height=100,
        status="indexed",
        face_count=0,
    )
    db.add(image)
    db.commit()
    db.refresh(image)

    session_id = uuid.uuid4()
    token = create_event_token(event.id, session_id)
    db.add(GuestSession(
        id=session_id,
        event_id=event.id,
        session_token=token,
        expires_at=datetime.utcnow() + timedelta(hours=1),
    ))
    db.commit()

    download_ip_rate_limiter.reset_limit(f"{event.id}:testclient", "download_ip")
    return event, image, token


# ─── P2: download per-IP survives re-auth ─────────────────────────────────


def test_downloading_then_reauth_still_hits_ip_limit(client, db_session: Session):
    """The per-IP download limiter must persist when a guest re-auths to
    mint a fresh session. Without it the per-session budget resets and
    the throttle is trivially bypassable.
    """
    event, image, token = _seed_event_with_photo(db_session)

    original_limit = download_ip_rate_limiter.limit
    download_ip_rate_limiter.limit = 1
    try:
        headers = {"Authorization": f"Bearer {token}"}
        payload = {"image_ids": [str(image.id)]}

        r1 = client.post("/download-zip", json=payload, headers=headers)
        # 200 (success) OR 404/500 if MinIO isn't actually serving the
        # photo — either way the limiter recorded one use.
        assert r1.status_code in (200, 404, 500), r1.text

        # Mint a fresh session for the SAME event (the re-auth bypass).
        new_session_id = uuid.uuid4()
        new_token = create_event_token(event.id, new_session_id)
        db_session.add(GuestSession(
            id=new_session_id,
            event_id=event.id,
            session_token=new_token,
            expires_at=datetime.utcnow() + timedelta(hours=1),
        ))
        db_session.commit()
        new_headers = {"Authorization": f"Bearer {new_token}"}

        # The per-session limiter is fresh, but the per-IP limiter still
        # remembers the first hit. Second call must 429.
        r2 = client.post("/download-zip", json=payload, headers=new_headers)
        assert r2.status_code == 429, (
            f"re-auth bypass must not work — got {r2.status_code}, body "
            f"{r2.text}"
        )
    finally:
        download_ip_rate_limiter.limit = original_limit
        download_ip_rate_limiter.reset_limit(f"{event.id}:testclient", "download_ip")


# ─── P3: passcode failure throttling is two-tier ───────────────────────────


def test_single_ip_locks_only_itself_not_all_guests(client, db_session: Session):
    """Tier 1 (per-slug+IP) fires before Tier 2 (per-slug) when a single
    bad actor is brute-forcing. Other IPs must still be able to fail-
    and-eventually-succeed without being locked out by the attacker.
    """
    event = _seed_event_with_passcode(db_session, passcode_plain="correct-horse")

    original_ip_limit = event_passcode_ip_rate_limiter.limit
    original_slug_limit = event_passcode_rate_limiter.limit
    # Tight tier 1 (5 per IP) AND high tier 2 (100 per slug) so we exercise
    # tier 1 in isolation.
    event_passcode_ip_rate_limiter.limit = 3
    event_passcode_rate_limiter.limit = 100
    # Reset both budgets so a prior test run isn't poisoning state.
    event_passcode_ip_rate_limiter.reset_limit(
        f"{event.slug}:testclient", "event_passcode_fail_ip"
    )
    event_passcode_rate_limiter.reset_limit(event.slug, "event_passcode_fail")

    try:
        # Burn through the per-IP budget with wrong passcodes from the
        # one fixed TestClient IP.
        for i in range(3):
            r = client.post(f"/e/{event.slug}/auth", json={"passcode": f"wrong-{i}"})
            assert r.status_code == 401, f"attempt {i}: {r.text}"

        # 4th attempt must be 429 (per-IP limit hit), NOT 401.
        r = client.post(f"/e/{event.slug}/auth", json={"passcode": "wrong-final"})
        assert r.status_code == 429, (
            f"per-IP limit failed to trip — got {r.status_code}"
        )

        # The per-slug budget should NOT have been exhausted yet (only 4
        # failures recorded against a 100-budget). A different IP should
        # still be able to attempt — we can't simulate a different IP from
        # TestClient, but we CAN verify the per-slug counter hasn't
        # already-locked it out.
        slug_count = event_passcode_rate_limiter.get_current_count(
            event.slug, "event_passcode_fail"
        )
        assert slug_count < event_passcode_rate_limiter.limit, (
            "per-slug bucket exhausted by a single IP — should still have headroom"
        )
    finally:
        event_passcode_ip_rate_limiter.limit = original_ip_limit
        event_passcode_rate_limiter.limit = original_slug_limit
        event_passcode_ip_rate_limiter.reset_limit(
            f"{event.slug}:testclient", "event_passcode_fail_ip"
        )
        event_passcode_rate_limiter.reset_limit(event.slug, "event_passcode_fail")


def test_correct_passcode_does_not_burn_either_budget(client, db_session: Session):
    """Successful passcode attempts must NEVER consume the failure
    budgets — neither per-slug nor per-IP. Re-confirms the
    'enforce inside failure branches only' pattern.
    """
    event = _seed_event_with_passcode(db_session, passcode_plain="correct-horse")

    event_passcode_ip_rate_limiter.reset_limit(
        f"{event.slug}:testclient", "event_passcode_fail_ip"
    )
    event_passcode_rate_limiter.reset_limit(event.slug, "event_passcode_fail")

    r = client.post(f"/e/{event.slug}/auth", json={"passcode": "correct-horse"})
    assert r.status_code == 200, r.text

    assert event_passcode_ip_rate_limiter.get_current_count(
        f"{event.slug}:testclient", "event_passcode_fail_ip"
    ) == 0
    assert event_passcode_rate_limiter.get_current_count(
        event.slug, "event_passcode_fail"
    ) == 0


# ─── P3: Pydantic-level size protections ──────────────────────────────────


def test_face_scan_rejects_oversized_image_at_parse_time(client, db_session: Session):
    """An image string longer than the bound is rejected with 422 before
    the route code ever sees it — proves the cap is enforced at
    Pydantic parse time, not after the body has been deserialised.
    """
    # Need a valid guest token to even hit the endpoint; otherwise the
    # auth dep would 403 before we reach the body parser.
    event, _image, token = _seed_event_with_photo(db_session)
    headers = {"Authorization": f"Bearer {token}"}

    # Build a payload comfortably larger than max_scan_frame_bytes * 4/3.
    # The proof that the cap is at PARSE time is the 422 — pre-fix this
    # request would have returned 413 from the in-route check AFTER the
    # body had been deserialised into a multi-MB string in memory.
    over = "A" * ((settings.max_scan_frame_bytes * 4 // 3) + 1024)
    r = client.post("/scan", json={"image": over}, headers=headers)
    assert r.status_code == 422, r.text  # global error handler scrubs detail text


def test_face_scan_rejects_too_many_additional_frames(client, db_session: Session):
    """additional_frames is capped to 4 by Pydantic. Sending 10 must
    422 immediately."""
    event, _image, token = _seed_event_with_photo(db_session)
    headers = {"Authorization": f"Bearer {token}"}

    frame = _jpeg_b64()
    payload = {"image": frame, "additional_frames": [frame] * 10}
    r = client.post("/scan", json=payload, headers=headers)
    assert r.status_code == 422, r.text


def test_bulk_download_rejects_too_many_image_ids_at_parse_time(client, db_session: Session):
    """BulkDownloadRequest.image_ids is capped to settings.bulk_download
    _max_images at Pydantic parse time."""
    event, _image, token = _seed_event_with_photo(db_session)
    headers = {"Authorization": f"Bearer {token}"}

    overflow = settings.bulk_download_max_images + 5
    payload = {"image_ids": [str(uuid.uuid4()) for _ in range(overflow)]}
    r = client.post("/download-zip", json=payload, headers=headers)
    assert r.status_code == 422, r.text
