"""
Regression tests for the audit-trail-preservation / atomicity findings:

P1 — AuditLog rows must survive Event deletion via the FK's ON DELETE
     SET NULL action (migration a3d4e5f6g7). The Event.audit_logs
     relationship previously had cascade="all, delete-orphan" which
     silently overrode the FK and wiped the audit trail.

P2 — log_action(commit=False) must stage the row inside the caller's
     transaction so a downstream failure rolls back the audit row too.
     Default log_action(commit=True) keeps its own commit for the
     read-only / informational call sites.

P3 — Event.status must be DB-constrained to {active, frozen, expired}
     in both the production schema AND the test schema generated via
     Base.metadata.create_all().
"""
import uuid

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.exc import DataError, IntegrityError
from sqlalchemy.orm import Session

from app.audit import log_action
from app.auth import hash_password
from app.models import AuditLog, Event, User


def _make_owner_and_event(db: Session) -> tuple[User, Event]:
    user = User(
        email=f"audit-{uuid.uuid4().hex}@example.com",
        password_hash=hash_password("x"),
        is_verified=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    event = Event(
        owner_user_id=user.id,
        slug=f"e-{uuid.uuid4().hex[:8]}",
        name="Audit-trail event",
        retention_days=30,
        status="active",
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    return user, event


# ─── P1: FK SET NULL actually fires ─────────────────────────────────────────

def test_audit_rows_survive_event_delete_via_fk_set_null(db_session: Session):
    """Pre-fix: Event.audit_logs had cascade='all, delete-orphan', so the
    ORM emitted DELETE FROM audit_logs before the event delete and the
    FK action never fired. Audit rows were wiped along with the event.
    Post-fix: cascade removed, passive_deletes=True, FK SET NULL leaves
    the rows in place with event_id=NULL.
    """
    user, event = _make_owner_and_event(db_session)
    event_id = event.id

    # Stage a handful of audit rows.
    for i in range(4):
        log_action(
            db=db_session,
            event_id=event.id,
            actor_type='admin',
            actor_id=user.id,
            action='test_action',
            metadata={'i': i},
        )

    before = db_session.query(AuditLog).filter(AuditLog.event_id == event_id).count()
    assert before == 4

    db_session.delete(event)
    db_session.commit()

    # Event gone.
    assert db_session.query(Event).filter(Event.id == event_id).count() == 0

    # Audit rows still here — their event_id is now NULL.
    still_pointing = db_session.query(AuditLog).filter(AuditLog.event_id == event_id).count()
    assert still_pointing == 0
    survived = (
        db_session.query(AuditLog)
        .filter(AuditLog.event_id.is_(None), AuditLog.actor_id == user.id, AuditLog.action == 'test_action')
        .count()
    )
    assert survived == 4, (
        "audit rows must SURVIVE event delete (FK SET NULL) — pre-fix the "
        "ORM cascade wiped them"
    )


# ─── P2: log_action(commit=False) is atomic with caller's transaction ──────

def test_log_action_commit_false_is_atomic_with_caller(db_session: Session):
    """When the caller passes commit=False, the audit row must roll back
    if the caller's transaction is rolled back. Pre-fix log_action
    always committed, so a destructive flow could leave an audit row
    saying 'deleted' even when the actual delete failed.
    """
    user, event = _make_owner_and_event(db_session)
    event_id = event.id

    log_action(
        db=db_session,
        event_id=event.id,
        actor_type='admin',
        actor_id=user.id,
        action='delete_event',
        metadata={'event_name': event.name},
        commit=False,
    )

    # Row should be visible inside the session (flushed).
    in_session = db_session.query(AuditLog).filter(
        AuditLog.event_id == event_id, AuditLog.action == 'delete_event'
    ).count()
    assert in_session == 1

    # Caller decides to roll back (simulating a failure in the
    # destructive flow that the audit row described).
    db_session.rollback()

    after_rollback = db_session.query(AuditLog).filter(
        AuditLog.event_id == event_id, AuditLog.action == 'delete_event'
    ).count()
    assert after_rollback == 0, (
        "log_action(commit=False) must let the audit row roll back with the "
        "caller's transaction"
    )


def test_log_action_default_still_commits(db_session: Session):
    """Default log_action(commit=True) must keep committing — every
    existing call site relies on this. Regression check: changing the
    default would silently drop audit rows from 20+ call sites.
    """
    user, event = _make_owner_and_event(db_session)
    log_action(
        db=db_session,
        event_id=event.id,
        actor_type='admin',
        actor_id=user.id,
        action='access',
        metadata={},
    )

    # Force a rollback. Should NOT remove the audit row because
    # log_action already committed.
    db_session.rollback()
    after = db_session.query(AuditLog).filter(
        AuditLog.event_id == event.id, AuditLog.action == 'access'
    ).count()
    assert after == 1


# ─── P3: Event status CheckConstraint is in the test schema too ────────────

def test_event_status_check_constraint_is_in_test_metadata(db_session: Session):
    """Production has CHECK (status IN ('active','frozen','expired')) from
    migration s5b6c7d8e9. The ORM model now declares it too, so
    Base.metadata.create_all() picks it up and tests exercise the same
    constraint as production. Verifies by inserting an invalid status.
    """
    user, event = _make_owner_and_event(db_session)

    # Use raw SQL to bypass any ORM-side validation and confirm the
    # constraint exists at the DB level. ('archived' is not in the
    # allowed set.)
    with pytest.raises((IntegrityError, DataError)):
        db_session.execute(
            text("UPDATE events SET status = :s WHERE id = :id"),
            {"s": "archived", "id": str(event.id)},
        )
        db_session.commit()
    db_session.rollback()


def test_event_status_check_constraint_named_correctly(db_session: Session):
    """The constraint name in the ORM declaration must match the one the
    migration creates so alembic check stays happy and downgrade scripts
    can reference it by name.
    """
    inspector = inspect(db_session.get_bind())
    constraints = inspector.get_check_constraints("events")
    names = {c["name"] for c in constraints}
    assert "valid_event_status" in names, (
        f"CheckConstraint name mismatch — got {names}, expected to include "
        f"'valid_event_status'"
    )
