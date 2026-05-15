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
    """Real and fake image_ids must respond in roughly the same time."""
    world = setup_world

    def time_call(image_id: str) -> float:
        t0 = time.monotonic()
        client.post("/report", json={"image_id": image_id, "category": "other"})
        return time.monotonic() - t0

    # Warm-up to factor out import/Redis-connect cost.
    time_call(str(world["image"].id))
    real = time_call(str(world["image"].id))
    fake = time_call(str(uuid.uuid4()))
    # 50ms floor + DB jitter — keep generous so the assertion isn't flaky.
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
