"""
Regression test for the audit-log "8h ago" bug.

Backend writes datetime.utcnow() and stores into TIMESTAMP columns
(no timezone). Pre-fix the API serialized the naive datetime as
"2026-05-14T06:48:31.252480" — no Z, no offset. JavaScript's
``new Date(str)`` parses such strings as LOCAL time, so a row written
one second ago appeared 8 hours old in a Malaysian (UTC+8) browser.

This test confirms every user-visible timestamp field carries a
timezone offset on the wire so the browser parses it correctly.
"""
import re
import uuid
from datetime import datetime, timedelta

import pytest
from sqlalchemy.orm import Session

from app.audit import log_action
from app.auth import create_access_token, hash_password
from app.models import Event, Image, User
from app.utils.time import to_utc_iso


# Match "...+00:00" or "...Z" at the end of an ISO timestamp.
_ISO_TZ_RE = re.compile(r"(\+\d{2}:?\d{2}|Z)$")


def _has_utc_offset(s: str) -> bool:
    return bool(_ISO_TZ_RE.search(s))


def test_to_utc_iso_adds_utc_offset_to_naive_datetime():
    """Unit test for the helper itself."""
    naive = datetime(2026, 5, 14, 6, 48, 31)
    iso = to_utc_iso(naive)
    assert iso is not None
    assert _has_utc_offset(iso), f"expected UTC offset in {iso!r}"


def test_to_utc_iso_passes_none_through():
    assert to_utc_iso(None) is None


def test_event_audit_log_timestamp_has_utc_offset(client, db_session: Session):
    """The per-event /events/{id}/logs endpoint must emit timestamp
    fields with a UTC offset so JS parses them as UTC, not local."""
    user = User(
        email=f"tz-{uuid.uuid4().hex}@example.com",
        password_hash=hash_password("x"),
        is_verified=True,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)

    event = Event(
        owner_user_id=user.id,
        slug=f"tz-{uuid.uuid4().hex[:8]}",
        name="Timezone test",
        retention_days=30,
        status="active",
    )
    db_session.add(event)
    db_session.commit()
    db_session.refresh(event)

    log_action(
        db=db_session,
        event_id=event.id,
        actor_type="admin",
        actor_id=user.id,
        action="test_action",
        metadata={"why": "timezone test"},
    )

    token = create_access_token(
        data={"sub": str(user.id), "email": user.email},
        expires_delta=timedelta(hours=1),
    )
    r = client.get(
        f"/events/{event.id}/logs",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert len(body["logs"]) >= 1
    ts = body["logs"][0]["timestamp"]
    assert _has_utc_offset(ts), (
        f"audit log timestamp must include a UTC offset; got {ts!r}. "
        f"Without it, JS new Date() parses as local time and fresh "
        f"entries appear stale by the user's UTC offset (e.g. 8h ago in MYT)."
    )


def test_admin_audit_log_timestamp_has_utc_offset(client, db_session: Session):
    """Superadmin /admin/audit-log endpoint also has to emit offsets."""
    superadmin = User(
        email=f"sa-{uuid.uuid4().hex}@example.com",
        password_hash=hash_password("x"),
        is_verified=True,
        is_superadmin=True,
    )
    db_session.add(superadmin)
    db_session.commit()
    db_session.refresh(superadmin)

    event = Event(
        owner_user_id=superadmin.id,
        slug=f"tz-{uuid.uuid4().hex[:8]}",
        name="Admin tz test",
        retention_days=30,
    )
    db_session.add(event)
    db_session.commit()
    db_session.refresh(event)

    log_action(
        db=db_session,
        event_id=event.id,
        actor_type="admin",
        actor_id=superadmin.id,
        action="admin_test_action",
        metadata={},
    )

    token = create_access_token(
        data={"sub": str(superadmin.id), "email": superadmin.email},
        expires_delta=timedelta(hours=1),
    )
    r = client.get(
        "/admin/audit-log?limit=10",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert len(body["entries"]) >= 1
    ts = body["entries"][0]["timestamp"]
    assert _has_utc_offset(ts), f"superadmin audit-log timestamp missing offset: {ts!r}"


def test_photo_list_uploaded_at_has_utc_offset(client, db_session: Session):
    user = User(
        email=f"pl-{uuid.uuid4().hex}@example.com",
        password_hash=hash_password("x"),
        is_verified=True,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)

    event = Event(
        owner_user_id=user.id,
        slug=f"pl-{uuid.uuid4().hex[:8]}",
        name="Photo list tz test",
        retention_days=30,
        status="active",
    )
    db_session.add(event)
    db_session.commit()
    db_session.refresh(event)

    image = Image(
        event_id=event.id,
        filename="f.jpg",
        file_hash=uuid.uuid4().hex + uuid.uuid4().hex,
        size_bytes=100,
        width=100,
        height=100,
        status="indexed",
        face_count=0,
    )
    db_session.add(image)
    db_session.commit()

    token = create_access_token(
        data={"sub": str(user.id), "email": user.email},
        expires_delta=timedelta(hours=1),
    )
    r = client.get(
        f"/events/{event.id}/photos",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    ts = body["photos"][0]["uploaded_at"]
    assert _has_utc_offset(ts), f"photo uploaded_at missing offset: {ts!r}"


def test_event_detail_created_at_has_utc_offset(client, db_session: Session):
    user = User(
        email=f"ed-{uuid.uuid4().hex}@example.com",
        password_hash=hash_password("x"),
        is_verified=True,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)

    event = Event(
        owner_user_id=user.id,
        slug=f"ed-{uuid.uuid4().hex[:8]}",
        name="Event detail tz test",
        retention_days=30,
        status="active",
    )
    db_session.add(event)
    db_session.commit()
    db_session.refresh(event)

    token = create_access_token(
        data={"sub": str(user.id), "email": user.email},
        expires_delta=timedelta(hours=1),
    )
    r = client.get(
        f"/events/{event.id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    ts = body["created_at"]
    assert _has_utc_offset(ts), f"event created_at missing offset: {ts!r}"
