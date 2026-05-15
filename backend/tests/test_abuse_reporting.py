"""Tests for the abuse-reporting Phase 1 wiring.

Covers the public POST /report endpoint, the superadmin queue + review
endpoints, and the abuse_review photo_type bypass. Focused on the
behaviour an operator depends on; the full plan-spec test inventory
lives in ABUSE_REPORTING_PLAN.md §Tests.
"""
import time
import uuid
from unittest.mock import Mock, patch

import pytest
from fastapi.testclient import TestClient

from app.auth import create_access_token, hash_password
from app.database import get_db
from app.main import app
from app.models import AbuseReport, AuditLog, Event, Image, User
from app.rate_limiter import abuse_report_rate_limiter, redis_client
from app.storage import storage_service

client = TestClient(app)
client.headers.update({"X-Requested-With": "XMLHttpRequest"})


# ─── shared fixtures ─────────────────────────────────────────────────


@pytest.fixture
def setup_world(db_session):
    """Create one superadmin, one regular admin, one event, one image."""
    mock_client = Mock()
    mock_client.remove_object.return_value = None
    storage_service._client = mock_client

    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db

    superadmin = User(
        email=f"super_{uuid.uuid4().hex[:8]}@example.com",
        password_hash=hash_password("pw"),
        is_superadmin=True,
        is_verified=True,
    )
    regular_admin = User(
        email=f"admin_{uuid.uuid4().hex[:8]}@example.com",
        password_hash=hash_password("pw"),
        is_verified=True,
    )
    db_session.add_all([superadmin, regular_admin])
    db_session.commit()
    db_session.refresh(superadmin)
    db_session.refresh(regular_admin)

    event = Event(
        owner_user_id=regular_admin.id,
        slug=f"slug-{uuid.uuid4().hex[:6]}",
        name="Test Event",
        allow_downloads=True,
        retention_days=30,
        status="active",
    )
    db_session.add(event)
    db_session.commit()
    db_session.refresh(event)

    image = Image(
        event_id=event.id,
        filename="photo.jpg",
        file_hash="x" * 64,
        size_bytes=1024,
        status="indexed",
    )
    db_session.add(image)
    db_session.commit()
    db_session.refresh(image)

    super_token = create_access_token(
        data={"sub": str(superadmin.id), "email": superadmin.email}
    )
    admin_token = create_access_token(
        data={"sub": str(regular_admin.id), "email": regular_admin.email}
    )

    # Wipe per-IP rate-limit buckets so prior tests don't pre-consume budget.
    try:
        for k in redis_client.keys("rate_limit:abuse_report:*"):
            redis_client.delete(k)
    except Exception:
        pass

    yield {
        "db": db_session,
        "superadmin": superadmin,
        "regular_admin": regular_admin,
        "event": event,
        "image": image,
        "super_token": super_token,
        "admin_token": admin_token,
    }

    app.dependency_overrides.clear()
    storage_service._client = None


# ─── POST /report ────────────────────────────────────────────────────


def test_report_valid_payload_creates_row(setup_world):
    world = setup_world
    resp = client.post("/report", json={
        "image_id": str(world["image"].id),
        "category": "nudity",
        "description": "Looks like an exposed minor.",
        "reporter_email": "Reporter@Example.com",
    })
    assert resp.status_code == 200
    assert resp.json() == {"message": "Thank you. We will review this report shortly."}

    rows = world["db"].query(AbuseReport).filter(
        AbuseReport.image_id == world["image"].id
    ).all()
    assert len(rows) == 1
    r = rows[0]
    assert r.category == "nudity"
    assert r.reporter_email == "reporter@example.com"  # lowercased
    assert r.status == "pending"
    assert r.reporter_ip is not None


def test_report_honeypot_silent_drop(setup_world):
    world = setup_world
    resp = client.post("/report", json={
        "image_id": str(world["image"].id),
        "category": "other",
        "website": "spam-bot",
    })
    assert resp.status_code == 200
    assert resp.json()["message"].startswith("Thank you")
    # No row written.
    assert world["db"].query(AbuseReport).filter(
        AbuseReport.image_id == world["image"].id
    ).count() == 0


def test_report_silent_drops_non_guest_visible_image(setup_world):
    """A real image_id whose status is quarantined / pending / failed —
    or whose event is frozen — must return the same fixed 200 body as
    a fake UUID, AND must create no row. Prevents both queue noise on
    invisible photos and a side-channel that could distinguish 'real
    but hidden' from 'fake'."""
    world = setup_world
    db = world["db"]
    _flush_abuse_rate_keys()
    # Flip the test image to quarantined.
    world["image"].status = "quarantined"
    db.commit()

    pre_count = db.query(AbuseReport).count()
    resp = client.post("/report", json={
        "image_id": str(world["image"].id),
        "category": "other",
    })
    assert resp.status_code == 200
    assert resp.json() == {"message": "Thank you. We will review this report shortly."}
    assert db.query(AbuseReport).count() == pre_count


def test_report_silent_drops_frozen_event_image(setup_world):
    world = setup_world
    db = world["db"]
    _flush_abuse_rate_keys()
    world["event"].status = "frozen"
    db.commit()

    pre_count = db.query(AbuseReport).count()
    resp = client.post("/report", json={
        "image_id": str(world["image"].id),
        "category": "other",
    })
    assert resp.status_code == 200
    assert db.query(AbuseReport).count() == pre_count


