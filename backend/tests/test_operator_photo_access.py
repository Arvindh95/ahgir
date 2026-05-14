"""
Regression tests for the authorization-matrix / operator-access review.

The public privacy and security copy promises:
    "The in-app admin console exposes only event metadata to authorised
    superadmins. There is no photo viewer for staff anywhere in the app."

P2 - The photo-list endpoint (events.py /events/{id}/photos) must
     return metadata only when the caller is a non-owner superadmin:
     thumbnail_url and download_url must be NULL. Owners still get
     full URLs.

P2 - The ZIP-download endpoints (/events/{id}/photos/download-zip
     and /events/{id}/photos/download-all-zip) must hard 403 when
     the caller is a non-owner superadmin, and log a
     superadmin_photo_download_blocked audit row so the operator-
     access policy is enforceable AND auditable.
"""
import uuid
from datetime import datetime, timedelta

import pytest
from sqlalchemy.orm import Session

from app.auth import create_access_token, hash_password
from app.models import AuditLog, Event, Image, User


def _make_owner_with_event_and_image(db: Session) -> tuple[User, Event, Image]:
    owner = User(
        email=f"own-{uuid.uuid4().hex}@example.com",
        password_hash=hash_password("x"),
        is_verified=True,
    )
    db.add(owner)
    db.commit()
    db.refresh(owner)

    event = Event(
        owner_user_id=owner.id,
        slug=f"opa-{uuid.uuid4().hex[:8]}",
        name="Operator-access test event",
        retention_days=30,
        status="active",
    )
    db.add(event)
    db.commit()
    db.refresh(event)

    image = Image(
        event_id=event.id,
        filename=f"f-{uuid.uuid4().hex[:6]}.jpg",
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
    return owner, event, image


def _make_superadmin(db: Session) -> User:
    sa = User(
        email=f"sa-{uuid.uuid4().hex}@example.com",
        password_hash=hash_password("x"),
        is_verified=True,
        is_superadmin=True,
    )
    db.add(sa)
    db.commit()
    db.refresh(sa)
    return sa


def _token(user: User) -> str:
    return create_access_token(
        data={"sub": str(user.id), "email": user.email},
        expires_delta=timedelta(hours=1),
    )


# ─── P2 #1: list_photos strips URLs for non-owner superadmin ──────────────


def test_list_photos_strips_urls_for_non_owner_superadmin(client, db_session: Session):
    """The public promise: operators see metadata, never photos. A
    superadmin's photo list response must have thumbnail_url and
    download_url == null."""
    owner, event, image = _make_owner_with_event_and_image(db_session)
    superadmin = _make_superadmin(db_session)

    r = client.get(
        f"/events/{event.id}/photos",
        headers={"Authorization": f"Bearer {_token(superadmin)}"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total"] == 1
    photo = body["photos"][0]
    # Metadata still surfaced
    assert photo["image_id"] == str(image.id)
    assert photo["filename"] == image.filename
    assert photo["status"] == "indexed"
    # But the URLs MUST be stripped
    assert photo["thumbnail_url"] is None, (
        "operator view must NOT include thumbnail_url — the public "
        "privacy promise says there is no photo viewer for staff"
    )
    assert photo["download_url"] is None


def test_list_photos_keeps_urls_for_owner(client, db_session: Session):
    """The owner of the event sees their own photos with URLs."""
    owner, event, _image = _make_owner_with_event_and_image(db_session)

    r = client.get(
        f"/events/{event.id}/photos",
        headers={"Authorization": f"Bearer {_token(owner)}"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["photos"][0]["thumbnail_url"] is not None
    assert body["photos"][0]["download_url"] is not None


# ─── P2 #2: ZIP downloads blocked for non-owner superadmin ────────────────


def test_admin_download_zip_blocks_non_owner_superadmin(client, db_session: Session):
    owner, event, image = _make_owner_with_event_and_image(db_session)
    superadmin = _make_superadmin(db_session)

    r = client.post(
        f"/events/{event.id}/photos/download-zip",
        json={"image_ids": [str(image.id)]},
        headers={"Authorization": f"Bearer {_token(superadmin)}"},
    )
    assert r.status_code == 403, r.text
    body = r.json()
    # Standardised error envelope with the policy-specific code
    assert body["error"]["code"] == "OPERATOR_PHOTO_ACCESS_DENIED"

    # And it left an audit trail
    blocked = (
        db_session.query(AuditLog)
        .filter(
            AuditLog.event_id == event.id,
            AuditLog.action == "superadmin_photo_download_blocked",
        )
        .all()
    )
    assert len(blocked) == 1
    assert blocked[0].actor_id == superadmin.id


def test_admin_download_all_zip_blocks_non_owner_superadmin(client, db_session: Session):
    owner, event, _image = _make_owner_with_event_and_image(db_session)
    superadmin = _make_superadmin(db_session)

    r = client.post(
        f"/events/{event.id}/photos/download-all-zip",
        headers={"Authorization": f"Bearer {_token(superadmin)}"},
    )
    assert r.status_code == 403, r.text
    body = r.json()
    assert body["error"]["code"] == "OPERATOR_PHOTO_ACCESS_DENIED"

    blocked = (
        db_session.query(AuditLog)
        .filter(
            AuditLog.event_id == event.id,
            AuditLog.action == "superadmin_photo_download_blocked",
        )
        .all()
    )
    assert len(blocked) == 1
    assert blocked[0].metadata_["operation"] == "admin_download_all_zip"


def test_admin_download_zip_works_for_owner(client, db_session: Session):
    """Owners must keep their normal download capability. This test
    confirms the policy gate is keyed on cross-tenant access, not
    blanket-disabling ZIP for everyone.
    """
    owner, event, image = _make_owner_with_event_and_image(db_session)

    r = client.post(
        f"/events/{event.id}/photos/download-zip",
        json={"image_ids": [str(image.id)]},
        headers={"Authorization": f"Bearer {_token(owner)}"},
    )
    # 200 (stream succeeded) or 500 (MinIO not actually serving the test
    # photo) — either way NOT a 403. The point is the policy gate did
    # not deny the owner.
    assert r.status_code != 403, r.text
