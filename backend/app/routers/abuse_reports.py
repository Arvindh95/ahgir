"""Abuse reporting endpoints.

Public:
* POST /report — anonymous file-a-report against an image.

Superadmin:
* GET /admin/abuse-reports — list + filter + sort + paginate.
* GET /admin/abuse-reports/pending-count — nav-badge count.
* POST /admin/abuse-reports/{id}/reveal — mint 5-min review URL + audit.
* POST /admin/abuse-reports/{id}/quarantine — hide from guests.
* POST /admin/abuse-reports/{id}/delete-photo — permanent removal.
* POST /admin/abuse-reports/{id}/dismiss — close as not-abuse.

See ABUSE_REPORTING_PLAN.md for the full design rationale, including the
threat model around the reporting mechanism itself (multi-keyed rate
limits, anti-enumeration, soft-ban) — most of that is Phase 2.
"""

from __future__ import annotations

import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.orm import Session

from app.audit import log_action
from app.cache import cache_delete_pattern
from app.database import get_db
from app.models import AbuseReport, Event, Face, Image, User
from app.rate_limiter import abuse_report_rate_limiter
from app.routers.admin import get_superadmin_user
from app.storage import generate_signed_abuse_review_url
from app.utils.storage_cleanup import safe_delete_compreface_subject, safe_delete_image_photo
from app.utils.time import to_utc_iso

logger = logging.getLogger(__name__)

router = APIRouter(tags=["abuse-reports"])

# Anti-enumeration: a real image_id and a fake one should be
# indistinguishable from the outside. Pad every /report response to take
# at least this much wall time so a probe can't measure DB-lookup latency
# differences. Tuned to ~50ms which is well above DB jitter on the VPS.
_REPORT_MIN_DURATION_SECONDS = 0.05

_VALID_CATEGORIES = {"csam", "nudity", "harassment", "copyright", "violence", "other"}

_FIXED_THANKS_BODY = {"message": "Thank you. We will review this report shortly."}


# ─── Pydantic models ─────────────────────────────────────────────────


class ReportCreateRequest(BaseModel):
    image_id: str
    category: str = Field(..., max_length=32)
    description: Optional[str] = Field(default=None, max_length=2000)
    reporter_email: Optional[EmailStr] = None
    # Honeypot field — frontend NEVER renders this; bots filling every
    # field will populate it and we silently drop the row.
    website: Optional[str] = Field(default=None, max_length=255)


class ReportRow(BaseModel):
    id: str
    image_id: str
    event_id: str
    event_name: Optional[str] = None
    event_slug: Optional[str] = None
    filename: Optional[str] = None
    uploaded_at: Optional[str] = None
    category: str
    description: Optional[str] = None
    reporter_email: Optional[str] = None
    reporter_ip: Optional[str] = None
    status: str
    action_taken: Optional[str] = None
    notes: Optional[str] = None
    created_at: str
    reviewed_at: Optional[str] = None
    reviewed_by_email: Optional[str] = None


class ReportListResponse(BaseModel):
    items: list[ReportRow]
    total: int
    limit: int
    offset: int


class PendingCountResponse(BaseModel):
    pending: int


class RevealResponse(BaseModel):
    review_url: str
    expires_in: int
    status: str
    reviewed_at: Optional[str] = None
    reviewed_by_email: Optional[str] = None


class ActionResponse(BaseModel):
    message: str
    status: str


# ─── Public endpoint ─────────────────────────────────────────────────


