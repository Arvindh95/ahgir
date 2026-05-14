"""
Regression tests for the scalability / hot-path review:

P2 - /events/{id}/reindex is now async. Endpoint enqueues a worker
     task and returns immediately. The actual CompreFace + DB work
     runs in the retention queue. Pre-fix the endpoint blocked for
     potentially minutes on large events.

P2 - /admin/users and /admin/events are paginated server-side.
     Pre-fix they returned every row plus every UserTier and every
     EventTier in one shot.

P3 - audit_logs has composite indexes on (action, timestamp),
     (event_id, action, timestamp), and (actor_type, timestamp) so
     the analytics dashboards stop full-scanning the table.
"""
import uuid
from datetime import timedelta
from unittest.mock import patch

import pytest
from sqlalchemy import inspect
from sqlalchemy.orm import Session

from app.auth import create_access_token, hash_password
from app.models import Event, Image, User, UserTier


# ─── P3: composite indexes are in the ORM metadata ───────────────────────


def test_audit_logs_has_action_timestamp_index(db_session: Session):
    inspector = inspect(db_session.get_bind())
    indexes = inspector.get_indexes("audit_logs")
    names = {idx["name"] for idx in indexes}
    assert "idx_audit_action_timestamp" in names
    assert "idx_audit_event_action_timestamp" in names
    assert "idx_audit_actor_type_timestamp" in names


# ─── P2 #2: /admin/users pagination ──────────────────────────────────────


def _make_superadmin(db: Session) -> tuple[User, str]:
    sa = User(
        email=f"sa-{uuid.uuid4().hex}@example.com",
        password_hash=hash_password("x"),
        is_verified=True,
        is_superadmin=True,
    )
    db.add(sa)
    db.commit()
    db.refresh(sa)
    token = create_access_token(
        data={"sub": str(sa.id), "email": sa.email},
        expires_delta=timedelta(hours=1),
    )
    return sa, token


def test_admin_users_returns_pagination_metadata(client, db_session: Session):
    _sa, token = _make_superadmin(db_session)
    headers = {"Authorization": f"Bearer {token}"}

    r = client.get("/admin/users?limit=10", headers=headers)
    assert r.status_code == 200, r.text
    body = r.json()
    # Pre-fix the response had only {users}. Post-fix the caller can
    # build pagination UI from these fields.
    assert "users" in body
    assert "total" in body
    assert "limit" in body
    assert "offset" in body
    assert body["limit"] == 10
    assert body["offset"] == 0
    assert len(body["users"]) <= 10


def test_admin_users_search_filters_by_email(client, db_session: Session):
    _sa, token = _make_superadmin(db_session)
    headers = {"Authorization": f"Bearer {token}"}

    # Seed 3 users with distinguishable emails
    for label in ("alpha", "bravo", "charlie"):
        u = User(
            email=f"{label}-{uuid.uuid4().hex}@example.com",
            password_hash=hash_password("x"),
            is_verified=True,
        )
        db_session.add(u)
    db_session.commit()

    r = client.get("/admin/users?q=alpha", headers=headers)
    assert r.status_code == 200, r.text
    emails = [u["email"] for u in r.json()["users"]]
    assert all("alpha" in e for e in emails)


def test_admin_users_rejects_invalid_sort(client, db_session: Session):
    _sa, token = _make_superadmin(db_session)
    headers = {"Authorization": f"Bearer {token}"}

    r = client.get("/admin/users?sort=bogus_field", headers=headers)
    assert r.status_code == 422, r.text


def test_admin_users_offset_advances(client, db_session: Session):
    _sa, token = _make_superadmin(db_session)
    headers = {"Authorization": f"Bearer {token}"}

    # Seed 5 users to ensure offset behaves correctly
    for _ in range(5):
        u = User(
            email=f"page-{uuid.uuid4().hex}@example.com",
            password_hash=hash_password("x"),
            is_verified=True,
        )
        db_session.add(u)
    db_session.commit()

    page1 = client.get("/admin/users?limit=2&offset=0", headers=headers).json()
    page2 = client.get("/admin/users?limit=2&offset=2", headers=headers).json()
    page1_ids = {u["user_id"] for u in page1["users"]}
    page2_ids = {u["user_id"] for u in page2["users"]}
    # No overlap between pages
    assert page1_ids & page2_ids == set()


# ─── P2 #2: /admin/events pagination ─────────────────────────────────────


