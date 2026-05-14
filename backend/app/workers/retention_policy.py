"""
Retention policy background job for cleaning up expired events
"""
import logging
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import func, text

from app.database import SessionLocal
from app.event_status import invalidate_event_public_cache, rebalance_event_status
from app.models import Event, Image, Face, UserTier
from app.storage import storage_service
from app.audit import log_action
from app.config import settings
from app.tiers import TIER_CONFIG
from app.utils.compreface import delete_compreface_subjects_for_event

logger = logging.getLogger(__name__)


def check_and_delete_expired_events(db: Session = None):
    """
    Check for expired events and delete them.
    
    This job should be run periodically (e.g., daily) to enforce retention policies.
    Events are considered expired if:
    - created_at + retention_days < current_date
    
    For each expired event:
    1. Log the deletion
    2. Delete all photos from MinIO
    3. Delete the event from database (cascades to all related records)
    
    Args:
        db: Optional database session (for testing). If not provided, creates a new session.
    """
    # Use provided session or create new one
    db_provided = db is not None
    if not db_provided:
        db = SessionLocal()
    
    try:
        # Get current date
        current_date = datetime.utcnow()
        
        # Find all events that have exceeded their retention period
        # Use raw SQL for date arithmetic since SQLAlchemy's func.date() + interval is complex
        expired_events = db.query(Event).filter(
            text("created_at + (retention_days || ' days')::interval < :current_date")
        ).params(current_date=current_date).all()
        
        deleted_count = 0
        
        for event in expired_events:
            try:
                # Get photo count for logging
                photo_count = db.query(func.count(Image.id)).filter(
                    Image.event_id == event.id
                ).scalar() or 0
                
                # Stage the audit row inside the same transaction (commit=
                # False). FK SET NULL preserves the row past the event
                # delete; rollback on cleanup failure discards it.
                log_action(
                    db=db,
                    event_id=event.id,
                    actor_type='admin',
                    actor_id=event.owner_user_id,
                    action='delete_event_retention',
                    metadata={
                        'event_name': event.name,
                        'photo_count': photo_count,
                        'retention_days': event.retention_days,
                        'reason': 'retention_policy'
                    },
                    commit=False,
                )

                delete_compreface_subjects_for_event(db, event.id)

                # Delete all photos from MinIO
                try:
                    storage_service.delete_event_photos(event.id)
                except Exception as e:
                    # Log error but continue with database deletion
                    logger.error(f"Failed to delete photos from MinIO for event {event.id}: {e}")

                invalidate_event_public_cache(event)

                # Delete event from database (cascades to all related records)
                db.delete(event)
                
                # Only commit if we created the session
                if not db_provided:
                    db.commit()
                else:
                    db.flush()
                
                deleted_count += 1
                logger.info(f"Deleted expired event: {event.name} (ID: {event.id})")
                
            except Exception as e:
                if not db_provided:
                    db.rollback()
                logger.error(f"Failed to delete event {event.id}: {e}")
                continue
        
        logger.info(f"Retention policy job completed. Deleted {deleted_count} expired events.")
        return deleted_count
        
    except Exception as e:
        if not db_provided:
            db.rollback()
        logger.error(f"Retention policy job failed: {e}")
        raise
    finally:
        if not db_provided:
            db.close()


