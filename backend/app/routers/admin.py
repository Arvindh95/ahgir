"""Superadmin management router."""

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import func
from pydantic import BaseModel
import uuid

from app.auth import get_current_user
from app.database import get_db
from app.models import User, Event, Image, Face
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

    return PlatformStats(
        total_users=total_users,
        total_events=total_events,
        total_photos=total_photos,
        total_faces=total_faces,
        total_storage_bytes=total_storage_bytes
    )


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
