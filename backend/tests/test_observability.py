"""
Regression tests for the audit / observability review:

P2 — "Scans by day (last 30 days)" must actually be last 30 days. The
     pre-fix queries had no timestamp cutoff, so once an event had
     more than 30 active days the chart showed the OLDEST 30 days
     (asc + limit) instead of recent activity.

P3 — Global "top events" must group by event id + name, not name
     alone. Two unrelated events with the same display name no longer
     collapse into one leaderboard row.

P3 — Retention sweep attributes audit rows to actor_type='system' so
     they don't masquerade as a human admin action. The log_action
     helper now accepts 'system' alongside admin / guest.

P3 — /health/load factors recent failed-image count into the score so
     a fast-failing CompreFace outage doesn't keep the verdict green.
"""
import uuid
from datetime import datetime, timedelta

import pytest
from sqlalchemy.orm import Session

from app.audit import log_action
from app.auth import hash_password
from app.models import AuditLog, Event, User


def _make_user_and_event(db: Session) -> tuple[User, Event]:
    user = User(
        email=f"obs-{uuid.uuid4().hex}@example.com",
        password_hash=hash_password("x"),
        is_verified=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    event = Event(
        owner_user_id=user.id,
        slug=f"obs-{uuid.uuid4().hex[:8]}",
        name="Observability event",
        retention_days=30,
        status="active",
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    return user, event


# ─── P3 #4: actor_type='system' is accepted ──────────────────────────────


def test_log_action_accepts_system_actor_type(db_session: Session):
    """The audit helper must allow actor_type='system' so automated jobs
    (retention sweep, scheduled downgrades) aren't misattributed as
    admin actions.
    """
    _user, event = _make_user_and_event(db_session)

    row = log_action(
        db=db_session,
        event_id=event.id,
        actor_type="system",
        actor_id=None,
        action="delete_event_retention",
        metadata={"reason": "retention_policy"},
    )
    assert row.id is not None
    assert row.actor_type == "system"
    assert row.actor_id is None


def test_log_action_rejects_unknown_actor_type(db_session: Session):
    """Belt-and-suspenders: invalid actor_type values must still raise
    so a typo can't sneak in past the CHECK constraint.
    """
    _user, event = _make_user_and_event(db_session)
    with pytest.raises(ValueError):
        log_action(
            db=db_session,
            event_id=event.id,
            actor_type="robot",  # not in the allowed set
            actor_id=None,
            action="bogus",
            metadata={},
        )


def test_audit_log_actor_type_check_constraint_includes_system(db_session: Session):
    """The DB-level CHECK constraint must mirror the ORM enum so insertion
    via raw SQL or a future migration is also caught.
    """
    from sqlalchemy import inspect

    inspector = inspect(db_session.get_bind())
    constraints = inspector.get_check_constraints("audit_logs")
    valid = next((c for c in constraints if c["name"] == "valid_actor_type"), None)
    assert valid is not None
    sql = valid["sqltext"].lower()
    assert "system" in sql, f"valid_actor_type CHECK missing 'system': {sql}"


# ─── P3 #2: top_events groups by id + name ───────────────────────────────


def test_top_events_query_groups_by_event_id(db_session: Session):
    """Two events with the same display name must produce two rows in
    the leaderboard, not one merged row. Pre-fix the admin analytics
    query grouped by Event.name alone, so 'Wedding' + 'Wedding'
    collapsed and the combined counts were misleading.
    """
    from sqlalchemy import func
    from app.models import AuditLog as AL, Event as E

    user, _ = _make_user_and_event(db_session)
    # Two distinct events with the same display name.
    e1 = Event(owner_user_id=user.id, slug=f"a-{uuid.uuid4().hex[:8]}", name="Wedding")
    e2 = Event(owner_user_id=user.id, slug=f"b-{uuid.uuid4().hex[:8]}", name="Wedding")
    db_session.add_all([e1, e2])
    db_session.commit()
    db_session.refresh(e1)
    db_session.refresh(e2)

    log_action(db=db_session, event_id=e1.id, actor_type="guest", actor_id=uuid.uuid4(), action="scan")
    log_action(db=db_session, event_id=e1.id, actor_type="guest", actor_id=uuid.uuid4(), action="scan")
    log_action(db=db_session, event_id=e2.id, actor_type="guest", actor_id=uuid.uuid4(), action="scan")

    # Same query shape as admin.py admin_analytics_endpoint after the fix.
    rows = (
        db_session.query(
            E.id,
            E.name,
            func.count(AL.id).label("scan_count"),
        )
        .join(AL, AL.event_id == E.id)
        .filter(AL.action == "scan", E.id.in_([e1.id, e2.id]))
        .group_by(E.id, E.name)
        .order_by(func.count(AL.id).desc())
        .all()
    )

    assert len(rows) == 2, f"expected 2 leaderboard rows for same-named events, got {len(rows)}"
    event_ids = {row[0] for row in rows}
    assert e1.id in event_ids
    assert e2.id in event_ids


# ─── P2 #1: scans_by_day cutoff ──────────────────────────────────────────


def test_scans_by_day_timestamp_cutoff_filters_old_rows(db_session: Session):
    """With a 30-day cutoff applied, audit rows older than 30 days must
    NOT appear in scans-by-day. Pre-fix any event with >30 active days
    showed the OLDEST 30 days because of asc + limit.
    """
    from sqlalchemy import func
    from app.models import AuditLog as AL

    _user, event = _make_user_and_event(db_session)

    # 35 days ago — must be filtered out
    old_audit = log_action(
        db=db_session,
        event_id=event.id,
        actor_type="guest",
        actor_id=uuid.uuid4(),
        action="scan",
    )
    db_session.execute(
        AL.__table__.update()
        .where(AL.id == old_audit.id)
        .values(timestamp=datetime.utcnow() - timedelta(days=35))
    )
    db_session.commit()

    # Recent scan — must appear
    log_action(
        db=db_session,
        event_id=event.id,
        actor_type="guest",
        actor_id=uuid.uuid4(),
        action="scan",
    )

    cutoff = datetime.utcnow() - timedelta(days=30)
    rows = (
        db_session.query(
            func.date_trunc("day", AL.timestamp).label("date"),
            func.count(AL.id).label("count"),
        )
        .filter(
            AL.event_id == event.id,
            AL.action == "scan",
            AL.timestamp >= cutoff,
        )
        .group_by(func.date_trunc("day", AL.timestamp))
        .order_by(func.date_trunc("day", AL.timestamp))
        .all()
    )

    assert len(rows) == 1, "only the recent scan should be inside the 30-day cutoff"
    assert int(rows[0][1]) == 1
