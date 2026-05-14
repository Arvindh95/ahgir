"""
Audit logging service for tracking Admin and Guest actions
"""
from typing import Optional, Dict, Any
from sqlalchemy.orm import Session
from datetime import datetime
import uuid

from app.models import AuditLog


def log_action(
    db: Session,
    event_id: Optional[uuid.UUID],
    actor_type: str,
    actor_id: Optional[uuid.UUID],
    action: str,
    metadata: Optional[Dict[str, Any]] = None,
    commit: bool = True,
) -> AuditLog:
    """
    Create an audit log entry.

    Args:
        db: Database session
        event_id: UUID of the event the action affected. May be None for
            superadmin actions that are not scoped to a specific event
            (user tier updates, user deletion, retried jobs, etc.).
        actor_type: Type of actor ('admin' or 'guest')
        actor_id: UUID of the user or session
        action: Action performed (e.g., 'access', 'scan', 'upload',
            'reindex', 'delete', 'admin_user_update', 'admin_event_delete')
        metadata: Optional metadata as dictionary
        commit: When True (default, backwards-compatible), the helper
            commits its own transaction. Set False when the caller wants
            the audit row to be part of a larger transaction — e.g., a
            destructive event-delete flow that must keep the audit
            insert atomic with the delete so a failed cleanup rolls
            back the audit entry too. With commit=False the caller is
            responsible for calling db.commit() afterwards.

    Returns:
        Created AuditLog instance. When commit=False the returned
        instance has been flushed but not committed; its primary key is
        populated and it is safe to reference, but it will be rolled
        back if the caller's transaction fails.
    """
    # Validate actor_type. 'system' is for automated jobs (retention
    # sweep, scheduled downgrades) so they don't get misattributed to a
    # human admin in the audit viewer.
    if actor_type not in ('admin', 'guest', 'system'):
        raise ValueError(
            f"Invalid actor_type: {actor_type}. Must be 'admin', 'guest', or 'system'"
        )

    # Create audit log entry
    audit_log = AuditLog(
        event_id=event_id,
        actor_type=actor_type,
        actor_id=actor_id,
        action=action,
        metadata_=metadata or {}
    )

    db.add(audit_log)
    if commit:
        db.commit()
        db.refresh(audit_log)
    else:
        # Flush so the row is sent to the DB (PK + server defaults populated)
        # but stays inside the caller's transaction. A subsequent
        # rollback by the caller discards the audit row alongside the
        # failed work, preserving atomicity for destructive flows.
        db.flush()

    return audit_log
