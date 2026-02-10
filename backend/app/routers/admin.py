"""Superadmin management router."""

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import func
from pydantic import BaseModel
import uuid

from app.auth import get_current_user
from app.database import get_db
from app.models import User, Event, Image, Face, AuditLog, EventTier, Payment
from app.config import settings, get_compreface_url
from app.storage import storage_service
from app.queue import get_failed_jobs, retry_failed_job

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
    created_at: str


class UserUpdateRequest(BaseModel):
    is_superadmin: Optional[bool] = None
    is_disabled: Optional[bool] = None


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
    """List all users with event counts."""
    users = db.query(User).order_by(User.created_at.desc()).all()

    result = []
    for user in users:
        event_count = db.query(func.count(Event.id)).filter(
            Event.owner_user_id == user.id
        ).scalar() or 0

        result.append(UserListItem(
            user_id=str(user.id),
            email=user.email,
            is_verified=user.is_verified,
            is_superadmin=user.is_superadmin,
            is_disabled=user.is_disabled,
            event_count=event_count,
            created_at=user.created_at.isoformat()
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

    # Prevent disabling yourself
    if target_user.id == current_user.id and update.is_disabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot disable your own account"
        )

    # Prevent removing your own superadmin
    if target_user.id == current_user.id and update.is_superadmin is False:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot remove your own superadmin status"
        )

    if update.is_superadmin is not None:
        target_user.is_superadmin = update.is_superadmin
    if update.is_disabled is not None:
        target_user.is_disabled = update.is_disabled

    db.commit()

    return {
        "user_id": str(target_user.id),
        "email": target_user.email,
        "is_superadmin": target_user.is_superadmin,
        "is_disabled": target_user.is_disabled,
        "message": "User updated successfully"
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
        # Delete CompreFace subjects
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
                    except Exception:
                        pass

        # Delete photos from MinIO
        try:
            storage_service.delete_event_photos(event.id)
        except Exception:
            pass

    email = target_user.email
    db.delete(target_user)
    db.commit()

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

    # Top events by scan count
    top_events_raw = db.query(
        Event.name,
        func.count(AuditLog.id).label('scan_count'),
        func.count(func.distinct(AuditLog.actor_id)).label('guest_count')
    ).join(AuditLog, AuditLog.event_id == Event.id).filter(
        AuditLog.action == 'scan'
    ).group_by(Event.name).order_by(
        func.count(AuditLog.id).desc()
    ).limit(5).all()

    top_events = [
        {"name": row[0], "scans": row[1], "guests": row[2]}
        for row in top_events_raw
    ]

    # Scans by day (last 30 days)
    scans_by_day_raw = db.query(
        func.date_trunc('day', AuditLog.timestamp).label('date'),
        func.count(AuditLog.id).label('count')
    ).filter(
        AuditLog.action == 'scan'
    ).group_by(
        func.date_trunc('day', AuditLog.timestamp)
    ).order_by(
        func.date_trunc('day', AuditLog.timestamp)
    ).limit(30).all()

    scans_by_day = [
        {"date": row[0].isoformat() if row[0] else None, "count": row[1]}
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
    """List all events with tier info (superadmin only)."""
    events = (
        db.query(Event, User.email, EventTier)
        .outerjoin(User, Event.owner_user_id == User.id)
        .outerjoin(EventTier, Event.id == EventTier.event_id)
        .order_by(Event.created_at.desc())
        .all()
    )

    photo_counts = dict(
        db.query(Image.event_id, func.count(Image.id))
        .group_by(Image.event_id)
        .all()
    )

    return {
        "events": [
            {
                "event_id": str(event.id),
                "name": event.name,
                "date": event.date.isoformat() if event.date else None,
                "owner_email": email,
                "photo_count": photo_counts.get(event.id, 0),
                "tier_name": tier.tier_name if tier else "free",
                "photo_limit": tier.photo_limit if tier else 25,
                "created_at": event.created_at.isoformat(),
            }
            for event, email, tier in events
        ]
    }


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

    # Delete photos from storage
    try:
        storage_service.delete_event_photos(event_uuid)
    except Exception:
        pass  # Continue with DB deletion

    db.delete(event)
    db.commit()

    return {"message": "Event deleted successfully", "event_id": str(event_uuid)}


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
):
    """Requeue a failed job for retry."""
    try:
        requeued_id = retry_failed_job(job_id)
        return {"message": "Job requeued successfully", "job_id": requeued_id}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job not found or cannot be retried: {str(e)}"
        )


# --- Tier Management ---

