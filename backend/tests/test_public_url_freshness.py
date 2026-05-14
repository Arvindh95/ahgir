"""
Regression tests for the cache / public-URL review:

P3 — Signed photo URLs must reject requests once the event becomes
     non-public OR the image leaves a guest-visible status, even if
     the HMAC signature is still inside its 15-minute window.

P3 — /share/{event_id}/{image_id} must restrict to indexed / no_faces
     images, matching the gallery filter. Pre-fix, knowing an
     image UUID was enough to mint a public signed URL for a pending
     / failed / mid-reindex image.

P3 — The superadmin debug reindex endpoint must invalidate the
     gallery and share caches, matching the regular reindex path.
"""
import uuid
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest
from sqlalchemy.orm import Session

from app.auth import hash_password
from app.models import Event, Image, User
from app.storage import storage_service, generate_signed_url


def _seed(db: Session, *, event_status: str = "active", image_status: str = "indexed") -> tuple[Event, Image]:
    user = User(
        email=f"pub-{uuid.uuid4().hex}@example.com",
        password_hash=hash_password("x"),
        is_verified=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    event = Event(
        owner_user_id=user.id,
        slug=f"pub-{uuid.uuid4().hex[:8]}",
        name="Public-URL test",
        retention_days=30,
        status=event_status,
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
        status=image_status,
        face_count=0,
    )
    db.add(image)
    db.commit()
    db.refresh(image)
    return event, image


def _signed_path(event_id: uuid.UUID, image_id: uuid.UUID, photo_type: str = "thumb") -> str:
    """Build the request path TestClient should hit.

    generate_signed_url returns the full URL the BROWSER hits — i.e.,
    ``{frontend_url}/api/photos/...``. The ``/api/`` prefix is stripped
    by Caddy / nginx at the edge before reaching the FastAPI app, so
    the in-process route is mounted at ``/photos/...``. For TestClient
    we need to peel both the host AND the /api segment.
    """
    from urllib.parse import urlparse

    full = generate_signed_url(event_id=event_id, image_id=image_id, photo_type=photo_type)
    if full.startswith("http"):
        u = urlparse(full)
        path = u.path
        query = u.query
    else:
        # Unexpected — generate_signed_url normally returns http(s)://...
        path, _, query = full.partition("?")
    if path.startswith("/api/"):
        path = path[4:]  # /api/photos/... -> /photos/...
    return f"{path}?{query}" if query else path


# ─── P3 #1: signed photo URL rejects frozen event ────────────────────────


def test_signed_url_rejects_when_event_is_frozen(client, db_session: Session):
    event, image = _seed(db_session, event_status="frozen", image_status="indexed")

    path = _signed_path(event.id, image.id, "thumb")
    with patch.object(storage_service, "get_photo", return_value=b"fake-jpeg-bytes"):
        r = client.get(path)
    assert r.status_code == 404, (
        f"frozen event must reject signed photo URLs even when the signature "
        f"is still valid — got {r.status_code}"
    )


def test_signed_url_rejects_when_image_status_pending(client, db_session: Session):
    """During reindex, an image's status drops back to 'pending'. A
    pre-issued signed URL must stop serving bytes for that image —
    otherwise a guest can still pull the photo while it's mid-reindex.
    """
    event, image = _seed(db_session, event_status="active", image_status="pending")

    path = _signed_path(event.id, image.id, "thumb")
    with patch.object(storage_service, "get_photo", return_value=b"fake-jpeg-bytes"):
        r = client.get(path)
    assert r.status_code == 404


def test_signed_url_rejects_when_image_status_failed(client, db_session: Session):
    event, image = _seed(db_session, event_status="active", image_status="failed")

    path = _signed_path(event.id, image.id, "thumb")
    with patch.object(storage_service, "get_photo", return_value=b"fake-jpeg-bytes"):
        r = client.get(path)
    assert r.status_code == 404


def test_signed_url_serves_when_event_active_and_image_indexed(client, db_session: Session):
    event, image = _seed(db_session, event_status="active", image_status="indexed")

    path = _signed_path(event.id, image.id, "thumb")
    with patch.object(storage_service, "get_photo", return_value=b"fake-jpeg-bytes"):
        r = client.get(path)
    assert r.status_code == 200
    assert r.content == b"fake-jpeg-bytes"


def test_signed_url_serves_when_image_no_faces(client, db_session: Session):
    """no_faces is a legitimate end state — image was scanned, no faces
    found, still shown in the gallery as a regular photo. Must serve.
    """
    event, image = _seed(db_session, event_status="active", image_status="no_faces")

    path = _signed_path(event.id, image.id, "thumb")
    with patch.object(storage_service, "get_photo", return_value=b"fake-jpeg-bytes"):
        r = client.get(path)
    assert r.status_code == 200


# ─── P3 #2: /share restricts to guest-visible statuses ────────────────────


def test_share_rejects_pending_image(client, db_session: Session):
    event, image = _seed(db_session, event_status="active", image_status="pending")

    r = client.get(f"/share/{event.id}/{image.id}")
    assert r.status_code == 404, (
        f"pending images must not mint share previews — got {r.status_code}"
    )


def test_share_rejects_failed_image(client, db_session: Session):
    event, image = _seed(db_session, event_status="active", image_status="failed")

    r = client.get(f"/share/{event.id}/{image.id}")
    assert r.status_code == 404


def test_share_serves_indexed_image(client, db_session: Session):
    event, image = _seed(db_session, event_status="active", image_status="indexed")

    r = client.get(f"/share/{event.id}/{image.id}")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["event_slug"] == event.slug


def test_share_rejects_frozen_event(client, db_session: Session):
    event, image = _seed(db_session, event_status="frozen", image_status="indexed")
    r = client.get(f"/share/{event.id}/{image.id}")
    assert r.status_code == 404


# ─── P3 #3: superadmin debug reindex invalidates caches ───────────────────


def test_debug_reindex_invalidates_gallery_and_share_caches(client, db_session: Session, monkeypatch):
    """Same cache-clear behaviour as the regular /events/{id}/reindex
    path. Pre-fix the debug path left stale guest payloads in Redis
    until TTL expired.
    """
    # We mock cache_delete_pattern so the test doesn't need a real
    # Redis; the assertion is just "the patterns we expect were
    # requested". The endpoint imports the function lazily inside the
    # function body, so patch the source module.
    seen_patterns: list[str] = []

    def _record(pattern: str) -> int:
        seen_patterns.append(pattern)
        return 0

    # Patch at health.py's namespace because that's where the symbol is
    # bound (module-level import). Patching app.cache.cache_delete_pattern
    # would not affect references already captured at import time.
    monkeypatch.setattr("app.routers.health.cache_delete_pattern", _record)
    # health.py also imports enqueue_face_indexing lazily inside the
    # function body; stub at the source so the lazy import picks it up.
    monkeypatch.setattr("app.queue.enqueue_face_indexing", lambda *_a, **_k: "test-job-id")

    # Make a superadmin user, log in, and seed an event with one
    # no_faces image (the default status_filter on the debug endpoint).
    superadmin = User(
        email=f"super-{uuid.uuid4().hex}@example.com",
        password_hash=hash_password("x"),
        is_verified=True,
        is_superadmin=True,
    )
    db_session.add(superadmin)
    db_session.commit()
    db_session.refresh(superadmin)

    event = Event(
        owner_user_id=superadmin.id,
        slug=f"sa-{uuid.uuid4().hex[:8]}",
        name="Debug reindex event",
        retention_days=30,
        status="active",
    )
    db_session.add(event)
    db_session.commit()
    db_session.refresh(event)

    image = Image(
        event_id=event.id,
        filename="x.jpg",
        file_hash=uuid.uuid4().hex + uuid.uuid4().hex,
        size_bytes=100,
        width=100,
        height=100,
        status="no_faces",
        face_count=0,
    )
    db_session.add(image)
    db_session.commit()

    # /health/debug/reindex/{slug} requires the get_superadmin_user
    # dependency. We need a JWT for the superadmin.
    from app.auth import create_access_token
    from datetime import timedelta as _td

    token = create_access_token(
        data={"sub": str(superadmin.id), "email": superadmin.email},
        expires_delta=_td(hours=1),
    )

    r = client.post(
        f"/health/debug/reindex/{event.slug}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200, r.text

    expected = {
        f"gallery:{event.id}:*",
        f"share:{event.id}:*",
    }
    actual = set(seen_patterns)
    missing = expected - actual
    assert not missing, (
        f"debug reindex must invalidate gallery + share caches; missing: {missing}"
    )