def test_admin_events_returns_pagination_metadata(client, db_session: Session):
    _sa, token = _make_superadmin(db_session)
    headers = {"Authorization": f"Bearer {token}"}

    r = client.get("/admin/events?limit=10", headers=headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert "events" in body
    assert "total" in body
    assert "limit" in body
    assert "offset" in body


def test_admin_events_filter_by_status(client, db_session: Session):
    _sa, token = _make_superadmin(db_session)
    headers = {"Authorization": f"Bearer {token}"}

    owner = User(
        email=f"own-{uuid.uuid4().hex}@example.com",
        password_hash=hash_password("x"),
        is_verified=True,
    )
    db_session.add(owner)
    db_session.commit()
    db_session.refresh(owner)

    active_event = Event(
        owner_user_id=owner.id,
        slug=f"act-{uuid.uuid4().hex[:8]}",
        name="Active event",
        retention_days=30,
        status="active",
    )
    frozen_event = Event(
        owner_user_id=owner.id,
        slug=f"frz-{uuid.uuid4().hex[:8]}",
        name="Frozen event",
        retention_days=30,
        status="frozen",
    )
    db_session.add_all([active_event, frozen_event])
    db_session.commit()

    r = client.get(
        f"/admin/events?event_status=frozen&owner_id={owner.id}",
        headers=headers,
    )
    assert r.status_code == 200, r.text
    events = r.json()["events"]
    # All returned events must be the frozen one
    assert all(e["event_id"] == str(frozen_event.id) for e in events)


# ─── P2 #1: reindex enqueues + returns immediately ───────────────────────


def test_reindex_endpoint_enqueues_async_task(client, db_session: Session):
    """The endpoint must call enqueue_event_reindex and return 200
    promptly, NOT do the CompreFace cleanup inline.
    """
    owner = User(
        email=f"rx-{uuid.uuid4().hex}@example.com",
        password_hash=hash_password("x"),
        is_verified=True,
    )
    db_session.add(owner)
    db_session.commit()
    db_session.refresh(owner)

    event = Event(
        owner_user_id=owner.id,
        slug=f"rx-{uuid.uuid4().hex[:8]}",
        name="Reindex test",
        retention_days=30,
        status="active",
    )
    db_session.add(event)
    db_session.commit()
    db_session.refresh(event)

    token = create_access_token(
        data={"sub": str(owner.id), "email": owner.email},
        expires_delta=timedelta(hours=1),
    )
    headers = {"Authorization": f"Bearer {token}"}

    calls: list[tuple] = []

    def _fake_enqueue(event_id, actor_user_id):
        calls.append((event_id, actor_user_id))
        return "fake-reindex-job-id"

    with patch("app.queue.enqueue_event_reindex", side_effect=_fake_enqueue):
        r = client.post(f"/events/{event.id}/reindex", headers=headers)

    assert r.status_code == 200, r.text
    body = r.json()
    assert "background" in body["message"].lower() or "started" in body["message"].lower()
    assert len(calls) == 1, "endpoint must enqueue exactly one reindex task"
    assert calls[0][0] == str(event.id)
    assert calls[0][1] == str(owner.id)


def test_reindex_endpoint_does_not_call_compreface_inline(client, db_session: Session, monkeypatch):
    """Belt-and-suspenders: even if the worker is absent, httpx.delete
    against CompreFace must NOT be called from the request handler.
    Pre-fix the endpoint looped through every face row and made one
    HTTP call per face with a 10s timeout.
    """
    owner = User(
        email=f"rx2-{uuid.uuid4().hex}@example.com",
        password_hash=hash_password("x"),
        is_verified=True,
    )
    db_session.add(owner)
    db_session.commit()
    db_session.refresh(owner)

    event = Event(
        owner_user_id=owner.id,
        slug=f"rx2-{uuid.uuid4().hex[:8]}",
        name="Reindex inline-check",
        retention_days=30,
        status="active",
    )
    db_session.add(event)
    db_session.commit()
    db_session.refresh(event)

    token = create_access_token(
        data={"sub": str(owner.id), "email": owner.email},
        expires_delta=timedelta(hours=1),
    )
    headers = {"Authorization": f"Bearer {token}"}

    cf_calls = []
    monkeypatch.setattr(
        "app.routers.events.httpx.delete",
        lambda *args, **kwargs: cf_calls.append((args, kwargs)),
    )
    monkeypatch.setattr(
        "app.queue.enqueue_event_reindex",
        lambda *_a, **_k: "fake-job-id",
    )

    r = client.post(f"/events/{event.id}/reindex", headers=headers)
    assert r.status_code == 200, r.text
    assert cf_calls == [], (
        "request handler must not call CompreFace inline anymore — "
        f"got {len(cf_calls)} httpx.delete calls"
    )
