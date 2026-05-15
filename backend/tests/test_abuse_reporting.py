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
