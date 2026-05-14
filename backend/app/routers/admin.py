"""Superadmin management router."""

import logging
from datetime import datetime, timedelta

from app.utils.time import to_utc_iso
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status

logger = logging.getLogger(__name__)
from sqlalchemy.orm import Session
from sqlalchemy import func
from pydantic import BaseModel, Field
import uuid

from app.auth import get_current_user
from app.audit import log_action
from app.database import get_db
from app.models import User, Event, Image, Face, AuditLog, EventTier, UserTier, Payment
from app.config import settings, get_compreface_url
from app.event_status import rebalance_event_status
from app.storage import storage_service
from app.queue import get_failed_jobs, retry_failed_job
from app.tiers import get_effective_limits
from app.cache import cache_delete_pattern
from app.utils.compreface import delete_compreface_subjects_for_event

router = APIRouter(prefix="/admin", tags=["admin"])


async def get_superadmin_user(
    current_user: User = Depends(get_current_user),
) -> User:
    """Dependency that ensures the current user is a superadmin."""
    if not current_user.is_superadmin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Superadmin access required"
        )
    return current_user


class UserListItem(BaseModel):
    user_id: str
    email: str
    is_verified: bool
    is_superadmin: bool
    is_disabled: bool
    event_count: int
    tier_name: str
    max_events: int
    max_photos_per_event: int
    created_at: str


class UserUpdateRequest(BaseModel):
    is_superadmin: Optional[bool] = None
    is_disabled: Optional[bool] = None


class UserTierUpdateRequest(BaseModel):
    tier_name: str  # free, starter, pro, custom
    # Custom-tier overrides: must be positive integers. Without these bounds
    # superadmin can write zero/negative values, putting users into nonsensical
    # quota states that produce confusing upload/create failures downstream.
    max_events: Optional[int] = Field(default=None, ge=1, le=100000)
    max_photos_per_event: Optional[int] = Field(default=None, ge=1, le=1000000)
    # Custom-tier retention override (days). Optional — only honored when
    # tier_name='custom'. Bounded so a typo doesn't park photos for a century
    # or accidentally instant-delete them.
    retention_days: Optional[int] = Field(default=None, ge=1, le=3650)


class PlatformStats(BaseModel):
    total_users: int
    total_events: int
    total_photos: int
    total_faces: int
    total_storage_bytes: int
    total_revenue_cents: int = 0


@router.get("/users")
async def list_users(
    current_user: User = Depends(get_superadmin_user),
    db: Session = Depends(get_db)
):
    """List all users with event counts and tier info."""
    users = db.query(User).order_by(User.created_at.desc()).all()

    # Batch load user tiers and event counts
    user_tiers = {
        ut.user_id: ut
        for ut in db.query(UserTier).all()
    }
    event_counts = dict(
        db.query(Event.owner_user_id, func.count(Event.id))
        .group_by(Event.owner_user_id)
        .all()
    )

    result = []
    for user in users:
        tier = user_tiers.get(user.id)
        limits = get_effective_limits(tier)
        result.append(UserListItem(
            user_id=str(user.id),
            email=user.email,
            is_verified=user.is_verified,
            is_superadmin=user.is_superadmin,
            is_disabled=user.is_disabled,
            event_count=event_counts.get(user.id, 0),
            tier_name=limits["tier_name"],
            max_events=limits["max_events"],
            max_photos_per_event=limits["max_photos_per_event"],
            created_at=to_utc_iso(user.created_at)
        ))

    return {"users": [u.model_dump() for u in result]}


@router.patch("/users/{user_id}")
async def update_user(
    user_id: str,
    update: UserUpdateRequest,
    current_user: User = Depends(get_superadmin_user),
    db: Session = Depends(get_db)
):
    """Toggle superadmin or disabled status for a user."""
    try:
        target_uuid = uuid.UUID(user_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid user ID")

    target_user = db.query(User).filter(User.id == target_uuid).first()
    if not target_user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    if target_user.id == current_user.id and update.is_disabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot disable your own account"
        )

    if target_user.id == current_user.id and update.is_superadmin is False:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot remove your own superadmin status"
        )

    changes: dict = {}
    if update.is_superadmin is not None:
        changes["is_superadmin"] = update.is_superadmin
        target_user.is_superadmin = update.is_superadmin
    if update.is_disabled is not None:
        changes["is_disabled"] = update.is_disabled
        target_user.is_disabled = update.is_disabled

    db.commit()

    log_action(
        db=db,
        event_id=None,
        actor_type="admin",
        actor_id=current_user.id,
        action="admin_user_update",
        metadata={"target_user_id": str(target_uuid), "target_email": target_user.email, "changes": changes},
    )

    return {
        "user_id": str(target_user.id),
        "email": target_user.email,
        "is_superadmin": target_user.is_superadmin,
        "is_disabled": target_user.is_disabled,
        "message": "User updated successfully"
    }


