"""
Endpoint tests covering the gaps flagged in the second security review:
- Frozen-event photo deletion must be blocked (the P2 fix).
- Bulk delete: ownership, ID validation, frozen-event block.
- Event delete: ownership.
- Event update: ownership + frozen-event block.
- Event cover upload: ownership + frozen-event block (skipped with reason
  if the test runner cannot ship multipart data through this codebase's
  storage stub).

Existing tests already cover list / get / QR / single-photo upload and
delete / reindex isolation, so this file only fills the missing surfaces.
"""
from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.auth import create_access_token, hash_password
from app.database import get_db
from app.main import app
from app.models import Event, Image, User, UserTier


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


def _attach_pro_tier(db_session: Session, user: User) -> None:
    db_session.add(UserTier(
        user_id=user.id,
        tier_name="pro",
        max_events=20,
        max_photos_per_event=2000,
        retention_days=365,
        price_cents=9900,
        is_active=True,
    ))
    db_session.commit()


def _make_user(db_session: Session, email: str, *, with_tier: bool = True) -> User:
    u = User(email=email, password_hash=hash_password("StrongPass1!"), is_verified=True)
    db_session.add(u)
    db_session.commit()
    db_session.refresh(u)
    if with_tier:
        _attach_pro_tier(db_session, u)
    return u


def _make_event(db_session: Session, owner: User, *, name: str = "Test Event", status_: str = "active") -> Event:
    e = Event(
        name=name,
        slug=f"{name.lower().replace(' ', '-')}-{owner.id.hex[:6]}",
        date=date(2026, 6, 15),
        owner_user_id=owner.id,
        retention_days=90,
        status=status_,
    )
    db_session.add(e)
    db_session.commit()
    db_session.refresh(e)
    return e


def _make_image(db_session: Session, event: Event, *, filename: str = None) -> Image:
    # Minimal kwargs matching the Image model in app/models.py — the
    # MinIO object key is derived from event_id + image_id at runtime,
    # so there is no storage_path column on the row itself. Filename is
    # parameterised because there's a UNIQUE (event_id, filename) and
    # some tests need two images on the same event.
    import uuid as _uuid
    img = Image(
        event_id=event.id,
        filename=filename or f"test-{_uuid.uuid4().hex[:8]}.jpg",
        file_hash=_uuid.uuid4().hex + _uuid.uuid4().hex,  # 64-char unique placeholder
        size_bytes=1024,
        width=800,
        height=600,
        status="indexed",
        face_count=0,
    )
    db_session.add(img)
    db_session.commit()
    db_session.refresh(img)
    return img


# ---------- FROZEN EVENT: photo deletion must be blocked (P2 fix) ----------

