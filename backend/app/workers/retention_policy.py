"""
Retention policy background job for cleaning up expired events
"""
import logging
import uuid
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
from app.utils.storage_cleanup import (
    safe_delete_event_photos,
    enqueue_cleanup_task,
    drain_storage_cleanup_tasks,
)

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
                # actor_type='system' so the row reads as an automated
                # retention sweep, not as the event owner manually
                # deleting their own event. We still record the owner
                # via metadata.owner_user_id for forensic traceability.
                log_action(
                    db=db,
                    event_id=event.id,
                    actor_type='system',
                    actor_id=None,
                    action='delete_event_retention',
                    metadata={
                        'event_name': event.name,
                        'photo_count': photo_count,
                        'retention_days': event.retention_days,
                        'reason': 'retention_policy',
                        'owner_user_id': str(event.owner_user_id) if event.owner_user_id else None,
                    },
                    commit=False,
                )

                try:
                    delete_compreface_subjects_for_event(db, event.id)
                except Exception as e:
                    logger.error(f"CompreFace cleanup failed for event {event.id}: {e}")
                    for face in db.query(Face).filter(Face.event_id == event.id).all():
                        if face.compreface_subject_id:
                            enqueue_cleanup_task(
                                db, "compreface_subject",
                                {"subject_id": face.compreface_subject_id},
                                commit=False,
                            )

                # Delete all photos from MinIO — tombstone on failure so
                # the drainer keeps retrying instead of orphaning bytes.
                safe_delete_event_photos(db, event.id, commit=False)

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


def drain_storage_cleanups(db: Session = None) -> dict:
    """Retry every due storage-cleanup tombstone.

    Called from the retention cron. Each tombstone is an in-flight cleanup
    that failed inline (MinIO unavailable, CompreFace 5xx). Idempotent — a
    successful retry marks the tombstone done; a failed retry backs off and
    re-tries on the next cycle.
    """
    db_provided = db is not None
    if not db_provided:
        db = SessionLocal()
    try:
        stats = drain_storage_cleanup_tasks(db)
        logger.info("Storage cleanup drain: %s", stats)
        return stats
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
    now = datetime.utcnow()
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

        # Soft-cancel reconciliation: catch active subs scheduled to cancel
        # whose current_period_end has already passed. Stripe normally fires
        # customer.subscription.deleted on schedule, but if that webhook is
        # missed (transient outage, signing-secret mismatch, retry exhaustion)
        # the user keeps paid limits past the end date. We re-check Stripe
        # directly and downgrade if the sub is no longer active.
        scheduled_cancels = (
            db.query(UserTier)
            .filter(
                UserTier.subscription_status.in_(("active", "trialing")),
                UserTier.cancel_at_period_end.is_(True),
                UserTier.current_period_end.isnot(None),
                UserTier.current_period_end < now,
                UserTier.stripe_subscription_id.isnot(None),
            )
            .all()
        )

        for ut in scheduled_cancels:
            try:
                import stripe
                stripe.api_key = settings.stripe_secret_key
                sub = stripe.Subscription.retrieve(ut.stripe_subscription_id)
                stripe_status = getattr(sub, "status", None)
                if stripe_status in ("active", "trialing"):
                    # Stripe still considers it active (period rolled over
                    # naturally or user reactivated). Resync local state from
                    # Stripe rather than downgrade.
                    cpe = getattr(sub, "current_period_end", None)
                    if cpe:
                        ut.current_period_end = datetime.utcfromtimestamp(cpe)
                    ut.cancel_at_period_end = bool(getattr(sub, "cancel_at_period_end", False))
                    if not db_provided:
                        db.commit()
                    else:
                        db.flush()
                    logger.info(
                        "Soft-cancel reconcile: user %s still active in Stripe; resynced state",
                        ut.user_id,
                    )
                    continue
                # Stripe confirms cancellation (canceled / incomplete_expired
                # / unpaid). Apply the downgrade we would have done from the
                # missed webhook.
                overdue.append(ut)
                logger.info(
                    "Soft-cancel reconcile: user %s confirmed canceled in Stripe (status=%s); queued for downgrade",
                    ut.user_id, stripe_status,
                )
            except Exception as e:
                logger.error(
                    "Failed to reconcile soft-cancel for user %s: %s",
                    ut.user_id, e,
                )
                continue

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


