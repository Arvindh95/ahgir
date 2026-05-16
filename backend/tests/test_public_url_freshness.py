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


def test_owner_thumb_serves_pending_image(client, db_session: Session):
    """owner_thumb URLs are minted by the authenticated owner photo list
    so the photographer sees their just-uploaded photos before the
    worker has flipped status to 'indexed'. The bytes are written
    synchronously on upload; only face indexing is async. Pre-fix the
    owner saw a broken-image icon for the seconds-to-minutes the photo
    sat in the worker queue.
    """
    event, image = _seed(db_session, event_status="active", image_status="pending")

    path = _signed_path(event.id, image.id, "owner_thumb")
    with patch.object(storage_service, "get_photo", return_value=b"fake-jpeg-bytes"):
        r = client.get(path)
    assert r.status_code == 200
    assert r.content == b"fake-jpeg-bytes"


def test_owner_original_serves_failed_image(client, db_session: Session):
    """Failed-indexing photos still have valid bytes in MinIO — the
    failure is in face indexing, not in the file itself. The owner
    must be able to view + download to decide whether to retry or
    delete."""
    event, image = _seed(db_session, event_status="active", image_status="failed")

    path = _signed_path(event.id, image.id, "owner_original")
    with patch.object(storage_service, "get_photo", return_value=b"fake-jpeg-bytes"):
        r = client.get(path)
    assert r.status_code == 200


def test_owner_thumb_serves_frozen_event(client, db_session: Session):
    """Owner-context URLs must continue to work after the event freezes
    (paid plan expired / manual freeze) so the photographer can still
    download or export photos. Only guest-facing thumb/original URLs
    are blocked when the event is non-active."""
    event, image = _seed(db_session, event_status="frozen", image_status="indexed")

    path = _signed_path(event.id, image.id, "owner_thumb")
    with patch.object(storage_service, "get_photo", return_value=b"fake-jpeg-bytes"):
        r = client.get(path)
    assert r.status_code == 200


def test_owner_thumb_still_404s_when_image_deleted(client, db_session: Session):
    """Even with the relaxed status gate, owner_* must still 404 when
    the underlying image row is gone — otherwise a stale signed URL
    would keep serving bytes after deletion."""
    event, image = _seed(db_session, event_status="active", image_status="indexed")
    path = _signed_path(event.id, image.id, "owner_thumb")
    db_session.delete(image)
    db_session.commit()
    with patch.object(storage_service, "get_photo", return_value=b"fake-jpeg-bytes"):
        r = client.get(path)
    assert r.status_code == 404


def test_signed_url_serves_cover_with_event_id_sentinel(client, db_session: Session):
    """Covers are event-scoped (one per event); generate_signed_cover_url
    encodes the event_id in BOTH the event_id and image_id positions of
    the URL. There is no Image row with id == event_id, so the photo
    route's image-status check must skip when photo_type == 'cover'.
    Pre-fix regression: the new DB check 404'd every cover URL, breaking
    the "Customize Landing Page" cover thumbnail.
    """
    user = User(
        email=f"cov-{uuid.uuid4().hex}@example.com",
        password_hash=hash_password("x"),
        is_verified=True,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)

    event = Event(
        owner_user_id=user.id,
        slug=f"cov-{uuid.uuid4().hex[:8]}",
        name="Cover test",
        retention_days=30,
        status="active",
        cover_image=f"events/cover-key.jpg",
    )
    db_session.add(event)
    db_session.commit()
    db_session.refresh(event)

    path = _signed_path(event.id, event.id, "cover")
    with patch.object(storage_service, "get_photo", return_value=b"fake-cover-bytes"):
        r = client.get(path)
    assert r.status_code == 200, r.text
    assert r.content == b"fake-cover-bytes"


def test_signed_cover_url_rejected_when_event_frozen(client, db_session: Session):
    """Cover requests must still be gated by event.status. Skipping the
    image lookup for covers doesn't mean we skip the event check.
    """
    user = User(
        email=f"cov-{uuid.uuid4().hex}@example.com",
        password_hash=hash_password("x"),
        is_verified=True,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)

    event = Event(
        owner_user_id=user.id,
        slug=f"cov-{uuid.uuid4().hex[:8]}",
        name="Frozen cover",
        retention_days=30,
        status="frozen",
        cover_image=f"events/cover-key.jpg",
    )
    db_session.add(event)
    db_session.commit()
    db_session.refresh(event)

    path = _signed_path(event.id, event.id, "cover")
    with patch.object(storage_service, "get_photo", return_value=b"fake-cover-bytes"):
        r = client.get(path)
    assert r.status_code == 404


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


def test_debug_reindex_invalidates_gallery_and_share_caches(monkeypatch):
    """Same cache-clear behaviour as the regular /events/{id}/reindex
    path. Pre-fix the debug path left stale guest payloads in Redis
    until TTL expired.

    The HTTP endpoint uses ``SessionLocal()`` directly (not the
    request-scoped ``get_db`` dependency), so the standard client+
    db_session test fixtures point at different databases. We bypass
    the HTTP layer and invoke the function directly with a mocked
    SessionLocal so the assertion is solely about the cache invalidation
    behaviour, not the route plumbing.
    """
    import asyncio
    from app.routers import health as health_module

    seen_patterns: list[str] = []
    enqueued: list[str] = []

    def _record_pattern(pattern: str) -> int:
        seen_patterns.append(pattern)
        return 0

    monkeypatch.setattr(
        "app.routers.health.cache_delete_pattern", _record_pattern
    )
    monkeypatch.setattr(
        "app.queue.enqueue_face_indexing",
        lambda image_id: enqueued.append(image_id) or "test-job-id",
    )

    event_uuid = uuid.uuid4()
    image_uuid = uuid.uuid4()

    # Fake SessionLocal — returns an object that responds to .execute()
    # the way SQLAlchemy's Connection does. The endpoint only needs:
    #   1. a SELECT for events.id by slug
    #   2. a SELECT for images by event_id + status
    #   3. an UPDATE images SET status='pending' ...
    #   4. a DELETE FROM faces WHERE image_id = ...
    #   5. commit + close
    class _Row:
        def __init__(self, **kw):
            self.__dict__.update(kw)

    class _FakeDb:
        def __init__(self):
            self.executed: list[str] = []

        def execute(self, stmt, params=None):  # noqa: ARG002
            sql = str(stmt).lower()
            self.executed.append(sql)

            class _Result:
                def fetchone(_self):
                    if "from events where slug" in sql:
                        return _Row(id=event_uuid)
                    return None

                def fetchall(_self):
                    if "from images" in sql:
                        return [_Row(id=image_uuid, filename="x.jpg")]
                    return []

            return _Result()

        def commit(self):
            pass

        def close(self):
            pass

    monkeypatch.setattr("app.database.SessionLocal", _FakeDb)

    result = asyncio.run(
        health_module.reindex_event_images("doesnt-matter-slug", status_filter="no_faces", _superadmin=object())
    )

    assert result["queued_count"] == 1
    assert str(image_uuid) in enqueued

    expected = {
        f"gallery:{event_uuid}:*",
        f"share:{event_uuid}:*",
    }
    actual = set(seen_patterns)
    missing = expected - actual
    assert not missing, (
        f"debug reindex must invalidate gallery + share caches; missing: {missing}"
    )