@router.post("/report", response_model=dict)
async def file_abuse_report(
    payload: ReportCreateRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    """File an anonymous abuse report against a single image.

    Anti-abuse layers (Phase 1 subset):
    * Per-IP rate limit (5/hour).
    * Honeypot field (silent 200 if populated).
    * Pydantic enforces category enum + length caps + email format.
    * Anti-enumeration: real image_id and fake UUID both return the
      same fixed 200 body, and the handler runs for at least 50ms
      regardless of whether the image exists.
    """
    started = time.monotonic()
    reporter_ip = request.client.host if request.client else "unknown"

    # Honeypot — bots fill every field; legit clients never see this one.
    if payload.website:
        logger.info("abuse-report honeypot hit ip=%s", reporter_ip)
        _pad_duration(started)
        return _FIXED_THANKS_BODY

    # Pydantic max_length=32 already caps the category string. Reject
    # values outside the enum here so the DB CHECK never sees garbage.
    category = (payload.category or "").lower()
    if category not in _VALID_CATEGORIES:
        # Use a 422-like response shape, not the fixed 200 — this is a
        # client bug, not a routine submission.
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"category must be one of {sorted(_VALID_CATEGORIES)}",
        )

    # Per-IP rate limit. Trips a 429 — distinct from the silent honeypot
    # drop and the silent fake-id 200.
    allowed, retry_after = abuse_report_rate_limiter.check_rate_limit(
        reporter_ip, action="abuse_report"
    )
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many reports from your address. Please try again later.",
            headers={"Retry-After": str(retry_after or 3600)},
        )

    # Parse image_id. Bad UUIDs get the same fixed 200 — leaking "this
    # was malformed" would let a probe enumerate the UUID space by
    # error-message shape.
    try:
        image_uuid = uuid.UUID(payload.image_id)
    except (ValueError, TypeError):
        _pad_duration(started)
        return _FIXED_THANKS_BODY

    image = db.query(Image).filter(Image.id == image_uuid).first()
    if not image:
        # Anti-enumeration: same response as a successful submission.
        _pad_duration(started)
        return _FIXED_THANKS_BODY

    report = AbuseReport(
        image_id=image.id,
        event_id=image.event_id,
        category=category,
        description=(payload.description or "").strip() or None,
        reporter_email=(payload.reporter_email.lower() if payload.reporter_email else None),
        reporter_ip=reporter_ip,
        status="pending",
    )
    db.add(report)
    db.commit()

    logger.info(
        "abuse-report filed id=%s image_id=%s category=%s reporter_ip=%s",
        report.id, image.id, category, reporter_ip,
    )
    _pad_duration(started)
    return _FIXED_THANKS_BODY


def _pad_duration(started: float) -> None:
    """Hold the request open until at least _REPORT_MIN_DURATION_SECONDS."""
    elapsed = time.monotonic() - started
    remaining = _REPORT_MIN_DURATION_SECONDS - elapsed
    if remaining > 0:
        time.sleep(remaining)


# ─── Superadmin endpoints ────────────────────────────────────────────


@router.get(
    "/admin/abuse-reports/pending-count",
    response_model=PendingCountResponse,
)
async def get_pending_count(
    _superadmin: User = Depends(get_superadmin_user),
    db: Session = Depends(get_db),
):
    """Count of reports in 'pending' status. Powers the nav-badge."""
    n = db.query(AbuseReport).filter(AbuseReport.status == "pending").count()
    return PendingCountResponse(pending=n)


