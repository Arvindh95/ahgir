"""
Regression tests for the API contract / validation review:

P2 - EventUpdate now enforces the same length bounds as EventCreate
     (slug, location, description) and rejects unknown fields. Pre-fix
     a 100KB description sailed past Pydantic and only failed at the
     DB column length (500 response), and typo'd field names were
     silently ignored.

P3 - BulkPhotoRequest caps image_ids list length and the route
     rejects malformed UUIDs up-front. Pre-fix bad IDs were silently
     dropped, producing partial-success responses with no signal
     about which IDs were ignored.

P3 - PasscodeRequest enforces a max passcode length so a huge JSON
     payload can't reach bcrypt hash compare.

P3 - HTTPException responses are wrapped into the standard
     {error: {code, message}} envelope so the frontend's err.response
     .data.error.message parser surfaces backend messages.
"""
import uuid
from datetime import datetime, timedelta
from io import BytesIO

import pytest
from PIL import Image as PILImage
from sqlalchemy.orm import Session

from app.auth import create_access_token, hash_password
from app.config import settings
from app.models import Event, Image, User


def _make_admin_with_event(db: Session) -> tuple[User, Event, str]:
    user = User(
        email=f"api-{uuid.uuid4().hex}@example.com",
        password_hash=hash_password("x"),
        is_verified=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    event = Event(
        owner_user_id=user.id,
        slug=f"api-{uuid.uuid4().hex[:8]}",
        name="API test event",
        retention_days=30,
        status="active",
    )
    db.add(event)
    db.commit()
    db.refresh(event)

    token = create_access_token(
        data={"sub": str(user.id), "email": user.email},
        expires_delta=timedelta(hours=1),
    )
    return user, event, token


# ─── P2 #1: EventUpdate validation ────────────────────────────────────────


def test_event_update_rejects_oversized_description(client, db_session: Session):
    """A 5000-char description must 422 at Pydantic, not 500 from the
    DB column length later."""
    _user, event, token = _make_admin_with_event(db_session)
    headers = {"Authorization": f"Bearer {token}"}

    r = client.patch(
        f"/events/{event.id}",
        json={"description": "x" * 5000},
        headers=headers,
    )
    assert r.status_code == 422, r.text


def test_event_update_rejects_oversized_location(client, db_session: Session):
    _user, event, token = _make_admin_with_event(db_session)
    headers = {"Authorization": f"Bearer {token}"}

    r = client.patch(
        f"/events/{event.id}",
        json={"location": "x" * 1000},
        headers=headers,
    )
    assert r.status_code == 422, r.text


def test_event_update_rejects_unknown_field(client, db_session: Session):
    """A typo like `descripton` must 422, not 200. Pre-fix the server
    silently dropped it and returned "Event updated"."""
    _user, event, token = _make_admin_with_event(db_session)
    headers = {"Authorization": f"Bearer {token}"}

    r = client.patch(
        f"/events/{event.id}",
        json={"descripton": "typo'd"},
        headers=headers,
    )
    assert r.status_code == 422, r.text


def test_event_update_accepts_valid_payload(client, db_session: Session):
    _user, event, token = _make_admin_with_event(db_session)
    headers = {"Authorization": f"Bearer {token}"}

    r = client.patch(
        f"/events/{event.id}",
        json={"description": "Within bounds", "location": "Somewhere"},
        headers=headers,
    )
    assert r.status_code == 200, r.text


# ─── P3 #2: BulkPhotoRequest validation ──────────────────────────────────


def test_bulk_delete_rejects_overflow_image_ids_at_parse_time(client, db_session: Session):
    _user, event, token = _make_admin_with_event(db_session)
    headers = {"Authorization": f"Bearer {token}"}

    overflow = settings.bulk_download_max_images + 5
    r = client.post(
        f"/events/{event.id}/photos/bulk-delete",
        json={"image_ids": [str(uuid.uuid4()) for _ in range(overflow)]},
        headers=headers,
    )
    assert r.status_code == 422, r.text


def test_bulk_delete_rejects_malformed_uuid_explicitly(client, db_session: Session):
    """Pre-fix malformed UUIDs were silently dropped — bulk_delete
    returned "deleted N" for the survivors and the client had no
    signal about which IDs were typos."""
    _user, event, token = _make_admin_with_event(db_session)
    headers = {"Authorization": f"Bearer {token}"}

    r = client.post(
        f"/events/{event.id}/photos/bulk-delete",
        json={"image_ids": ["not-a-uuid", str(uuid.uuid4())]},
        headers=headers,
    )
    assert r.status_code == 400, r.text


# ─── P3 #3: Passcode length cap ──────────────────────────────────────────


def test_passcode_request_rejects_oversized_passcode(client, db_session: Session):
    """A 1KB passcode must 422 at Pydantic, not reach bcrypt's compare."""
    # We need an event slug to even hit /e/{slug}/auth. Use any
    # event from the helper.
    user = User(
        email=f"pc-{uuid.uuid4().hex}@example.com",
        password_hash=hash_password("x"),
        is_verified=True,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)

    event = Event(
        owner_user_id=user.id,
        slug=f"pc-{uuid.uuid4().hex[:8]}",
        name="Passcode test",
        retention_days=30,
        status="active",
        passcode_hash=hash_password("real"),
    )
    db_session.add(event)
    db_session.commit()
    db_session.refresh(event)

    r = client.post(
        f"/e/{event.slug}/auth",
        json={"passcode": "x" * 1024},
    )
    assert r.status_code == 422, r.text


# ─── P3 #4: HTTPException -> error envelope ──────────────────────────────


def test_404_event_not_found_returns_standard_error_envelope(client, db_session: Session):
    """Any direct HTTPException (not just PicUrException) must produce
    a body shaped like {error: {code, message}}. The frontend reads
    err.response.data.error.message and falls back to a generic
    message otherwise — this is what gave us "Failed to load event"
    when the backend actually had a specific reason.
    """
    _user, _event, token = _make_admin_with_event(db_session)
    headers = {"Authorization": f"Bearer {token}"}

    bogus_id = str(uuid.uuid4())
    r = client.get(f"/events/{bogus_id}", headers=headers)
    assert r.status_code == 404
    body = r.json()
    assert "error" in body
    assert isinstance(body["error"], dict)
    assert "code" in body["error"]
    assert "message" in body["error"]
    assert body["error"]["code"] == "NOT_FOUND"
    assert "Event not found" in body["error"]["message"]


def test_403_forbidden_uses_standard_envelope(client, db_session: Session):
    """A different user's event triggers 403. Same envelope shape
    must apply.
    """
    # Two users, one event
    user_a = User(email=f"a-{uuid.uuid4().hex}@example.com", password_hash=hash_password("x"), is_verified=True)
    user_b = User(email=f"b-{uuid.uuid4().hex}@example.com", password_hash=hash_password("x"), is_verified=True)
    db_session.add_all([user_a, user_b])
    db_session.commit()
    db_session.refresh(user_a)
    db_session.refresh(user_b)

    event = Event(
        owner_user_id=user_a.id,
        slug=f"fb-{uuid.uuid4().hex[:8]}",
        name="Forbidden test",
        retention_days=30,
        status="active",
    )
    db_session.add(event)
    db_session.commit()
    db_session.refresh(event)

    # Log in as user_b, try to access user_a's event
    token_b = create_access_token(
        data={"sub": str(user_b.id), "email": user_b.email},
        expires_delta=timedelta(hours=1),
    )
    headers = {"Authorization": f"Bearer {token_b}"}

    r = client.get(f"/events/{event.id}", headers=headers)
    assert r.status_code == 403
    body = r.json()
    assert body["error"]["code"] == "FORBIDDEN"
    assert "permission" in body["error"]["message"].lower()


def test_structured_detail_dict_preserves_inner_code(client, db_session: Session):
    """Some routers raise HTTPException with detail=dict that carries
    its own 'code' field (e.g. EVENT_NOT_ACTIVE). The wrapper should
    surface that inner code instead of the generic HTTP-status code.
    """
    # Need a frozen event to trigger the EVENT_NOT_ACTIVE branch.
    user = User(email=f"fr-{uuid.uuid4().hex}@example.com", password_hash=hash_password("x"), is_verified=True)
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)

    event = Event(
        owner_user_id=user.id,
        slug=f"fr-{uuid.uuid4().hex[:8]}",
        name="Frozen test",
        retention_days=30,
        status="frozen",
    )
    db_session.add(event)
    db_session.commit()
    db_session.refresh(event)

    token = create_access_token(
        data={"sub": str(user.id), "email": user.email},
        expires_delta=timedelta(hours=1),
    )
    headers = {"Authorization": f"Bearer {token}"}

    r = client.patch(
        f"/events/{event.id}",
        json={"description": "trying to update a frozen event"},
        headers=headers,
    )
    assert r.status_code == 403, r.text
    body = r.json()
    # The structured detail's 'code' wins over the generic FORBIDDEN.
    assert body["error"]["code"] == "EVENT_NOT_ACTIVE", body