def process_overdue_subscriptions(db: Session = None):
    """Downgrade subscriptions that exceeded the payment-failure grace period.

    Stripe sends customer.subscription.deleted on hard-cancel, but past_due
    and paused subscriptions sit in limbo with no upcoming billing event.
    After grace_period_days past current_period_end we drop the user back
    to free and freeze excess events. paused is rarer than past_due — it
    comes from `pause_collection` on the Stripe side — but it has the same
    failure mode (paid limits with no payment in sight) and the same fix.

    Run daily alongside event retention.
    """
    db_provided = db is not None
    if not db_provided:
        db = SessionLocal()

    grace = timedelta(days=settings.subscription_grace_period_days)
    cutoff = datetime.utcnow() - grace
    downgraded = 0

    try:
        overdue = (
            db.query(UserTier)
            .filter(
                # past_due: Stripe accepted the sub but the latest invoice failed.
                # paused: Stripe-side pause (manager.pause or customer request).
                # Both leave the user on a paid tier but with no upcoming
                # successful billing event, so without a grace cutoff they
                # could keep paid limits forever.
                UserTier.subscription_status.in_(("past_due", "paused")),
                UserTier.current_period_end.isnot(None),
                UserTier.current_period_end < cutoff,
            )
            .all()
        )

        for ut in overdue:
            try:
                cfg = TIER_CONFIG["free"]
                ut.tier_name = "free"
                ut.max_events = cfg["max_events"]
                ut.max_photos_per_event = cfg["max_photos_per_event"]
                ut.retention_days = cfg["retention_days"]
                ut.price_cents = 0
                ut.subscription_status = None
                ut.stripe_subscription_id = None
                ut.billing_interval = None
                ut.current_period_end = None
                ut.cancel_at_period_end = False
                # Stamp now so any stale Stripe webhook (created < utcnow)
                # for the past_due sub fails the staleness check and cannot
                # re-grant the paid tier after this manual downgrade.
                ut.last_subscription_event_at = datetime.utcnow()
                ut.last_subscription_event_id = None
                ut.last_subscription_event_type = "grace_period_downgrade"
                ut.last_subscription_event_subscription_id = None

                # Freeze excess active events down to free-tier cap and clear
                # guest-facing caches for any event whose status changed.
                rebalance = rebalance_event_status(ut.user_id, cfg["max_events"], db)

                if not db_provided:
                    db.commit()
                else:
                    db.flush()
                downgraded += 1
                logger.info(
                    f"Subscription grace period exceeded - user {ut.user_id} "
                    f"downgraded to free, froze {rebalance.frozen} events"
                )
            except Exception as e:
                if not db_provided:
                    db.rollback()
                logger.error(f"Failed to downgrade user {ut.user_id}: {e}")
                continue

        logger.info(f"Subscription processor completed. Downgraded {downgraded} users.")
        return downgraded
    finally:
        if not db_provided:
            db.close()


def requeue_stale_pending_indexing(db: Session = None, stale_minutes: int = 30) -> int:
    """Re-enqueue images stuck at status='pending' for longer than stale_minutes.

    The upload path commits the Image row before enqueueing the face-indexing
    job. If the enqueue fails (Redis down, worker not running, transient
    network issue), the upload handler now flips the image to 'failed' —
    but a process crash BETWEEN commit-image and enqueue would still leave a
    pending row with no job. This reconciler is the backstop for that case.

    Run alongside the other daily jobs.
    """
    from app.queue import enqueue_face_indexing  # local import: avoids worker-import cycles

    db_provided = db is not None
    if not db_provided:
        db = SessionLocal()

    cutoff = datetime.utcnow() - timedelta(minutes=stale_minutes)
    requeued = 0

    try:
        stale = (
            db.query(Image)
            .filter(
                Image.status == "pending",
                Image.uploaded_at < cutoff,
            )
            .all()
        )

        for img in stale:
            try:
                enqueue_face_indexing(str(img.id))
                requeued += 1
                logger.info(
                    f"Requeued stale pending image {img.id} "
                    f"(uploaded {img.uploaded_at}, age >= {stale_minutes} min)"
                )
            except Exception as e:
                logger.error(f"Failed to requeue stale pending image {img.id}: {e}")
                continue

        logger.info(f"Stale-pending reconciler complete. Requeued {requeued} image(s).")
        return requeued
    finally:
        if not db_provided:
            db.close()


if __name__ == "__main__":
    # Allow running this script directly for testing
    check_and_delete_expired_events()
    process_overdue_subscriptions()
    requeue_stale_pending_indexing()
