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
    event_id: uuid.UUID,
    actor_type: str,
    actor_id: Optional[uuid.UUID],
    action: str,
    metadata: Optional[Dict[str, Any]] = None
) -> AuditLog:
    """
    Create an audit log entry
    
    Args:
        db: Database session
        event_id: UUID of the event
        actor_type: Type of actor ('admin' or 'guest')
        actor_id: UUID of the user or session
        action: Action performed (e.g., 'access', 'scan', 'upload', 'reindex', 'delete')
        metadata: Optional metadata as dictionary
    
    Returns:
        Created AuditLog instance
    """
    # Validate actor_type
    if actor_type not in ['admin', 'guest']:
        raise ValueError(f"Invalid actor_type: {actor_type}. Must be 'admin' or 'guest'")
    
    # Create audit log entry
    audit_log = AuditLog(
        event_id=event_id,
        actor_type=actor_type,
        actor_id=actor_id,
        action=action,
        metadata_=metadata or {}
    )
    
    db.add(audit_log)
    db.commit()
    db.refresh(audit_log)
    
    return audit_log