class AdminTierUpdate(BaseModel):
    tier_name: str  # free, standard, premium, custom
    photo_limit: Optional[int] = None  # required for custom
    price_cents: Optional[int] = None


@router.get("/events/{event_id}/tier")
async def admin_get_event_tier(
    event_id: str,
    current_user: User = Depends(get_superadmin_user),
    db: Session = Depends(get_db),
):
    """Get tier details and payment history for any event (superadmin only)."""
    try:
        event_uuid = uuid.UUID(event_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid event ID")

    event = db.query(Event).filter(Event.id == event_uuid).first()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    event_tier = db.query(EventTier).filter(EventTier.event_id == event_uuid).first()
    tier_data = None
    payments_data = []

    if event_tier:
        tier_data = {
            "tier_name": event_tier.tier_name,
            "photo_limit": event_tier.photo_limit,
            "price_cents": event_tier.price_cents,
            "is_active": event_tier.is_active,
            "activated_at": event_tier.activated_at.isoformat() if event_tier.activated_at else None,
        }
        payments = db.query(Payment).filter(Payment.event_tier_id == event_tier.id).order_by(Payment.created_at.desc()).all()
        payments_data = [
            {
                "payment_id": str(p.id),
                "amount_cents": p.amount_cents,
                "currency": p.currency,
                "status": p.status,
                "created_at": p.created_at.isoformat(),
            }
            for p in payments
        ]

    return {
        "event_id": event_id,
        "event_name": event.name,
        "tier": tier_data,
        "payments": payments_data,
    }


@router.patch("/events/{event_id}/tier")
async def admin_update_event_tier(
    event_id: str,
    update: AdminTierUpdate,
    current_user: User = Depends(get_superadmin_user),
    db: Session = Depends(get_db),
):
    """Override tier for any event (superadmin only). Used for custom deals."""
    from datetime import datetime
    from app.tiers import TIER_CONFIG

    try:
        event_uuid = uuid.UUID(event_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid event ID")

    event = db.query(Event).filter(Event.id == event_uuid).first()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    valid_tiers = list(TIER_CONFIG.keys()) + ["custom"]
    if update.tier_name not in valid_tiers:
        raise HTTPException(status_code=400, detail=f"Invalid tier. Must be one of: {valid_tiers}")

    if update.tier_name == "custom" and not update.photo_limit:
        raise HTTPException(status_code=400, detail="photo_limit is required for custom tier")

    # Determine photo_limit and price
    if update.tier_name == "custom":
        photo_limit = update.photo_limit
        price_cents = update.price_cents or 0
    else:
        tier_config = TIER_CONFIG[update.tier_name]
        photo_limit = update.photo_limit or tier_config["photo_limit"]
        price_cents = update.price_cents if update.price_cents is not None else tier_config["price_cents"]

    event_tier = db.query(EventTier).filter(EventTier.event_id == event_uuid).first()
    if event_tier:
        event_tier.tier_name = update.tier_name
        event_tier.photo_limit = photo_limit
        event_tier.price_cents = price_cents
        event_tier.is_active = True
        event_tier.activated_at = datetime.utcnow()
    else:
        event_tier = EventTier(
            event_id=event_uuid,
            tier_name=update.tier_name,
            photo_limit=photo_limit,
            price_cents=price_cents,
            is_active=True,
            activated_at=datetime.utcnow(),
        )
        db.add(event_tier)

    db.commit()

    return {
        "message": f"Event tier updated to {update.tier_name}",
        "event_id": event_id,
        "tier_name": event_tier.tier_name,
        "photo_limit": event_tier.photo_limit,
        "price_cents": event_tier.price_cents,
    }


@router.get("/payments")
async def admin_list_payments(
    current_user: User = Depends(get_superadmin_user),
    db: Session = Depends(get_db),
):
    """List all payments platform-wide."""
    payments = (
        db.query(Payment, User.email, Event.name, EventTier.tier_name)
        .outerjoin(User, Payment.user_id == User.id)
        .outerjoin(EventTier, Payment.event_tier_id == EventTier.id)
        .outerjoin(Event, EventTier.event_id == Event.id)
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
                "event_name": event_name,
                "tier_name": tier_name or "unknown",
                "amount_cents": p.amount_cents,
                "currency": p.currency,
                "status": p.status,
                "created_at": p.created_at.isoformat(),
            }
            for p, email, event_name, tier_name in payments
        ],
        "total_revenue_cents": total_revenue,
        "total_revenue_display": f"RM {total_revenue / 100:.2f}",
    }