@router.get("/admin/abuse-reports", response_model=ReportListResponse)
async def list_abuse_reports(
    status_filter: Optional[str] = Query(default="pending", alias="status"),
    category: Optional[str] = Query(default=None),
    sort: str = Query(default="newest"),
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    _superadmin: User = Depends(get_superadmin_user),
    db: Session = Depends(get_db),
):
    """List reports with filters + pagination. Metadata only — photo bytes
    and signed URLs are never returned by this endpoint, preserving the
    'no photo viewer for staff' contract until /reveal is invoked."""
    q = db.query(AbuseReport)
    if status_filter:
        if status_filter not in ("pending", "reviewing", "dismissed", "quarantined", "removed"):
            raise HTTPException(status_code=422, detail="invalid status filter")
        q = q.filter(AbuseReport.status == status_filter)
    if category:
        if category not in _VALID_CATEGORIES:
            raise HTTPException(status_code=422, detail="invalid category filter")
        q = q.filter(AbuseReport.category == category)

    total = q.count()

    if sort == "oldest":
        q = q.order_by(AbuseReport.created_at.asc())
    else:
        q = q.order_by(AbuseReport.created_at.desc())

    rows = q.limit(limit).offset(offset).all()

    # Bulk-join the metadata we render alongside each row.
    image_ids = [r.image_id for r in rows]
    event_ids = [r.event_id for r in rows]
    reviewer_ids = [r.reviewed_by for r in rows if r.reviewed_by]

    images = {
        i.id: i for i in db.query(Image).filter(Image.id.in_(image_ids)).all()
    } if image_ids else {}
    events = {
        e.id: e for e in db.query(Event).filter(Event.id.in_(event_ids)).all()
    } if event_ids else {}
    reviewers = {
        u.id: u for u in db.query(User).filter(User.id.in_(reviewer_ids)).all()
    } if reviewer_ids else {}

    items: list[ReportRow] = []
    for r in rows:
        ev = events.get(r.event_id)
        img = images.get(r.image_id)
        reviewer = reviewers.get(r.reviewed_by) if r.reviewed_by else None
        items.append(ReportRow(
            id=str(r.id),
            image_id=str(r.image_id),
            event_id=str(r.event_id),
            event_name=ev.name if ev else None,
            event_slug=ev.slug if ev else None,
            filename=img.filename if img else None,
            uploaded_at=to_utc_iso(img.uploaded_at) if img and img.uploaded_at else None,
            category=r.category,
            description=r.description,
            reporter_email=r.reporter_email,
            reporter_ip=r.reporter_ip,
            status=r.status,
            action_taken=r.action_taken,
            notes=r.notes,
            created_at=to_utc_iso(r.created_at),
            reviewed_at=to_utc_iso(r.reviewed_at) if r.reviewed_at else None,
            reviewed_by_email=reviewer.email if reviewer else None,
        ))

    return ReportListResponse(items=items, total=total, limit=limit, offset=offset)


def _load_report_or_404(report_id: str, db: Session) -> AbuseReport:
    try:
        rid = uuid.UUID(report_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="invalid report id")
    report = db.query(AbuseReport).filter(AbuseReport.id == rid).first()
    if not report:
        raise HTTPException(status_code=404, detail="report not found")
    return report


@router.post(
    "/admin/abuse-reports/{report_id}/reveal",
    response_model=RevealResponse,
)
async def reveal_report(
    report_id: str,
    current_user: User = Depends(get_superadmin_user),
    db: Session = Depends(get_db),
):
    """Mint a 5-minute signed abuse_review URL and record the access.

    First reveal flips status to 'reviewing' and stamps reviewed_at /
    reviewed_by. Subsequent reveals do NOT clobber those fields
    (first-reviewer wins) but DO write a fresh abuse_review_view audit
    row every time — re-opening a closed report is also traceable.
    """
    report = _load_report_or_404(report_id, db)

    first_review = report.status == "pending"
    if first_review:
        report.status = "reviewing"
        report.reviewed_at = datetime.now(timezone.utc)
        report.reviewed_by = current_user.id
    db.commit()
    db.refresh(report)

    review_url = generate_signed_abuse_review_url(
        event_id=report.event_id,
        image_id=report.image_id,
        expires_minutes=5,
    )

    log_action(
        db=db,
        event_id=report.event_id,
        actor_type="admin",
        actor_id=current_user.id,
        action="abuse_review_view",
        metadata={
            "report_id": str(report.id),
            "image_id": str(report.image_id),
            "category": report.category,
            "first_review": first_review,
        },
    )

    reviewer_email = (
        db.query(User.email).filter(User.id == report.reviewed_by).scalar()
        if report.reviewed_by else None
    )
    return RevealResponse(
        review_url=review_url,
        expires_in=5 * 60,
        status=report.status,
        reviewed_at=to_utc_iso(report.reviewed_at) if report.reviewed_at else None,
        reviewed_by_email=reviewer_email,
    )


def _ensure_actionable(report: AbuseReport) -> None:
    if report.status in ("dismissed", "removed"):
        raise HTTPException(
            status_code=409,
            detail=f"Report already actioned (status={report.status}).",
        )