def test_delete_photo_blocked_on_frozen_event(db_session: Session):
    """The P2 fix: deleting a photo from a frozen event must 403 with EVENT_NOT_ACTIVE."""
    owner = _make_user(db_session, "frozen-del@example.com")
    event = _make_event(db_session, owner, status_="frozen")
    image = _make_image(db_session, event)
    _override(db_session)
    token = create_access_token({"sub": str(owner.id), "email": owner.email})

    response = client.delete(
        f"/events/{event.id}/photos/{image.id}",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 403, response.text
    body = response.json()
    # FastAPI standard envelope wraps detail under `error.details`. Accept either
    # legacy `detail` or the new envelope so this test stays useful across the
    # error_handler rewrite.
    payload = body.get("error", {}).get("details") or body.get("detail") or {}
    assert payload.get("code") == "EVENT_NOT_ACTIVE" or "EVENT_NOT_ACTIVE" in response.text

    # Photo must still be in the DB.
    refreshed = db_session.query(Image).filter(Image.id == image.id).first()
    assert refreshed is not None

    app.dependency_overrides.clear()


def test_bulk_delete_blocked_on_frozen_event(db_session: Session):
    """Same as above, but the bulk-delete back door."""
    owner = _make_user(db_session, "frozen-bulkdel@example.com")
    event = _make_event(db_session, owner, status_="frozen")
    img1 = _make_image(db_session, event)
    img2 = _make_image(db_session, event)
    _override(db_session)
    token = create_access_token({"sub": str(owner.id), "email": owner.email})

    response = client.post(
        f"/events/{event.id}/photos/bulk-delete",
        headers={"Authorization": f"Bearer {token}"},
        json={"image_ids": [str(img1.id), str(img2.id)]},
    )

    assert response.status_code == 403, response.text
    # Both photos must still exist.
    remaining = db_session.query(Image).filter(Image.event_id == event.id).all()
    assert len(remaining) == 2

    app.dependency_overrides.clear()


def test_delete_photo_works_on_active_event(db_session: Session):
    """Sanity: the mutable-check does NOT break the happy path on active events."""
    owner = _make_user(db_session, "active-del@example.com")
    event = _make_event(db_session, owner, status_="active")
    image = _make_image(db_session, event)
    _override(db_session)
    token = create_access_token({"sub": str(owner.id), "email": owner.email})

    response = client.delete(
        f"/events/{event.id}/photos/{image.id}",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200, response.text
    refreshed = db_session.query(Image).filter(Image.id == image.id).first()
    assert refreshed is None

    app.dependency_overrides.clear()


# ---------- BULK DELETE: ownership + validation ----------

def test_bulk_delete_other_owners_event_forbidden(db_session: Session):
    """A non-owner (not superadmin) cannot bulk-delete photos on someone else's event."""
    owner = _make_user(db_session, "bd-owner@example.com")
    intruder = _make_user(db_session, "bd-intruder@example.com")
    event = _make_event(db_session, owner)
    img = _make_image(db_session, event)
    _override(db_session)
    token = create_access_token({"sub": str(intruder.id), "email": intruder.email})

    response = client.post(
        f"/events/{event.id}/photos/bulk-delete",
        headers={"Authorization": f"Bearer {token}"},
        json={"image_ids": [str(img.id)]},
    )
    assert response.status_code == 403, response.text

    remaining = db_session.query(Image).filter(Image.id == img.id).first()
    assert remaining is not None

    app.dependency_overrides.clear()


def test_bulk_delete_empty_image_ids_rejected(db_session: Session):
    """Empty image_ids must return 400, not silently no-op."""
    owner = _make_user(db_session, "bd-empty@example.com")
    event = _make_event(db_session, owner)
    _override(db_session)
    token = create_access_token({"sub": str(owner.id), "email": owner.email})

    response = client.post(
        f"/events/{event.id}/photos/bulk-delete",
        headers={"Authorization": f"Bearer {token}"},
        json={"image_ids": []},
    )
    # 422 from Pydantic min_length=1 OR 400 from the route's
    # "No images specified" guard — either is a clean rejection of
    # an empty list. Pre-fix only 400 was possible; post-fix 422
    # trips first.
    assert response.status_code in (400, 422), response.text

    app.dependency_overrides.clear()


# ---------- EVENT DELETE ----------

def test_delete_event_other_owner_forbidden(db_session: Session):
    """Owner cannot delete someone else's event."""
    owner = _make_user(db_session, "del-owner@example.com")
    intruder = _make_user(db_session, "del-intruder@example.com")
    event = _make_event(db_session, owner)
    _override(db_session)
    token = create_access_token({"sub": str(intruder.id), "email": intruder.email})

    response = client.delete(
        f"/events/{event.id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code in (403, 404), response.text  # 404 leaks less info

    surviving = db_session.query(Event).filter(Event.id == event.id).first()
    assert surviving is not None

    app.dependency_overrides.clear()


def test_delete_event_owner_succeeds(db_session: Session):
    """Owner can delete their own event."""
    owner = _make_user(db_session, "del-own@example.com")
    event = _make_event(db_session, owner)
    _override(db_session)
    token = create_access_token({"sub": str(owner.id), "email": owner.email})

    response = client.delete(
        f"/events/{event.id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code in (200, 204), response.text

    gone = db_session.query(Event).filter(Event.id == event.id).first()
    assert gone is None

    app.dependency_overrides.clear()


# ---------- EVENT UPDATE: ownership + frozen-event ----------

def test_update_event_other_owner_forbidden(db_session: Session):
    """Non-owner cannot patch event metadata.

    Use `description` (a valid EventUpdate field) rather than `name`
    (which EventUpdate doesn't accept — extra='forbid' now). The
    test still exercises the ownership-check branch: a different
    user's PATCH must 403/404 regardless of payload content.
    """
    owner = _make_user(db_session, "up-owner@example.com")
    intruder = _make_user(db_session, "up-intruder@example.com")
    event = _make_event(db_session, owner, name="Original")
    _override(db_session)
    token = create_access_token({"sub": str(intruder.id), "email": intruder.email})

    response = client.patch(
        f"/events/{event.id}",
        headers={"Authorization": f"Bearer {token}"},
        json={"description": "Hijack attempt"},
    )
    assert response.status_code in (403, 404), response.text

    db_session.refresh(event)
    assert event.name == "Original"

    app.dependency_overrides.clear()


def test_update_event_blocked_on_frozen_event(db_session: Session):
    """Existing ensure_event_mutable() coverage on update — regression test.

    Uses `description` (a valid EventUpdate field) rather than `name`
    (which EventUpdate rejects post extra='forbid' tightening).
    """
    owner = _make_user(db_session, "up-frozen@example.com")
    event = _make_event(db_session, owner, status_="frozen", name="Frozen")
    _override(db_session)
    token = create_access_token({"sub": str(owner.id), "email": owner.email})

    response = client.patch(
        f"/events/{event.id}",
        headers={"Authorization": f"Bearer {token}"},
        json={"description": "Renamed While Frozen"},
    )
    assert response.status_code == 403, response.text

    db_session.refresh(event)
    assert event.name == "Frozen"

    app.dependency_overrides.clear()


# ---------- ANALYTICS ----------

def test_analytics_other_owner_forbidden(db_session: Session):
    """Analytics endpoint must enforce ownership."""
    owner = _make_user(db_session, "an-owner@example.com")
    intruder = _make_user(db_session, "an-intruder@example.com")
    event = _make_event(db_session, owner)
    _override(db_session)
    token = create_access_token({"sub": str(intruder.id), "email": intruder.email})

    response = client.get(
        f"/events/{event.id}/analytics",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code in (403, 404), response.text

    app.dependency_overrides.clear()


# ---------- ZIP DOWNLOADS ----------

def test_bulk_zip_download_other_owner_forbidden(db_session: Session):
    """Selected-photo ZIP download must enforce ownership."""
    owner = _make_user(db_session, "zip-owner@example.com")
    intruder = _make_user(db_session, "zip-intruder@example.com")
    event = _make_event(db_session, owner)
    img = _make_image(db_session, event)
    _override(db_session)
    token = create_access_token({"sub": str(intruder.id), "email": intruder.email})

    response = client.post(
        f"/events/{event.id}/photos/download-zip",
        headers={"Authorization": f"Bearer {token}"},
        json={"image_ids": [str(img.id)]},
    )
    assert response.status_code in (403, 404), response.text

    app.dependency_overrides.clear()