def requeue_stale_pending_indexing(
    db: Session = None,
    stale_minutes: int = 30,
    enqueue_failed_lookback_days: int = 7,
) -> int:
    """Re-enqueue images that never made it through indexing for a
    transient queueing reason. Covers two distinct stuck-state cases:

    1. ``status='pending'`` for longer than ``stale_minutes``. This is
       the original case: upload committed the Image row, then the
       process crashed before reaching the enqueue call, so the row
       sits in pending with no RQ job pointing at it.

    2. ``status='failed'`` where the failure was specifically the
       upload-time enqueue (not the worker). The upload path now logs
       ``action='index_enqueue_failed'`` audit rows when Redis is
       briefly unreachable. We pick those rows up by audit-log join,
       reset the image to 'pending', and re-enqueue. Without this,
       a one-second Redis hiccup at upload time left photos
       permanently failed and required a manual admin reindex.

    Genuine indexing failures (the worker actually ran and CompreFace
    raised, image was corrupted, etc.) do NOT have an
    ``index_enqueue_failed`` audit row, so they are NOT retried here.
    That stays a manual admin call.

    Run alongside the other daily jobs.
    """
    # Local imports avoid worker-import cycles and keep AuditLog import
    # local to this function so the rest of retention_policy doesn't
    # pull it.
    from app.queue import enqueue_face_indexing, JobAlreadyQueued
    from app.models import AuditLog

    db_provided = db is not None
    if not db_provided:
        db = SessionLocal()

    now = datetime.utcnow()
    pending_cutoff = now - timedelta(minutes=stale_minutes)
    audit_cutoff = now - timedelta(days=enqueue_failed_lookback_days)
    requeued = 0
    skipped_already_queued = 0

    try:
        # Case 1: pending for too long
        pending_stuck = (
            db.query(Image)
            .filter(
                Image.status == "pending",
                Image.uploaded_at < pending_cutoff,
            )
            .all()
        )

        # Case 2: failed with an index_enqueue_failed audit row in the
        # recent past. metadata_ is a JSONB column; image_id is stored
        # there at audit-write time.
        enqueue_failed_audit_rows = (
            db.query(AuditLog)
            .filter(
                AuditLog.action == "index_enqueue_failed",
                AuditLog.timestamp >= audit_cutoff,
            )
            .all()
        )
        failed_image_uuids: list[uuid.UUID] = []
        for row in enqueue_failed_audit_rows:
            meta = row.metadata_ or {}
            image_id_str = meta.get("image_id") if isinstance(meta, dict) else None
            if not image_id_str:
                continue
            try:
                failed_image_uuids.append(uuid.UUID(str(image_id_str)))
            except (TypeError, ValueError):
                continue

        failed_to_recover: list[Image] = []
        if failed_image_uuids:
            failed_to_recover = (
                db.query(Image)
                .filter(
                    Image.id.in_(failed_image_uuids),
                    Image.status == "failed",
                )
                .all()
            )

        targets = pending_stuck + failed_to_recover

        for img in targets:
            try:
                enqueue_face_indexing(str(img.id))
                # Reset failed -> pending so the worker treats it as a
                # fresh attempt rather than skipping under its already-
                # indexed / already-failed guard.
                if img.status == "failed":
                    img.status = "pending"
                requeued += 1
                logger.info(
                    f"Requeued image {img.id} "
                    f"(was status={img.status}, uploaded {img.uploaded_at})"
                )
            except JobAlreadyQueued:
                # Another reconciler tick already enqueued this image,
                # or the deterministic job hash is still in flight from
                # an earlier run. No need to re-enqueue.
                skipped_already_queued += 1
                logger.info(f"Skipping image {img.id} — job already queued")
                continue
            except Exception as e:
                logger.error(f"Failed to requeue image {img.id}: {e}")
                continue

        if requeued and not db_provided:
            db.commit()
        elif requeued:
            db.flush()

        logger.info(
            f"Stale-pending reconciler complete. Requeued {requeued} image(s); "
            f"{skipped_already_queued} skipped (already queued)."
        )
        return requeued
    finally:
        if not db_provided:
            db.close()


if __name__ == "__main__":
    # Allow running this script directly for testing
    check_and_delete_expired_events()
    process_overdue_subscriptions()
    requeue_stale_pending_indexing()