@router.post(
    "/admin/abuse-reports/{report_id}/quarantine",
    response_model=ActionResponse,
)
async def quarantine_image(
    report_id: str,
    current_user: User = Depends(get_superadmin_user),
    db: Session = Depends(get_db),
):
    """Hide the image from guests by flipping Image.status='quarantined'.

    Photo bytes stay in MinIO, the DB row stays, but every guest endpoint
    filters to status IN ('indexed', 'no_faces') so the image is no
    longer served. /admin/abuse-reports/{id}/reveal still mints an
    abuse_review URL since the photo route bypasses the status check
    for that photo_type.
    """
    report = _load_report_or_404(report_id, db)
    _ensure_actionable(report)

    image = db.query(Image).filter(Image.id == report.image_id).first()
    if not image:
        raise HTTPException(status_code=404, detail="image no longer exists")

    image.status = "quarantined"
    report.status = "quarantined"
    report.action_taken = "quarantine"
    db.commit()

    cache_delete_pattern(f"gallery:{report.event_id}:*")
    cache_delete_pattern(f"share:{report.event_id}:{report.image_id}")

    log_action(
        db=db,
        event_id=report.event_id,
        actor_type="admin",
        actor_id=current_user.id,
        action="abuse_review_quarantine",
        metadata={
            "report_id": str(report.id),
            "image_id": str(report.image_id),
            "category": report.category,
        },
    )
    return ActionResponse(message="Image quarantined.", status=report.status)


@router.post(
    "/admin/abuse-reports/{report_id}/delete-photo",
    response_model=ActionResponse,
)
async def delete_photo_for_report(
    report_id: str,
    current_user: User = Depends(get_superadmin_user),
    db: Session = Depends(get_db),
):
    """Permanently remove the image (MinIO + CompreFace + DB row).

    Reuses the tombstone helpers from storage_cleanup so a transient
    MinIO / CompreFace outage records a retryable cleanup task instead
    of orphaning storage.
    """
    report = _load_report_or_404(report_id, db)
    _ensure_actionable(report)

    image = db.query(Image).filter(Image.id == report.image_id).first()
    if not image:
        raise HTTPException(status_code=404, detail="image no longer exists")

    original_filename = image.filename
    event_id = image.event_id

    # CompreFace subjects per face — tombstone on failure.
    faces = db.query(Face).filter(Face.image_id == image.id).all()
    for face in faces:
        if face.compreface_subject_id:
            safe_delete_compreface_subject(db, face.compreface_subject_id, commit=False)

    # MinIO original + thumb — tombstone on failure.
    safe_delete_image_photo(db, event_id, image.id, commit=False)

    # DB cascade removes Face rows + the AbuseReport via FK ON DELETE
    # CASCADE on abuse_reports.image_id. We have to update the in-memory
    # report row BEFORE the cascade so the audit row gets the right state.
    report.status = "removed"
    report.action_taken = "remove"
    db.delete(image)
    db.commit()

    cache_delete_pattern(f"gallery:{event_id}:*")
    cache_delete_pattern(f"share:{event_id}:{report.image_id}")

    log_action(
        db=db,
        event_id=event_id,
        actor_type="admin",
        actor_id=current_user.id,
        action="abuse_review_delete",
        metadata={
            "report_id": str(report.id),
            "image_id": str(report.image_id),
            "original_filename": original_filename,
            "category": report.category,
        },
    )
    return ActionResponse(message="Photo permanently removed.", status="removed")


@router.post(
    "/admin/abuse-reports/{report_id}/dismiss",
    response_model=ActionResponse,
)
async def dismiss_report(
    report_id: str,
    current_user: User = Depends(get_superadmin_user),
    db: Session = Depends(get_db),
):
    """Close as not-abuse. Image is untouched."""
    report = _load_report_or_404(report_id, db)
    _ensure_actionable(report)

    report.status = "dismissed"
    report.action_taken = "dismiss"
    db.commit()

    log_action(
        db=db,
        event_id=report.event_id,
        actor_type="admin",
        actor_id=current_user.id,
        action="abuse_review_dismiss",
        metadata={
            "report_id": str(report.id),
            "image_id": str(report.image_id),
            "category": report.category,
        },
    )
    return ActionResponse(message="Report dismissed.", status="dismissed")