@router.patch("/users/{user_id}/tier")
async def update_user_tier(
    user_id: str,
    update: UserTierUpdateRequest,
    current_user: User = Depends(get_superadmin_user),
    db: Session = Depends(get_db)
):
    """Override user tier (superadmin only). Used for custom deals."""
    from app.tiers import TIER_CONFIG

    try:
        target_uuid = uuid.UUID(user_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid user ID")

    target_user = db.query(User).filter(User.id == target_uuid).first()
    if not target_user:
        raise HTTPException(status_code=404, detail="User not found")

    valid_tiers = list(TIER_CONFIG.keys()) + ["custom"]
    if update.tier_name not in valid_tiers:
        raise HTTPException(status_code=400, detail=f"Invalid tier. Must be one of: {valid_tiers}")

    # Named tiers (free/starter/pro) read limits from TIER_CONFIG at runtime via
    # tiers.get_effective_limits. Per-row overrides on named tiers are ignored on
    # read, so reject them at write time. Use tier_name='custom' for overrides.
    if update.tier_name == "custom":
        if not update.max_events or not update.max_photos_per_event:
            raise HTTPException(status_code=400, detail="max_events and max_photos_per_event are required for custom tier")
        max_events = update.max_events
        max_photos = update.max_photos_per_event
        # Default to 365 days when the operator does not specify retention.
        # Same fallback used by get_effective_limits for custom rows without
        # a retention_days override.
        retention_days = update.retention_days or 365
        price_cents = 0
    else:
        if (
            update.max_events is not None
            or update.max_photos_per_event is not None
            or update.retention_days is not None
        ):
            raise HTTPException(
                status_code=400,
                detail="max_events / max_photos_per_event / retention_days overrides are only allowed for tier_name='custom'. "
                       "For named tiers, edit tiers.py to change limits for all users.",
            )
        tier_config = TIER_CONFIG[update.tier_name]
        max_events = tier_config["max_events"]
        max_photos = tier_config["max_photos_per_event"]
        retention_days = tier_config["retention_days"]
        price_cents = tier_config.get("monthly_cents", 0)

    user_tier = db.query(UserTier).filter(UserTier.user_id == target_uuid).first()
    if user_tier:
        user_tier.tier_name = update.tier_name
        user_tier.max_events = max_events
        user_tier.max_photos_per_event = max_photos
        # retention_days is persisted only for custom tier (get_effective_limits
        # falls back to TIER_CONFIG for named tiers regardless), but stamp it
        # anyway so the row stays internally consistent.
        user_tier.retention_days = retention_days
        user_tier.price_cents = price_cents
        user_tier.is_active = True
        user_tier.activated_at = datetime.utcnow()
    else:
        user_tier = UserTier(
            user_id=target_uuid,
            tier_name=update.tier_name,
            max_events=max_events,
            max_photos_per_event=max_photos,
            retention_days=retention_days,
            price_cents=price_cents,
            is_active=True,
            activated_at=datetime.utcnow(),
        )
        db.add(user_tier)

    # This endpoint is an explicit superadmin override. Decouple entitlement
    # from any existing Stripe subscription so a later webhook cannot silently
    # reapply the old paid plan over the manual tier.
    prior_sub_id = user_tier.stripe_subscription_id
    prior_sub_status = user_tier.subscription_status
    user_tier.stripe_subscription_id = None
    user_tier.subscription_status = None
    user_tier.billing_interval = None
    user_tier.current_period_end = None
    user_tier.cancel_at_period_end = False
    user_tier.last_subscription_event_at = datetime.utcnow()
    user_tier.last_subscription_event_id = None
    user_tier.last_subscription_event_type = "manual_override"
    user_tier.last_subscription_event_subscription_id = None

    # We do NOT auto-cancel the Stripe subscription — that has user-visible
    # billing/refund consequences and should be an explicit operator decision.
    # Surface the orphan so the operator knows to cancel via the Stripe
    # dashboard if the customer should stop being charged.
    stripe_subscription_orphaned = bool(
        prior_sub_id and prior_sub_status in ("active", "trialing", "past_due")
    )
    if stripe_subscription_orphaned:
        logger.warning(
            "Manual tier override applied to user %s while Stripe subscription %s is still %s. "
            "Cancel it via the Stripe dashboard if the customer should stop being charged.",
            target_uuid, prior_sub_id, prior_sub_status,
        )

    rebalance_event_status(target_uuid, max_events, db)
    db.commit()

    log_action(
        db=db,
        event_id=None,
        actor_type="admin",
        actor_id=current_user.id,
        action="admin_tier_update",
        metadata={
            "target_user_id": str(target_uuid),
            "target_email": target_user.email,
            "tier_name": update.tier_name,
            "max_events": max_events,
            "max_photos_per_event": max_photos,
            "stripe_subscription_orphaned": stripe_subscription_orphaned,
        },
    )

    return {
        "message": f"User tier updated to {update.tier_name}",
        "user_id": user_id,
        "tier_name": user_tier.tier_name,
        "max_events": user_tier.max_events,
        "max_photos_per_event": user_tier.max_photos_per_event,
        "stripe_subscription_orphaned": stripe_subscription_orphaned,
        "stripe_subscription_id": prior_sub_id if stripe_subscription_orphaned else None,
    }


@router.delete("/users/{user_id}")
async def delete_user(
    user_id: str,
    current_user: User = Depends(get_superadmin_user),
    db: Session = Depends(get_db)
):
    """Permanently delete a user and all their data (events, photos, faces)."""
    try:
        target_uuid = uuid.UUID(user_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid user ID")

    target_user = db.query(User).filter(User.id == target_uuid).first()
    if not target_user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    if target_user.id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete your own account"
        )

    # Clean up external resources for each event
    user_events = db.query(Event).filter(Event.owner_user_id == target_uuid).all()
    for event in user_events:
        if settings.compreface_api_key:
            import httpx
            event_faces = db.query(Face).filter(Face.event_id == event.id).all()
            for face in event_faces:
                if face.compreface_subject_id:
                    try:
                        httpx.delete(
                            f"{get_compreface_url()}/api/v1/recognition/faces",
                            headers={"x-api-key": settings.compreface_api_key},
                            params={"subject": face.compreface_subject_id},
                            timeout=5.0,
                        )
                    except Exception as e:
                        # Orphaned faces in CompreFace eventually leak storage there.
                        # Log so admin can run a CompreFace cleanup script later.
                        import logging
                        logging.getLogger(__name__).error(
                            f"CompreFace face deletion failed for subject={face.compreface_subject_id} "
                            f"event={event.id}: {e}"
                        )

        try:
            storage_service.delete_event_photos(event.id)
        except Exception:
            pass

        cache_delete_pattern(f"event_info:{event.slug}")
        cache_delete_pattern(f"gallery:{event.id}:*")
        cache_delete_pattern(f"share:{event.id}:*")

    email = target_user.email
    deleted_event_count = len(user_events)
    db.delete(target_user)
    db.commit()

    # Logged AFTER delete commits so the audit row survives even if the user FK
    # is gone (event_id is nullable, and target_user_id is recorded in metadata).
    log_action(
        db=db,
        event_id=None,
        actor_type="admin",
        actor_id=current_user.id,
        action="admin_user_delete",
        metadata={"target_user_id": str(target_uuid), "target_email": email, "events_deleted": deleted_event_count},
    )

    return {"message": f"User {email} and all their data deleted successfully"}


@router.get("/stats")
async def get_platform_stats(
    current_user: User = Depends(get_superadmin_user),
    db: Session = Depends(get_db)
):
    """Get platform-wide statistics."""
    total_users = db.query(func.count(User.id)).scalar() or 0
    total_events = db.query(func.count(Event.id)).scalar() or 0
    total_photos = db.query(func.count(Image.id)).scalar() or 0
    total_faces = db.query(func.count(Face.id)).scalar() or 0
    total_storage_bytes = db.query(func.sum(Image.size_bytes)).scalar() or 0
    total_revenue_cents = db.query(func.sum(Payment.amount_cents)).filter(Payment.status == "completed").scalar() or 0

    return PlatformStats(
        total_users=total_users,
        total_events=total_events,
        total_photos=total_photos,
        total_faces=total_faces,
        total_storage_bytes=total_storage_bytes,
        total_revenue_cents=total_revenue_cents,
    )


@router.get("/global-analytics")
async def get_global_analytics(
    current_user: User = Depends(get_superadmin_user),
    db: Session = Depends(get_db)
):
    """Get platform-wide analytics from audit logs."""
    total_scans = db.query(func.count(AuditLog.id)).filter(
        AuditLog.action == 'scan'
    ).scalar() or 0

    unique_guests = db.query(func.count(func.distinct(AuditLog.actor_id))).filter(
        AuditLog.actor_type == 'guest'
    ).scalar() or 0

    total_downloads = db.query(func.count(AuditLog.id)).filter(
        AuditLog.action == 'bulk_download'
    ).scalar() or 0

    total_gallery_views = db.query(func.count(AuditLog.id)).filter(
        AuditLog.action == 'gallery_view'
    ).scalar() or 0

    # Group by event id AND name. Pre-fix two events with the same
    # display name ("Wedding", "Annual Dinner") collapsed into one
    # leaderboard row and reported combined scan/guest counts. We
    # include Event.id in the group key and surface it on the
    # response so the frontend can deep-link to the per-event view.
    top_events_raw = db.query(
        Event.id,
        Event.name,
        func.count(AuditLog.id).label('scan_count'),
        func.count(func.distinct(AuditLog.actor_id)).label('guest_count')
    ).join(AuditLog, AuditLog.event_id == Event.id).filter(
        AuditLog.action == 'scan'
    ).group_by(Event.id, Event.name).order_by(
        func.count(AuditLog.id).desc()
    ).limit(5).all()

    top_events = [
        {"event_id": str(row[0]), "name": row[1], "scans": row[2], "guests": row[3]}
        for row in top_events_raw
    ]

    # Same fix as per-event scans_by_day: filter by timestamp cutoff so
    # the dashboard shows ACTUAL last-30-days, not just the oldest 30
    # days that happen to appear first under asc-order.
    scans_by_day_raw = db.query(
        func.date_trunc('day', AuditLog.timestamp).label('date'),
        func.count(AuditLog.id).label('count')
    ).filter(
        AuditLog.action == 'scan',
        AuditLog.timestamp >= datetime.utcnow() - timedelta(days=30),
    ).group_by(
        func.date_trunc('day', AuditLog.timestamp)
    ).order_by(
        func.date_trunc('day', AuditLog.timestamp)
    ).limit(31).all()

    scans_by_day = [
        {"date": to_utc_iso(row[0]) if row[0] else None, "count": row[1]}
        for row in scans_by_day_raw
    ]

    return {
        "total_scans": total_scans,
        "unique_guests": unique_guests,
        "total_downloads": total_downloads,
        "total_gallery_views": total_gallery_views,
        "top_events": top_events,
        "scans_by_day": scans_by_day,
    }


@router.get("/events")
async def admin_list_events(
    current_user: User = Depends(get_superadmin_user),
    db: Session = Depends(get_db),
):
    """List all events with owner tier info (superadmin only)."""
    events = (
        db.query(Event, User.email)
        .outerjoin(User, Event.owner_user_id == User.id)
        .order_by(Event.created_at.desc())
        .all()
    )

    photo_counts = dict(
        db.query(Image.event_id, func.count(Image.id))
        .group_by(Image.event_id)
        .all()
    )

    # Load user tiers and event-level overrides
    user_tiers = {ut.user_id: ut for ut in db.query(UserTier).all()}
    event_tiers = {et.event_id: et for et in db.query(EventTier).all()}

    def _row(event, email):
        ut = user_tiers.get(event.owner_user_id)
        limits = get_effective_limits(ut)
        et = event_tiers.get(event.id)
        return {
            "event_id": str(event.id),
            "name": event.name,
            "date": event.date.isoformat() if event.date else None,
            "owner_email": email,
            "photo_count": photo_counts.get(event.id, 0),
            "user_tier": limits["tier_name"],
            "photo_limit": et.photo_limit if et else limits["max_photos_per_event"],
            "has_override": et is not None,
            "created_at": to_utc_iso(event.created_at),
        }

    return {"events": [_row(event, email) for event, email in events]}


@router.delete("/events/{event_id}")
async def admin_delete_event(
    event_id: str,
    current_user: User = Depends(get_superadmin_user),
    db: Session = Depends(get_db)
):
    """Delete any event (superadmin only, no ownership check)."""
    try:
        event_uuid = uuid.UUID(event_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid event ID")

    event = db.query(Event).filter(Event.id == event_uuid).first()
    if not event:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")

    try:
        delete_compreface_subjects_for_event(db, event_uuid)
    except Exception as e:
        logger.error(f"CompreFace cleanup failed for event {event_uuid}: {e}")

    try:
        storage_service.delete_event_photos(event_uuid)
    except Exception:
        pass

    cache_delete_pattern(f"event_info:{event.slug}")
    cache_delete_pattern(f"gallery:{event_uuid}:*")
    cache_delete_pattern(f"share:{event_uuid}:*")

    owner_email = (
        db.query(User.email).filter(User.id == event.owner_user_id).scalar()
        if event.owner_user_id else None
    )
    event_name = event.name

    db.delete(event)
    db.commit()

    # event_id is nullable now and FK is ON DELETE SET NULL, so logging after
    # the event delete still preserves a trail without dangling refs.
    log_action(
        db=db,
        event_id=None,
        actor_type="admin",
        actor_id=current_user.id,
        action="admin_event_delete",
        metadata={"target_event_id": str(event_uuid), "target_event_name": event_name, "owner_email": owner_email},
    )

    return {"message": "Event deleted successfully", "event_id": str(event_uuid)}


# --- Per-Event Photo Override ---

class EventPhotoOverrideRequest(BaseModel):
    photo_limit: int = Field(..., ge=1, le=1000000)


@router.patch("/events/{event_id}/photo-override")
async def set_event_photo_override(
    event_id: str,
    req: EventPhotoOverrideRequest,
    current_user: User = Depends(get_superadmin_user),
    db: Session = Depends(get_db),
):
    """Set a per-event photo limit override (superadmin only)."""
    try:
        event_uuid = uuid.UUID(event_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid event ID")

    event = db.query(Event).filter(Event.id == event_uuid).first()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    event_tier = db.query(EventTier).filter(EventTier.event_id == event_uuid).first()
    if event_tier:
        event_tier.photo_limit = req.photo_limit
        event_tier.tier_name = "custom"
        event_tier.is_active = True
        event_tier.activated_at = datetime.utcnow()
    else:
        event_tier = EventTier(
            event_id=event_uuid,
            tier_name="custom",
            photo_limit=req.photo_limit,
            price_cents=0,
            is_active=True,
            activated_at=datetime.utcnow(),
        )
        db.add(event_tier)

    db.commit()

    log_action(
        db=db,
        event_id=event_uuid,
        actor_type="admin",
        actor_id=current_user.id,
        action="admin_photo_override_set",
        metadata={"photo_limit": req.photo_limit},
    )

    return {
        "message": f"Photo limit for event set to {req.photo_limit}",
        "event_id": event_id,
        "photo_limit": req.photo_limit,
    }


@router.delete("/events/{event_id}/photo-override")
async def remove_event_photo_override(
    event_id: str,
    current_user: User = Depends(get_superadmin_user),
    db: Session = Depends(get_db),
):
    """Remove per-event photo override, reverting to user tier limit."""
    try:
        event_uuid = uuid.UUID(event_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid event ID")

    event_tier = db.query(EventTier).filter(EventTier.event_id == event_uuid).first()
    if not event_tier:
        raise HTTPException(status_code=404, detail="No override exists for this event")

    db.delete(event_tier)
    db.commit()

    log_action(
        db=db,
        event_id=event_uuid,
        actor_type="admin",
        actor_id=current_user.id,
        action="admin_photo_override_remove",
    )

    return {"message": "Photo override removed", "event_id": event_id}


@router.get("/failed-jobs")
async def list_failed_jobs(
    current_user: User = Depends(get_superadmin_user),
):
    """List all failed jobs across queues."""
    jobs = get_failed_jobs()
    return {"failed_jobs": jobs, "total": len(jobs)}


@router.post("/retry-job/{job_id}")
async def retry_job(
    job_id: str,
    current_user: User = Depends(get_superadmin_user),
    db: Session = Depends(get_db),
):
    """Requeue a failed job for retry."""
    try:
        requeued_id = retry_failed_job(job_id)
        log_action(
            db=db,
            event_id=None,
            actor_type="admin",
            actor_id=current_user.id,
            action="admin_job_retry",
            metadata={"job_id": job_id, "requeued_id": requeued_id},
        )
        return {"message": "Job requeued successfully", "job_id": requeued_id}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job not found or cannot be retried: {str(e)}"
        )


@router.get("/payments")
async def admin_list_payments(
    current_user: User = Depends(get_superadmin_user),
    db: Session = Depends(get_db),
):
    """List all payments platform-wide."""
    payments = (
        db.query(Payment, User.email)
        .outerjoin(User, Payment.user_id == User.id)
        .order_by(Payment.created_at.desc())
        .limit(100)
        .all()
    )

    total_revenue = (
        db.query(func.sum(Payment.amount_cents))
        .filter(Payment.status == "completed")
        .scalar()
        or 0
    )

    return {
        "payments": [
            {
                "payment_id": str(p.id),
                "user_email": email,
                "tier_name": p.tier_name or "unknown",
                "amount_cents": p.amount_cents,
                "currency": p.currency,
                "status": p.status,
                "created_at": to_utc_iso(p.created_at),
            }
            for p, email in payments
        ],
        "total_revenue_cents": total_revenue,
        "total_revenue_display": f"RM {total_revenue / 100:.2f}",
    }


@router.get("/audit-log")
async def admin_list_audit_log(
    actor_type: Optional[str] = None,
    action: Optional[str] = None,
    actor_id: Optional[str] = None,
    event_id: Optional[str] = None,
    q: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
    current_user: User = Depends(get_superadmin_user),
    db: Session = Depends(get_db),
):
    """List audit log entries (superadmin only).

    Filters:
    - actor_type: 'admin' | 'guest' | 'system' (system = automated jobs)
    - action: substring match (e.g. 'admin_user' matches all admin user actions)
    - actor_id: UUID of acting user
    - event_id: UUID of target event
    - q: free-text search across actor email + metadata JSON
    """
    if limit < 1 or limit > 500:
        limit = 100
    if offset < 0:
        offset = 0

    query = (
        db.query(AuditLog, User.email)
        .outerjoin(User, AuditLog.actor_id == User.id)
    )

    if actor_type in ("admin", "guest", "system"):
        query = query.filter(AuditLog.actor_type == actor_type)
    if action:
        query = query.filter(AuditLog.action.ilike(f"%{action}%"))
    if actor_id:
        try:
            query = query.filter(AuditLog.actor_id == uuid.UUID(actor_id))
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid actor_id")
    if event_id:
        try:
            query = query.filter(AuditLog.event_id == uuid.UUID(event_id))
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid event_id")
    if q:
        from sqlalchemy import cast, Text
        like = f"%{q}%"
        # Cast jsonb metadata to text so we can ILIKE-match across keys/values
        # without expanding every metadata field into a separate column. The
        # audit log is bounded by retention so a full scan stays cheap.
        query = query.filter(
            (User.email.ilike(like)) |
            (AuditLog.action.ilike(like)) |
            (cast(AuditLog.metadata_, Text).ilike(like))
        )

    total = query.with_entities(func.count(AuditLog.id)).scalar() or 0

    rows = (
        query.order_by(AuditLog.timestamp.desc())
        .limit(limit)
        .offset(offset)
        .all()
    )

    # Resolve event names in one query for any non-null event_ids in the page.
    event_ids = [a.event_id for a, _ in rows if a.event_id is not None]
    event_names: dict = {}
    if event_ids:
        for eid, ename in db.query(Event.id, Event.name).filter(Event.id.in_(event_ids)).all():
            event_names[eid] = ename

    return {
        "entries": [
            {
                "id": str(a.id),
                "timestamp": to_utc_iso(a.timestamp),
                "actor_type": a.actor_type,
                "actor_id": str(a.actor_id) if a.actor_id else None,
                "actor_email": actor_email,
                "action": a.action,
                "event_id": str(a.event_id) if a.event_id else None,
                "event_name": event_names.get(a.event_id),
                "metadata": a.metadata_ or {},
            }
            for a, actor_email in rows
        ],
        "total": total,
        "limit": limit,
        "offset": offset,
    }