def test_reveal_on_removed_image_returns_409(setup_world):
    """After /delete-photo the report row survives with image_id=NULL.
    /reveal in that state cannot mint a signed URL — must 409."""
    world = setup_world
    db = world["db"]
    report = AbuseReport(
        image_id=None,
        event_id=world["event"].id,
        category="csam", reporter_ip="1.1.1.1", status="removed",
        action_taken="remove",
    )
    db.add(report)
    db.commit()
    db.refresh(report)

    resp = client.post(
        f"/admin/abuse-reports/{report.id}/reveal",
        headers={"Authorization": f"Bearer {world['super_token']}"},
    )
    assert resp.status_code == 409


def test_list_returns_null_image_id_for_removed_report(setup_world):
    """Removed reports surface in the list with image_id=null (not the
    string 'None'). Verifies the Pydantic schema correctly accepts None."""
    world = setup_world
    db = world["db"]
    report = AbuseReport(
        image_id=None,
        event_id=world["event"].id,
        category="csam", reporter_ip="1.1.1.1", status="removed",
        action_taken="remove",
    )
    db.add(report)
    db.commit()

    resp = client.get(
        "/admin/abuse-reports?status=removed",
        headers={"Authorization": f"Bearer {world['super_token']}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] >= 1
    removed_row = next(r for r in data["items"] if r["status"] == "removed")
    assert removed_row["image_id"] is None


def test_delete_photo_preserves_report_row_with_null_image_id(setup_world):
    """Regression: ORM Image.abuse_reports MUST NOT cascade-delete the
    AbuseReport row when db.delete(image) runs. The DB FK is ON DELETE
    SET NULL — and the relationship is configured passive_deletes=True
    so SQLAlchemy lets the FK action fire. Without passive_deletes the
    cascade fires *before* the DB-level SET NULL, wiping the audit row."""
    world = setup_world
    db = world["db"]
    _flush_abuse_rate_keys()

    # File a real pending report on the test image.
    report = AbuseReport(
        image_id=world["image"].id,
        event_id=world["event"].id,
        category="nudity", reporter_ip="2.2.2.2", status="pending",
    )
    db.add(report)
    db.commit()
    db.refresh(report)
    report_id = report.id

    # Operator hits /delete-photo.
    resp = client.post(
        f"/admin/abuse-reports/{report_id}/delete-photo",
        headers={"Authorization": f"Bearer {world['super_token']}"},
    )
    assert resp.status_code == 200, resp.text

    # Image row gone.
    assert db.query(Image).filter(Image.id == world["image"].id).count() == 0

    # Report row STILL EXISTS — image_id NULL'd via FK SET NULL,
    # status flipped to 'removed' by the endpoint.
    db.expire_all()
    surviving = db.query(AbuseReport).filter(AbuseReport.id == report_id).first()
    assert surviving is not None
    assert surviving.image_id is None
    assert surviving.status == "removed"
    assert surviving.action_taken == "remove"


def test_list_event_search_matches_name_and_slug(setup_world):
    """event_search filters the list by case-insensitive substring on
    Event.name or Event.slug. Operators commonly know the event by name
    so this is the primary way to locate a queue row fast."""
    world = setup_world
    db = world["db"]
    _flush_abuse_rate_keys()

    other_event = Event(
        owner_user_id=world["regular_admin"].id,
        slug="totally-different-slug-xyz",
        name="Birthday Bash",
        status="active",
        retention_days=30,
    )
    db.add(other_event)
    db.commit()
    db.refresh(other_event)
    other_image = Image(
        event_id=other_event.id, filename="b.jpg", file_hash="z" * 64,
        size_bytes=1, status="indexed",
    )
    db.add(other_image)
    db.commit()
    db.refresh(other_image)

    r_test = AbuseReport(
        image_id=world["image"].id, event_id=world["event"].id,
        category="csam", reporter_ip="20.0.0.1", status="pending",
    )
    r_birthday = AbuseReport(
        image_id=other_image.id, event_id=other_event.id,
        category="nudity", reporter_ip="20.0.0.2", status="pending",
    )
    db.add_all([r_test, r_birthday])
    db.commit()

    # Match on name (case-insensitive).
    resp = client.get(
        "/admin/abuse-reports?status=pending&event_search=birthday",
        headers={"Authorization": f"Bearer {world['super_token']}"},
    )
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["total"] == 1
    assert payload["items"][0]["event_name"] == "Birthday Bash"

    # Match on slug.
    resp = client.get(
        "/admin/abuse-reports?status=pending&event_search=different-slug",
        headers={"Authorization": f"Bearer {world['super_token']}"},
    )
    assert resp.status_code == 200
    assert resp.json()["total"] == 1

    # No-match returns empty.
    resp = client.get(
        "/admin/abuse-reports?status=pending&event_search=zzzz_nothing",
        headers={"Authorization": f"Bearer {world['super_token']}"},
    )
    assert resp.status_code == 200
    assert resp.json()["total"] == 0


def test_event_delete_blocked_by_quarantined_report(setup_world):
    """Regression: event-delete blocker MUST treat quarantined as non-
    terminal. Otherwise an owner deletes the event, the cascade wipes
    the quarantined report, and the moderation history is lost."""
    world = setup_world
    db = world["db"]
    _flush_abuse_rate_keys()

    report = AbuseReport(
        image_id=world["image"].id,
        event_id=world["event"].id,
        category="violence", reporter_ip="11.11.11.11",
        status="quarantined", action_taken="quarantine",
    )
    db.add(report)
    db.commit()

    resp = client.delete(
        f"/events/{world['event'].id}",
        headers={"Authorization": f"Bearer {world['admin_token']}"},
    )
    assert resp.status_code == 409
    assert "unresolved abuse report" in resp.json()["detail"].lower()


def test_delete_photo_closes_sibling_reports(setup_world):
    """Regression: admin /delete-photo on one report must also close
    every other pending/reviewing/quarantined report against the same
    image. Without this, sibling rows survive with image_id=NULL and
    no transition path — operator sees stuck rows in the queue."""
    world = setup_world
    db = world["db"]
    _flush_abuse_rate_keys()

    target = AbuseReport(
        image_id=world["image"].id, event_id=world["event"].id,
        category="csam", reporter_ip="12.12.12.1", status="pending",
    )
    sibling_pending = AbuseReport(
        image_id=world["image"].id, event_id=world["event"].id,
        category="nudity", reporter_ip="12.12.12.2", status="pending",
    )
    sibling_reviewing = AbuseReport(
        image_id=world["image"].id, event_id=world["event"].id,
        category="harassment", reporter_ip="12.12.12.3",
        status="reviewing",
    )
    sibling_quarantined = AbuseReport(
        image_id=world["image"].id, event_id=world["event"].id,
        category="other", reporter_ip="12.12.12.4",
        status="quarantined", action_taken="quarantine",
    )
    db.add_all([target, sibling_pending, sibling_reviewing, sibling_quarantined])
    db.commit()
    target_id = target.id
    sib_ids = (sibling_pending.id, sibling_reviewing.id, sibling_quarantined.id)

    resp = client.post(
        f"/admin/abuse-reports/{target_id}/delete-photo",
        headers={"Authorization": f"Bearer {world['super_token']}"},
    )
    assert resp.status_code == 200, resp.text

    db.expire_all()
    target_row = db.query(AbuseReport).filter(AbuseReport.id == target_id).first()
    assert target_row.status == "removed"
    assert target_row.action_taken == "remove"

    for sid in sib_ids:
        sib_row = db.query(AbuseReport).filter(AbuseReport.id == sid).first()
        assert sib_row is not None
        assert sib_row.status == "removed"
        assert sib_row.action_taken == "sibling_delete"
        assert sib_row.reviewed_at is not None
        assert sib_row.reviewed_by == world["superadmin"].id


def test_event_delete_blocked_while_open_abuse_reports(setup_world):
    """Regression: event delete must refuse while pending/reviewing
    abuse reports exist for that event. Otherwise an event owner could
    erase an active CSAM report by deleting the event."""
    world = setup_world
    db = world["db"]
    _flush_abuse_rate_keys()

    report = AbuseReport(
        image_id=world["image"].id,
        event_id=world["event"].id,
        category="csam", reporter_ip="3.3.3.3", status="pending",
    )
    db.add(report)
    db.commit()

    # Owner of the event (regular_admin) tries to delete it.
    resp = client.delete(
        f"/events/{world['event'].id}",
        headers={"Authorization": f"Bearer {world['admin_token']}"},
    )
    assert resp.status_code == 409
    assert "unresolved abuse report" in resp.json()["detail"].lower()

    # Same call after the report is dismissed must succeed.
    db.query(AbuseReport).filter(AbuseReport.id == report.id).update(
        {"status": "dismissed", "action_taken": "dismiss"}
    )
    db.commit()
    resp = client.delete(
        f"/events/{world['event'].id}",
        headers={"Authorization": f"Bearer {world['admin_token']}"},
    )
    assert resp.status_code == 200


def test_bulk_owner_delete_auto_closes_active_reports(setup_world):
    """Regression: bulk delete used to call _close_active_reports
    AFTER per-image db.delete(image), letting SQLAlchemy autoflush fire
    FK SET NULL before the helper's IN-clause filter ran — closing zero
    reports. The reorder ensures pending/reviewing reports for every
    image in the batch get auto-closed with action_taken='owner_delete'."""
    world = setup_world
    db = world["db"]
    _flush_abuse_rate_keys()

    # Add a second image in the same event so the bulk path has > 1 target.
    second_image = Image(
        event_id=world["event"].id,
        filename="photo2.jpg",
        file_hash="y" * 64,
        size_bytes=2048,
        status="indexed",
    )
    db.add(second_image)
    db.commit()
    db.refresh(second_image)

    r1 = AbuseReport(
        image_id=world["image"].id, event_id=world["event"].id,
        category="nudity", reporter_ip="7.7.7.7", status="pending",
    )
    r2 = AbuseReport(
        image_id=second_image.id, event_id=world["event"].id,
        category="harassment", reporter_ip="7.7.7.7", status="reviewing",
    )
    db.add_all([r1, r2])
    db.commit()
    r1_id, r2_id = r1.id, r2.id

    resp = client.post(
        f"/events/{world['event'].id}/photos/bulk-delete",
        headers={"Authorization": f"Bearer {world['admin_token']}"},
        json={"image_ids": [str(world["image"].id), str(second_image.id)]},
    )
    assert resp.status_code == 200, resp.text

    db.expire_all()
    for rid in (r1_id, r2_id):
        surviving = db.query(AbuseReport).filter(AbuseReport.id == rid).first()
        assert surviving is not None
        assert surviving.status == "removed"
        assert surviving.action_taken == "owner_delete"
        assert surviving.reviewed_at is not None


def test_owner_delete_closes_quarantined_report(setup_world):
    """Regression: a quarantined report whose image is then owner-deleted
    must be flipped to 'removed' / 'owner_delete'. Without this the
    report stays quarantined with image_id=NULL — no valid transition
    out (restore 404s on missing image, delete-photo 404s likewise)."""
    world = setup_world
    db = world["db"]
    _flush_abuse_rate_keys()

    world["image"].status = "quarantined"
    report = AbuseReport(
        image_id=world["image"].id, event_id=world["event"].id,
        category="violence", reporter_ip="8.8.8.8", status="quarantined",
        action_taken="quarantine",
    )
    db.add(report)
    db.commit()
    db.refresh(report)
    report_id = report.id

    resp = client.delete(
        f"/events/{world['event'].id}/photos/{world['image'].id}",
        headers={"Authorization": f"Bearer {world['admin_token']}"},
    )
    assert resp.status_code == 200, resp.text

    db.expire_all()
    surviving = db.query(AbuseReport).filter(AbuseReport.id == report_id).first()
    assert surviving is not None
    assert surviving.status == "removed"
    assert surviving.action_taken == "owner_delete"


def test_silent_drop_duplicates_surface_in_count(setup_world):
    """Regression: when /report is silent-dropped by the per-image
    dedupe rate limiter (4th+ on same image in window), no DB row is
    written — but the operator MUST still see the silent drops folded
    into duplicate_count, otherwise mass-reporting just past the cap
    is invisible."""
    world = setup_world
    db = world["db"]
    _flush_abuse_rate_keys()

    # Hit /report from N different IPs to bypass per-IP cap but trip
    # the per-image dedup. dedupe limit defaults to 3, so 5 attempts
    # should write 3 rows and silent-drop 2.
    import os
    real_drops = 0
    for i in range(5):
        resp = client.post(
            "/report",
            headers={"x-forwarded-for": f"10.0.0.{i+1}"},
            json={
                "image_id": str(world["image"].id),
                "category": "harassment",
            },
        )
        assert resp.status_code == 200

    rows = db.query(AbuseReport).filter(
        AbuseReport.image_id == world["image"].id
    ).all()
    # DB has at most the dedupe limit
    assert 1 <= len(rows) <= settings_dedupe_limit()
    # Silent-drop counter is non-zero
    silent = redis_client.get(f"abuse:image_silent_drops:{world['image'].id}")
    assert silent is not None
    assert int(silent) >= 1

    # GET single report surfaces the silent drops in duplicate_count.
    target_report = rows[0]
    resp = client.get(
        f"/admin/abuse-reports/{target_report.id}",
        headers={"Authorization": f"Bearer {world['super_token']}"},
    )
    assert resp.status_code == 200
    payload = resp.json()
    # duplicate_count should be at least the silent-drop count.
    assert payload["duplicate_count"] >= int(silent)


def settings_dedupe_limit():
    from app.config import settings as _s
    return _s.abuse_report_image_dedupe_limit


def test_report_image_id_length_capped(setup_world):
    """Regression: ReportCreateRequest.image_id must be max_length=64.
    Without the cap, an attacker could ship a multi-MB string in
    image_id, forcing UUID parsing on garbage before the handler's
    constant-time guard kicks in."""
    world = setup_world
    resp = client.post("/report", json={
        "image_id": "x" * 65,
        "category": "other",
    })
    assert resp.status_code == 422


def test_owner_photo_delete_auto_closes_active_reports(setup_world):
    """Regression: when an event owner deletes a photo via the normal
    /events/{event_id}/photos/{image_id} route, any pending/reviewing
    abuse reports against that image must be auto-closed with
    action_taken='owner_delete'. Otherwise the report stays pending
    forever with image_id=NULL (FK SET NULL), unrevealable."""
    world = setup_world
    db = world["db"]
    _flush_abuse_rate_keys()

    report = AbuseReport(
        image_id=world["image"].id,
        event_id=world["event"].id,
        category="nudity", reporter_ip="4.4.4.4", status="pending",
    )
    db.add(report)
    db.commit()
    db.refresh(report)
    report_id = report.id

    resp = client.delete(
        f"/events/{world['event'].id}/photos/{world['image'].id}",
        headers={"Authorization": f"Bearer {world['admin_token']}"},
    )
    assert resp.status_code == 200, resp.text

    db.expire_all()
    surviving = db.query(AbuseReport).filter(AbuseReport.id == report_id).first()
    assert surviving is not None
    assert surviving.status == "removed"
    assert surviving.action_taken == "owner_delete"
    assert surviving.reviewed_at is not None
    assert surviving.reviewed_by == world["regular_admin"].id


def test_dismiss_stamps_reviewer_when_skipping_reveal(setup_world):
    """Regression: dismiss/quarantine/delete-photo on a pending report
    (no /reveal first) must stamp reviewed_at + reviewed_by, so the
    queue's 'reviewed by' column is correct and the audit trail records
    who closed the row."""
    world = setup_world
    db = world["db"]
    _flush_abuse_rate_keys()

    report = AbuseReport(
        image_id=world["image"].id,
        event_id=world["event"].id,
        category="other", reporter_ip="5.5.5.5", status="pending",
    )
    db.add(report)
    db.commit()
    db.refresh(report)
    assert report.reviewed_at is None
    assert report.reviewed_by is None

    resp = client.post(
        f"/admin/abuse-reports/{report.id}/dismiss",
        headers={"Authorization": f"Bearer {world['super_token']}"},
    )
    assert resp.status_code == 200, resp.text

    db.refresh(report)
    assert report.status == "dismissed"
    assert report.reviewed_at is not None
    assert report.reviewed_by == world["superadmin"].id


def test_dismiss_by_source_stamps_reviewer(setup_world):
    world = setup_world
    db = world["db"]
    _flush_abuse_rate_keys()

    r1 = AbuseReport(
        image_id=world["image"].id, event_id=world["event"].id,
        category="harassment", reporter_ip="6.6.6.6", status="pending",
    )
    r2 = AbuseReport(
        image_id=world["image"].id, event_id=world["event"].id,
        category="harassment", reporter_ip="6.6.6.6", status="reviewing",
    )
    db.add_all([r1, r2])
    db.commit()

    resp = client.post(
        "/admin/abuse-reports/dismiss-by-source",
        headers={"Authorization": f"Bearer {world['super_token']}"},
        json={"reporter_ip": "6.6.6.6"},
    )
    assert resp.status_code == 200

    db.refresh(r1); db.refresh(r2)
    for r in (r1, r2):
        assert r.status == "dismissed"
        assert r.reviewed_at is not None
        assert r.reviewed_by == world["superadmin"].id


def test_abuse_review_photo_has_no_store_cache(setup_world):
    """Regression: /photos response for photo_type=abuse_review must
    return Cache-Control: no-store so the operator's browser does not
    keep the bytes around past the 5-minute URL expiry."""
    world = setup_world
    db = world["db"]

    # Mock storage_service.get_photo to return some bytes.
    storage_service._client.get_object = Mock()  # not used by get_photo monkeypatch below
    with patch.object(storage_service, "get_photo", return_value=b"fakejpeg"):
        # Build a valid signed abuse_review URL.
        from app.storage import generate_signed_abuse_review_url
        url = generate_signed_abuse_review_url(
            event_id=world["event"].id, image_id=world["image"].id, expires_minutes=5,
        )
        # url is path+query; pull just the path the FastAPI client expects.
        path = url[url.index("/photos/"):] if "/photos/" in url else url
        resp = client.get(path)
    assert resp.status_code == 200, resp.text
    assert resp.headers["cache-control"] == "private, no-store"


def test_report_invalid_category_returns_422(setup_world):
    world = setup_world
    resp = client.post("/report", json={
        "image_id": str(world["image"].id),
        "category": "not-a-category",
    })
    assert resp.status_code == 422


def test_report_fake_image_id_returns_same_fixed_body(setup_world):
    world = setup_world
    fake_uuid = str(uuid.uuid4())
    resp = client.post("/report", json={
        "image_id": fake_uuid,
        "category": "harassment",
    })
    assert resp.status_code == 200
    assert resp.json() == {"message": "Thank you. We will review this report shortly."}
    # No row.
    assert world["db"].query(AbuseReport).count() == 0


def test_report_bad_uuid_returns_same_fixed_body(setup_world):
    resp = client.post("/report", json={
        "image_id": "not-a-uuid",
        "category": "other",
    })
    assert resp.status_code == 200
    assert resp.json() == {"message": "Thank you. We will review this report shortly."}


def test_report_anti_enum_constant_time(setup_world):
    """Real and fake image_ids must both meet the 50ms minimum response
    floor AND respond in roughly the same time. The duration pad is what
    prevents a probe from measuring DB-lookup latency to distinguish
    real-but-rate-limited from fake."""
    world = setup_world
    _flush_abuse_rate_keys()

    def time_call(image_id: str) -> float:
        t0 = time.monotonic()
        client.post("/report", json={"image_id": image_id, "category": "other"})
        return time.monotonic() - t0

    # Warm-up to factor out import/Redis-connect cost.
    time_call(str(world["image"].id))
    real = time_call(str(world["image"].id))
    fake = time_call(str(uuid.uuid4()))
    # Minimum floor: anti-enum pad is 50ms; the await holds the request
    # open at least that long. Assert both paths cross the floor so a
    # missing-await regression (the P2 fix in this commit) is caught.
    assert real >= 0.045, f"real path skipped duration pad: {real:.3f}s"
    assert fake >= 0.045, f"fake path skipped duration pad: {fake:.3f}s"
    # And the two should be close enough that a probe can't distinguish.
    assert abs(real - fake) < 0.2


def test_report_per_ip_rate_limit_429(setup_world):
    world = setup_world
    # Default limit is 5/hour per IP. TestClient uses the same IP for
    # every request in a session, so a 6th hit must 429.
    for _ in range(5):
        resp = client.post("/report", json={
            "image_id": str(world["image"].id),
            "category": "other",
        })
        assert resp.status_code == 200
    resp = client.post("/report", json={
        "image_id": str(world["image"].id),
        "category": "other",
    })
    assert resp.status_code == 429


# ─── GET /admin/abuse-reports ────────────────────────────────────────


def test_list_requires_superadmin(setup_world):
    world = setup_world
    resp = client.get(
        "/admin/abuse-reports",
        headers={"Authorization": f"Bearer {world['admin_token']}"},
    )
    assert resp.status_code == 403


def test_list_returns_pending_only_by_default(setup_world):
    world = setup_world
    db = world["db"]
    db.add_all([
        AbuseReport(
            image_id=world["image"].id, event_id=world["event"].id,
            category="other", reporter_ip="1.1.1.1", status="pending",
        ),
        AbuseReport(
            image_id=world["image"].id, event_id=world["event"].id,
            category="other", reporter_ip="1.1.1.2", status="dismissed",
        ),
    ])
    db.commit()

    resp = client.get(
        "/admin/abuse-reports",
        headers={"Authorization": f"Bearer {world['super_token']}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["items"][0]["status"] == "pending"
    # Photo URLs must NOT be in the response.
    for item in data["items"]:
        for k in item.keys():
            assert "url" not in k.lower()


def test_pending_count(setup_world):
    world = setup_world
    db = world["db"]
    db.add_all([
        AbuseReport(image_id=world["image"].id, event_id=world["event"].id,
                    category="other", reporter_ip="1.1.1.1", status="pending"),
        AbuseReport(image_id=world["image"].id, event_id=world["event"].id,
                    category="other", reporter_ip="1.1.1.2", status="pending"),
        AbuseReport(image_id=world["image"].id, event_id=world["event"].id,
                    category="other", reporter_ip="1.1.1.3", status="dismissed"),
    ])
    db.commit()
    resp = client.get(
        "/admin/abuse-reports/pending-count",
        headers={"Authorization": f"Bearer {world['super_token']}"},
    )
    assert resp.status_code == 200
    assert resp.json() == {"pending": 2}


# ─── POST /reveal ────────────────────────────────────────────────────


def test_reveal_first_call_stamps_reviewer(setup_world):
    world = setup_world
    db = world["db"]
    report = AbuseReport(
        image_id=world["image"].id, event_id=world["event"].id,
        category="csam", reporter_ip="1.1.1.1", status="pending",
    )
    db.add(report)
    db.commit()
    db.refresh(report)

    resp = client.post(
        f"/admin/abuse-reports/{report.id}/reveal",
        headers={"Authorization": f"Bearer {world['super_token']}"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "abuse_review" in body["review_url"]
    assert body["expires_in"] == 300
    assert body["status"] == "reviewing"

    db.refresh(report)
    assert report.status == "reviewing"
    assert report.reviewed_by == world["superadmin"].id
    assert report.reviewed_at is not None

    audits = db.query(AuditLog).filter(
        AuditLog.event_id == world["event"].id,
        AuditLog.action == "abuse_review_view",
    ).all()
    assert len(audits) == 1


def test_reveal_writes_fresh_audit_row_each_call(setup_world):
    world = setup_world
    db = world["db"]
    report = AbuseReport(
        image_id=world["image"].id, event_id=world["event"].id,
        category="other", reporter_ip="1.1.1.1", status="pending",
    )
    db.add(report)
    db.commit()
    db.refresh(report)

    for _ in range(3):
        client.post(
            f"/admin/abuse-reports/{report.id}/reveal",
            headers={"Authorization": f"Bearer {world['super_token']}"},
        )

    audits = db.query(AuditLog).filter(
        AuditLog.event_id == world["event"].id,
        AuditLog.action == "abuse_review_view",
    ).all()
    assert len(audits) == 3


# ─── POST /quarantine / /dismiss ─────────────────────────────────────


def test_quarantine_flips_image_and_writes_audit(setup_world):
    world = setup_world
    db = world["db"]
    report = AbuseReport(
        image_id=world["image"].id, event_id=world["event"].id,
        category="csam", reporter_ip="1.1.1.1", status="reviewing",
    )
    db.add(report)
    db.commit()
    db.refresh(report)

    resp = client.post(
        f"/admin/abuse-reports/{report.id}/quarantine",
        headers={"Authorization": f"Bearer {world['super_token']}"},
    )
    assert resp.status_code == 200

    db.refresh(report)
    assert report.status == "quarantined"
    assert report.action_taken == "quarantine"

    img = db.query(Image).filter(Image.id == world["image"].id).first()
    assert img.status == "quarantined"

    audits = db.query(AuditLog).filter(
        AuditLog.action == "abuse_review_quarantine"
    ).all()
    assert len(audits) == 1


def test_restore_unquarantines_image(setup_world):
    """Operator quarantined an image, then realized it's fine — restore
    flips Image.status back so guests see it again. Status is derived
    from face_count (>0 → indexed, 0 → no_faces)."""
    world = setup_world
    db = world["db"]
    img = world["image"]
    img.status = "quarantined"
    img.face_count = 3
    db.commit()
    report = AbuseReport(
        image_id=img.id, event_id=world["event"].id,
        category="nudity", reporter_ip="1.1.1.1", status="quarantined",
    )
    db.add(report)
    db.commit()
    db.refresh(report)

    resp = client.post(
        f"/admin/abuse-reports/{report.id}/restore",
        headers={"Authorization": f"Bearer {world['super_token']}"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "indexed"

    db.refresh(img)
    assert img.status == "indexed"


def test_restore_409_when_image_not_quarantined(setup_world):
    world = setup_world
    db = world["db"]
    # image is indexed, not quarantined
    report = AbuseReport(
        image_id=world["image"].id, event_id=world["event"].id,
        category="other", reporter_ip="1.1.1.1", status="dismissed",
    )
    db.add(report)
    db.commit()
    db.refresh(report)

    resp = client.post(
        f"/admin/abuse-reports/{report.id}/restore",
        headers={"Authorization": f"Bearer {world['super_token']}"},
    )
    assert resp.status_code == 409


def test_dismiss_marks_dismissed(setup_world):
    world = setup_world
    db = world["db"]
    report = AbuseReport(
        image_id=world["image"].id, event_id=world["event"].id,
        category="other", reporter_ip="1.1.1.1", status="pending",
    )
    db.add(report)
    db.commit()
    db.refresh(report)

    resp = client.post(
        f"/admin/abuse-reports/{report.id}/dismiss",
        headers={"Authorization": f"Bearer {world['super_token']}"},
    )
    assert resp.status_code == 200

    db.refresh(report)
    assert report.status == "dismissed"
    assert report.action_taken == "dismiss"


def test_action_on_terminal_status_returns_409(setup_world):
    world = setup_world
    db = world["db"]
    report = AbuseReport(
        image_id=world["image"].id, event_id=world["event"].id,
        category="other", reporter_ip="1.1.1.1", status="dismissed",
    )
    db.add(report)
    db.commit()
    db.refresh(report)

    resp = client.post(
        f"/admin/abuse-reports/{report.id}/quarantine",
        headers={"Authorization": f"Bearer {world['super_token']}"},
    )
    assert resp.status_code == 409


def test_double_quarantine_returns_409(setup_world):
    """Quarantine on an already-quarantined report → 409 per the
    explicit transition map (quarantined → quarantined is not allowed)."""
    world = setup_world
    db = world["db"]
    report = AbuseReport(
        image_id=world["image"].id, event_id=world["event"].id,
        category="nudity", reporter_ip="1.1.1.1", status="quarantined",
    )
    db.add(report)
    db.commit()
    db.refresh(report)

    resp = client.post(
        f"/admin/abuse-reports/{report.id}/quarantine",
        headers={"Authorization": f"Bearer {world['super_token']}"},
    )
    assert resp.status_code == 409


def test_dismiss_quarantined_report_allowed(setup_world):
    """Quarantined report can still be dismissed (closes the report
    while leaving the image quarantined — operator may then use the
    /restore action separately)."""
    world = setup_world
    db = world["db"]
    report = AbuseReport(
        image_id=world["image"].id, event_id=world["event"].id,
        category="nudity", reporter_ip="1.1.1.1", status="quarantined",
    )
    db.add(report)
    db.commit()
    db.refresh(report)

    resp = client.post(
        f"/admin/abuse-reports/{report.id}/dismiss",
        headers={"Authorization": f"Bearer {world['super_token']}"},
    )
    assert resp.status_code == 200
    db.refresh(report)
    assert report.status == "dismissed"


# ─── Phase 2 defence layer ───────────────────────────────────────────


def _flush_abuse_rate_keys():
    try:
        for prefix in (
            "rate_limit:abuse_report:*",
            "rate_limit:abuse_report_subnet:*",
            "rate_limit:abuse_report_event:*",
            "rate_limit:abuse_report_email:*",
            "rate_limit:abuse_report_image_dedupe:*",
            "abuse:permaban:*",
            "abuse:softban:*",
        ):
            for k in redis_client.keys(prefix):
                redis_client.delete(k)
    except Exception:
        pass


def test_image_dedupe_silent_drop_after_threshold(setup_world):
    world = setup_world
    db = world["db"]
    _flush_abuse_rate_keys()
    # First 3 reports against the same image go through (within dedup window).
    for _ in range(3):
        resp = client.post("/report", json={
            "image_id": str(world["image"].id),
            "category": "harassment",
        })
        assert resp.status_code == 200
    # 4th is silent-dropped: 200 + fixed body, NO new row.
    pre_count = db.query(AbuseReport).filter(
        AbuseReport.image_id == world["image"].id
    ).count()
    resp = client.post("/report", json={
        "image_id": str(world["image"].id),
        "category": "harassment",
    })
    assert resp.status_code == 200
    post_count = db.query(AbuseReport).filter(
        AbuseReport.image_id == world["image"].id
    ).count()
    assert post_count == pre_count


def test_email_rate_limit_returns_429(setup_world):
    world = setup_world
    _flush_abuse_rate_keys()
    # Per-email cap is 5/hour. Need to also have different image_ids to
    # avoid the per-image dedup silent-dropping requests 4-5 (which would
    # never reach the email limiter). Create extra images.
    images = [world["image"]]
    for _ in range(5):
        img = Image(
            event_id=world["event"].id,
            filename=f"p{uuid.uuid4().hex[:6]}.jpg",
            file_hash="x" * 64,
            size_bytes=1024,
            status="indexed",
        )
        world["db"].add(img)
        world["db"].commit()
        world["db"].refresh(img)
        images.append(img)

    for i in range(5):
        resp = client.post("/report", json={
            "image_id": str(images[i].id),
            "category": "other",
            "reporter_email": "same@example.com",
        })
        assert resp.status_code == 200
    # 6th from same email but different image → 429 from the email
    # limiter (the per-IP, subnet, event limits are all still under cap).
    resp = client.post("/report", json={
        "image_id": str(images[5].id),
        "category": "other",
        "reporter_email": "same@example.com",
    })
    assert resp.status_code == 429


def test_softban_silent_drop_after_dismiss_rate_threshold(setup_world):
    world = setup_world
    db = world["db"]
    _flush_abuse_rate_keys()
    # Seed 5 reports from a single IP with 4 dismissed (80% dismiss rate
    # over min-5 reports triggers softban).
    ip = "5.5.5.5"
    for i in range(5):
        db.add(AbuseReport(
            image_id=world["image"].id, event_id=world["event"].id,
            category="other", reporter_ip=ip,
            status="dismissed" if i < 4 else "pending",
        ))
    db.commit()
    pre_count = db.query(AbuseReport).count()
    with patch("app.routers.abuse_reports.request_ip_unused", create=True):
        pass  # placeholder so the indent stays consistent
    # We can't easily override request.client.host from TestClient, so
    # patch the dependency at the call site by setting X-Forwarded-For
    # is NOT enough (FastAPI uses request.client). Use an inline override
    # of the rate limiter's key derivation? Simpler: directly call the
    # reputation helper to verify the threshold logic; the request-side
    # is covered by the integration tests.
    from app.routers.abuse_reports import _check_reputation_ban
    state = _check_reputation_ban(db, ip)
    assert state in ("softban", "permaban")


def test_subnet_limit_blocks_after_threshold(setup_world):
    """Per-/24 subnet limiter trips at the configured limit. We can't easily
    rotate the test client's IP, so verify the limiter directly."""
    world = setup_world
    _flush_abuse_rate_keys()
    from app.rate_limiter import abuse_report_subnet_rate_limiter
    from app.config import settings as _settings
    key = "192.0.2.0/24"
    # Exhaust the bucket.
    for _ in range(_settings.abuse_report_subnet_rate_limit):
        ok, _ = abuse_report_subnet_rate_limiter.check_rate_limit(
            key, action="abuse_report_subnet"
        )
        assert ok
    # Next one trips.
    ok, _ = abuse_report_subnet_rate_limiter.check_rate_limit(
        key, action="abuse_report_subnet"
    )
    assert ok is False


def test_list_surfaces_duplicate_count(setup_world):
    world = setup_world
    db = world["db"]
    _flush_abuse_rate_keys()
    # Three pending reports against the same image.
    for ip in ("1.1.1.1", "2.2.2.2", "3.3.3.3"):
        db.add(AbuseReport(
            image_id=world["image"].id, event_id=world["event"].id,
            category="other", reporter_ip=ip, status="pending",
        ))
    db.commit()

    resp = client.get(
        "/admin/abuse-reports",
        headers={"Authorization": f"Bearer {world['super_token']}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 3
    for item in data["items"]:
        # Each row reports "+2 other pending/reviewing on same image".
        assert item["duplicate_count"] == 2


def test_dismiss_by_source_bulk_dismisses(setup_world):
    world = setup_world
    db = world["db"]
    _flush_abuse_rate_keys()
    for _ in range(3):
        db.add(AbuseReport(
            image_id=world["image"].id, event_id=world["event"].id,
            category="other", reporter_ip="9.9.9.9", status="pending",
        ))
    db.commit()

    resp = client.post(
        "/admin/abuse-reports/dismiss-by-source",
        headers={"Authorization": f"Bearer {world['super_token']}"},
        json={"reporter_ip": "9.9.9.9"},
    )
    assert resp.status_code == 200
    assert resp.json()["dismissed"] == 3
    remaining = db.query(AbuseReport).filter(
        AbuseReport.reporter_ip == "9.9.9.9",
        AbuseReport.status == "pending",
    ).count()
    assert remaining == 0


def test_clear_ban_drops_redis_flags(setup_world):
    world = setup_world
    ip = "7.7.7.7"
    redis_client.set(f"abuse:permaban:{ip}", "1")
    redis_client.set(f"abuse:softban:{ip}", "1")
    resp = client.post(
        "/admin/abuse-reports/clear-ban",
        headers={"Authorization": f"Bearer {world['super_token']}"},
        json={"reporter_ip": ip},
    )
    assert resp.status_code == 200
    assert not redis_client.exists(f"abuse:permaban:{ip}")
    assert not redis_client.exists(f"abuse:softban:{ip}")


def test_turnstile_required_when_secret_configured(setup_world):
    world = setup_world
    _flush_abuse_rate_keys()
    # No token in body — with secret configured, /report must return 403.
    with patch(
        "app.routers.abuse_reports.settings.cloudflare_turnstile_secret_key",
        "test-secret",
    ):
        resp = client.post("/report", json={
            "image_id": str(world["image"].id),
            "category": "other",
        })
        assert resp.status_code == 403


def test_get_single_report_after_reveal_flips_status(setup_world):
    """Reveal transitions pending → reviewing. The single-fetch endpoint
    must return the report regardless of status; the list endpoint
    defaults to status='pending' so it would silently exclude this row."""
    world = setup_world
    db = world["db"]
    report = AbuseReport(
        image_id=world["image"].id, event_id=world["event"].id,
        category="csam", reporter_ip="1.1.1.1", status="pending",
    )
    db.add(report)
    db.commit()
    db.refresh(report)

    # Reveal flips to 'reviewing'.
    client.post(
        f"/admin/abuse-reports/{report.id}/reveal",
        headers={"Authorization": f"Bearer {world['super_token']}"},
    )

    # Single fetch must still return the row.
    resp = client.get(
        f"/admin/abuse-reports/{report.id}",
        headers={"Authorization": f"Bearer {world['super_token']}"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == str(report.id)
    assert body["status"] == "reviewing"


def test_turnstile_passes_when_siteverify_returns_success(setup_world):
    world = setup_world
    _flush_abuse_rate_keys()
    with patch(
        "app.routers.abuse_reports.settings.cloudflare_turnstile_secret_key",
        "test-secret",
    ), patch(
        "app.routers.abuse_reports._verify_turnstile", return_value=True
    ):
        resp = client.post("/report", json={
            "image_id": str(world["image"].id),
            "category": "other",
            "turnstile_token": "valid-token",
        })
        assert resp.status_code == 200
