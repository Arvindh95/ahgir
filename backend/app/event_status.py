"""Event status reconciliation and public cache invalidation helpers."""

import logging
import uuid
from dataclasses import dataclass
from typing import Iterable

from sqlalchemy import asc, desc
from sqlalchemy.orm import Session

from app.cache import cache_delete_pattern
from app.models import Event

logger = logging.getLogger(__name__)


@dataclass
class EventStatusRebalanceResult:
    frozen: int = 0
    unfrozen: int = 0


def invalidate_event_public_caches(events: Iterable[Event]) -> None:
    """Drop all guest-facing caches for the given events."""
    for event in events:
        invalidate_event_public_cache(event)


def invalidate_event_public_cache(event: Event) -> None:
    """Drop all guest-facing caches for one event."""
    if event.slug:
        cache_delete_pattern(f"event_info:{event.slug}")
    cache_delete_pattern(f"share:{event.id}:*")
    cache_delete_pattern(f"gallery:{event.id}:*")


def rebalance_event_status(user_id: uuid.UUID, max_active: int, db: Session) -> EventStatusRebalanceResult:
    """Reconcile a user's event statuses with their active-event quota."""
    active_events = (
        db.query(Event)
        .filter(Event.owner_user_id == user_id, Event.status == "active")
        .order_by(asc(Event.created_at))
        .all()
    )
    active_count = len(active_events)

    if active_count > max_active:
        excess = active_count - max_active
        flipped = active_events[:excess]
        for event in flipped:
            event.status = "frozen"
        invalidate_event_public_caches(flipped)
        logger.info("Froze %s oldest events for user %s (cap %s)", excess, user_id, max_active)
        return EventStatusRebalanceResult(frozen=len(flipped))

    slots_available = max_active - active_count
    if slots_available <= 0:
        return EventStatusRebalanceResult()

    frozen_events = (
        db.query(Event)
        .filter(Event.owner_user_id == user_id, Event.status == "frozen")
        .order_by(desc(Event.created_at))
        .limit(slots_available)
        .all()
    )
    for event in frozen_events:
        event.status = "active"
    if frozen_events:
        invalidate_event_public_caches(frozen_events)
        logger.info("Unfroze %s events for user %s (cap %s)", len(frozen_events), user_id, max_active)
    return EventStatusRebalanceResult(unfrozen=len(frozen_events))
