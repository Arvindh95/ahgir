"""
Event management router
"""
from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status, UploadFile, File
from fastapi.responses import Response, StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import func
from pydantic import BaseModel, Field, field_validator
import uuid
import qrcode
from io import BytesIO
import secrets
import string
import hashlib
import logging
import re
import unicodedata
import zipfile
from app.utils.filename import attachment_content_disposition, safe_zip_filename
from app.utils.image_safety import safe_open as safe_open_image
import queue
import threading
from PIL import Image as PILImage, ImageOps

logger = logging.getLogger(__name__)

from app.auth import get_current_user, hash_password
from app.database import get_db
from app.models import User, Event, Image, Face, AuditLog, EventTier, UserTier
from app.storage import storage_service, generate_signed_cover_url
from app.queue import enqueue_face_indexing
from app.audit import log_action
from app.config import settings, get_compreface_url
from app.cache import cache_delete_pattern
from app.tiers import get_effective_limits
from app.utils.compreface import delete_compreface_subjects_for_event
from app.utils.exif import strip_exif_bytes
import httpx

router = APIRouter(prefix="/events", tags=["events"])

_SLUG_INVALID_RE = re.compile(r"[^a-z0-9]+")
_SLUG_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def normalize_public_slug(
    value: str,
    *,
    fallback: Optional[str] = None,
    max_length: int = 255,
    truncate: bool = False,
) -> str:
    """Normalize text into the route-safe public slug format."""
    raw = unicodedata.normalize("NFKD", value.strip().lower())
    ascii_value = raw.encode("ascii", "ignore").decode("ascii")
    slug = _SLUG_INVALID_RE.sub("-", ascii_value).strip("-")

    if not slug:
        if fallback is None:
            raise ValueError("Slug must contain at least one letter or number")
        slug = fallback

    if len(slug) > max_length and not truncate:
        raise ValueError(f"Slug must be {max_length} characters or fewer")
    if len(slug) > max_length:
        slug = slug[:max_length].rstrip("-")

    if not _SLUG_PATTERN.fullmatch(slug):
        raise ValueError("Slug must contain only lowercase letters, numbers, and single hyphens")
    return slug

# Pydantic models
class EventCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    date: Optional[str] = None  # ISO date string
    passcode: Optional[str] = None
    location: Optional[str] = Field(default=None, max_length=500)
    description: Optional[str] = Field(default=None, max_length=2000)
    allow_downloads: bool = True
    # Reject zero/negative (would auto-expire on next cleanup) and absurd
    # upper bounds. Tier ceiling is still enforced server-side after this.
    retention_days: int = Field(default=90, ge=1, le=3650)

class EventResponse(BaseModel):
    event_id: str
    slug: str
    name: str
    date: Optional[str] = None
    guest_link: str
    qr_code_url: str
    owner_user_id: str
    allow_downloads: bool
    retention_days: int
    created_at: datetime

class EventListItem(BaseModel):
    event_id: str
    slug: str
    name: str
    date: Optional[str] = None
    photo_count: int
    indexed_count: int
    face_count: int
    event_status: str = 'active'  # active, frozen, expired
    created_at: datetime

class EventListResponse(BaseModel):
    events: List[EventListItem]

class EventStatusResponse(BaseModel):
    total_photos: int
    pending: int
    indexed: int
    no_faces: int
    failed: int
    total_faces: int
    indexing_percentage: float

class EventTierInfo(BaseModel):
    tier_name: str
    photo_limit: int
    is_active: bool

class UserTierInfo(BaseModel):
    tier_name: str
    max_events: int
    max_photos_per_event: int
    events_used: int
    is_active: bool

class EventDetailResponse(BaseModel):
    event_id: str
    slug: str
    name: str
    date: Optional[str] = None
    guest_link: str
    location: Optional[str] = None
    description: Optional[str] = None
    cover_image_url: Optional[str] = None
    allow_downloads: bool
    retention_days: int
    event_status: str = 'active'  # active, frozen, expired
    status: EventStatusResponse
    tier: Optional[EventTierInfo] = None
    user_tier: Optional[UserTierInfo] = None
    created_at: datetime

# Helper functions
def generate_slug(name: str, db: Session) -> str:
    """Generate a unique slug for an event"""
    # Create route-safe base slug from name, leaving room for "-xxxxxx".
    base_slug = normalize_public_slug(name, fallback="event", max_length=248, truncate=True)
    
    # Add random suffix to ensure uniqueness
    while True:
        suffix = ''.join(secrets.choice(string.ascii_lowercase + string.digits) for _ in range(6))
        slug = f"{base_slug}-{suffix}"
        
        # Check if slug already exists
        existing = db.query(Event).filter(Event.slug == slug).first()
        if not existing:
            return slug

def generate_qr_code(url: str) -> bytes:
    """Generate QR code image for a URL"""
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=4,
    )
    qr.add_data(url)
    qr.make(fit=True)
    
    img = qr.make_image(fill_color="black", back_color="white")
    
    # Convert to bytes
    buffer = BytesIO()
    img.save(buffer, format='PNG')
    buffer.seek(0)
    return buffer.getvalue()

def get_event_status(event_id: uuid.UUID, db: Session) -> EventStatusResponse:
    """Calculate event status statistics"""
    # Get photo counts by status
    status_counts = db.query(
        Image.status,
        func.count(Image.id).label('count')
    ).filter(
        Image.event_id == event_id
    ).group_by(Image.status).all()
    
    # Convert to dict
    counts = {status: count for status, count in status_counts}
    
    total_photos = sum(counts.values())
    pending = counts.get('pending', 0)
    indexed = counts.get('indexed', 0)
    no_faces = counts.get('no_faces', 0)
    failed = counts.get('failed', 0)
    
    # Calculate indexing percentage
    if total_photos > 0:
        indexing_percentage = round((indexed + no_faces) / total_photos * 100, 1)
    else:
        indexing_percentage = 0.0
    
    # Get total face count
    total_faces = db.query(func.sum(Image.face_count)).filter(
        Image.event_id == event_id
    ).scalar() or 0
    
    return EventStatusResponse(
        total_photos=total_photos,
        pending=pending,
        indexed=indexed,
        no_faces=no_faces,
        failed=failed,
        total_faces=total_faces,
        indexing_percentage=indexing_percentage
    )


def ensure_event_mutable(event: Event, current_user: User) -> None:
    """Block owner-side mutations for frozen or otherwise inactive events."""
    if current_user.is_superadmin or event.status == "active":
        return

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail={
            "code": "EVENT_NOT_ACTIVE",
            "message": "This event is not active. Upgrade or delete a newer event to reactivate it before making changes.",
            "event_status": event.status,
        },
    )

# Endpoints
@router.post("", response_model=EventResponse, status_code=status.HTTP_201_CREATED)
async def create_event(
    event_data: EventCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Create a new Event
    
    - **name**: Event name (e.g., "Smith Wedding")
    - **date**: Optional event date (ISO format)
    - **passcode**: Optional passcode for guest access
    - **allow_downloads**: Whether guests can download photos (default: true)
    - **retention_days**: Days to retain event data (default: 90)
    
    Returns the created event with guest link and QR code URL
    """
    # Event creation limit (superadmin bypasses). Lock UserTier row to prevent
    # two concurrent create_event calls from both passing the count check.
    if not current_user.is_superadmin:
        user_tier = (
            db.query(UserTier)
            .filter(UserTier.user_id == current_user.id)
            .with_for_update()
            .first()
        )
        if not user_tier:
            user_tier = UserTier(
                user_id=current_user.id,
                tier_name="free",
                max_events=1,
                max_photos_per_event=50,
                price_cents=0,
                is_active=True,
                activated_at=datetime.utcnow()
            )
            db.add(user_tier)
            db.commit()
            user_tier = (
                db.query(UserTier)
                .filter(UserTier.user_id == current_user.id)
                .with_for_update()
                .first()
            )

        limits = get_effective_limits(user_tier)
        # Only count active events - frozen events from a prior downgrade
        # don't occupy a slot (they're read-only and unfreeze on upgrade).
        current_event_count = db.query(func.count(Event.id)).filter(
            Event.owner_user_id == current_user.id,
            Event.status == 'active',
        ).scalar() or 0

        if current_event_count >= limits["max_events"]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "code": "EVENT_LIMIT_REACHED",
                    "message": f"You have reached the maximum of {limits['max_events']} active event(s) on the {limits['tier_name']} tier. Upgrade to create more events.",
                    "current_count": current_event_count,
                    "max_events": limits["max_events"],
                    "tier": limits["tier_name"],
                }
            )

        # Clamp per-event retention to tier ceiling. Photographer can set a
        # shorter retention but cannot exceed the tier's limit.
        tier_retention = limits.get("retention_days") or 30
        if event_data.retention_days > tier_retention:
            event_data.retention_days = tier_retention

    # Generate unique slug
    slug = generate_slug(event_data.name, db)

    # Hash passcode if provided
    passcode_hash = None
    if event_data.passcode:
        passcode_hash = hash_password(event_data.passcode)

    # Parse date if provided
    event_date = None
    if event_data.date:
        try:
            event_date = datetime.fromisoformat(event_data.date).date()
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid date format. Use ISO format (YYYY-MM-DD)"
            )

    # Create event
    new_event = Event(
        owner_user_id=current_user.id,
        slug=slug,
        name=event_data.name,
        date=event_date,
        passcode_hash=passcode_hash,
        location=event_data.location,
        description=event_data.description,
        allow_downloads=event_data.allow_downloads,
        retention_days=event_data.retention_days
    )

    db.add(new_event)
    db.commit()
    db.refresh(new_event)

    # Log event creation
    log_action(
        db=db,
        event_id=new_event.id,
        actor_type='admin',
        actor_id=current_user.id,
        action='create_event',
        metadata={'event_name': new_event.name}
    )
    
    # Generate guest link (assuming domain is configured)
    # In production, this would use the actual domain from config
    guest_link = f"{settings.frontend_url}/e/{slug}"
    qr_code_url = f"{settings.frontend_url}/api/events/{new_event.id}/qr"
    
    return EventResponse(
        event_id=str(new_event.id),
        slug=new_event.slug,
        name=new_event.name,
        date=new_event.date.isoformat() if new_event.date else None,
        guest_link=guest_link,
        qr_code_url=qr_code_url,
        owner_user_id=str(new_event.owner_user_id),
        allow_downloads=new_event.allow_downloads,
        retention_days=new_event.retention_days,
        created_at=new_event.created_at
    )

@router.get("", response_model=EventListResponse)
async def list_events(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    List all Events owned by the current Admin
    
    Returns a list of events with photo counts and indexing status
    """
    # Query events - superadmin sees all, regular users see only their own
    if current_user.is_superadmin:
        events = db.query(Event).order_by(Event.created_at.desc()).all()
    else:
        events = db.query(Event).filter(
            Event.owner_user_id == current_user.id
        ).order_by(Event.created_at.desc()).all()
    
    # Build response with counts
    event_list = []
    for event in events:
        # Get photo count
        photo_count = db.query(func.count(Image.id)).filter(
            Image.event_id == event.id
        ).scalar() or 0
        
        # Get indexed count
        indexed_count = db.query(func.count(Image.id)).filter(
            Image.event_id == event.id,
            Image.status == 'indexed'
        ).scalar() or 0
        
        # Get total face count
        face_count = db.query(func.sum(Image.face_count)).filter(
            Image.event_id == event.id
        ).scalar() or 0
        
        event_list.append(EventListItem(
            event_id=str(event.id),
            slug=event.slug,
            name=event.name,
            date=event.date.isoformat() if event.date else None,
            photo_count=photo_count,
            indexed_count=indexed_count,
            face_count=face_count,
            event_status=event.status or 'active',
            created_at=event.created_at
        ))
    
    return EventListResponse(events=event_list)

@router.get("/{event_id}", response_model=EventDetailResponse)
async def get_event(
    event_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get Event details with status information
    
    Requires ownership validation - only the event owner can access
    """
    # Parse event_id
    try:
        event_uuid = uuid.UUID(event_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid event ID format"
        )
    
    # Query event
    event = db.query(Event).filter(Event.id == event_uuid).first()
    
    if not event:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Event not found"
        )
    
    # Validate ownership (superadmin bypasses)
    if not current_user.is_superadmin and event.owner_user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to access this event"
        )

    # Get status information
    status_info = get_event_status(event.id, db)
    
    # Generate guest link
    guest_link = f"{settings.frontend_url}/e/{event.slug}"
    
    # Generate signed cover image URL if exists (15-min expiry)
    cover_image_url = None
    if event.cover_image:
        cover_image_url = generate_signed_cover_url(event.id)

    # Get per-event tier override info
    tier_info = None
    event_tier = db.query(EventTier).filter(EventTier.event_id == event.id).first()
    if event_tier:
        tier_info = EventTierInfo(
            tier_name=event_tier.tier_name,
            photo_limit=event_tier.photo_limit,
            is_active=event_tier.is_active,
        )

    # Get user tier info (limits derived from config so tiers.py changes propagate)
    user_tier_info = None
    user_tier = db.query(UserTier).filter(UserTier.user_id == event.owner_user_id).first()
    if user_tier:
        limits = get_effective_limits(user_tier)
        events_used = db.query(func.count(Event.id)).filter(
            Event.owner_user_id == event.owner_user_id
        ).scalar() or 0
        user_tier_info = UserTierInfo(
            tier_name=limits["tier_name"],
            max_events=limits["max_events"],
            max_photos_per_event=limits["max_photos_per_event"],
            events_used=events_used,
            is_active=user_tier.is_active,
        )

    return EventDetailResponse(
        event_id=str(event.id),
        slug=event.slug,
        name=event.name,
        date=event.date.isoformat() if event.date else None,
        guest_link=guest_link,
        location=event.location,
        description=event.description,
        cover_image_url=cover_image_url,
        allow_downloads=event.allow_downloads,
        retention_days=event.retention_days,
        event_status=event.status or 'active',
        status=status_info,
        tier=tier_info,
        user_tier=user_tier_info,
        created_at=event.created_at
    )

class EventUpdate(BaseModel):
    slug: Optional[str] = None
    location: Optional[str] = None
    description: Optional[str] = None

    @field_validator("slug")
    @classmethod
    def normalize_slug(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        return normalize_public_slug(v)

@router.patch("/{event_id}")
async def update_event(
    event_id: str,
    update_data: EventUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update event details (slug, location, description)"""
    try:
        event_uuid = uuid.UUID(event_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid event ID format")

    event = db.query(Event).filter(Event.id == event_uuid).first()
    if not event:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")
    if not current_user.is_superadmin and event.owner_user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You do not have permission to update this event")

    ensure_event_mutable(event, current_user)

    old_slug = event.slug
    if update_data.slug is not None:
        existing = db.query(Event).filter(Event.slug == update_data.slug, Event.id != event_uuid).first()
        if existing:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Slug is already in use")
        event.slug = update_data.slug
    if update_data.location is not None:
        event.location = update_data.location
    if update_data.description is not None:
        event.description = update_data.description

    db.commit()
    db.refresh(event)

    # Invalidate event info cache (both old and new slug if changed)
    cache_delete_pattern(f"event_info:{event.slug}")
    if old_slug != event.slug:
        cache_delete_pattern(f"event_info:{old_slug}")
        # Share payloads embed event_slug; without this, OG previews and
        # share-page redirects keep pointing at the old slug for up to 60s.
        cache_delete_pattern(f"share:{event_uuid}:*")

    return {"message": "Event updated", "slug": event.slug}

@router.post("/{event_id}/cover")
async def upload_cover_image(
    event_id: str,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Upload a cover/hero image for the event"""
    try:
        event_uuid = uuid.UUID(event_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid event ID format")

    event = db.query(Event).filter(Event.id == event_uuid).first()
    if not event:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")
    if not current_user.is_superadmin and event.owner_user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permission denied")

    ensure_event_mutable(event, current_user)

    # Validate file type
    if not file.content_type or not file.content_type.startswith('image/'):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="File must be an image")

    max_bytes = settings.max_upload_bytes
    content_length = getattr(file, "size", None)
    if content_length is not None and content_length > max_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Cover image exceeds {max_bytes // (1024*1024)}MB upload limit"
        )

    # Read and process image
    image_bytes = await file.read()
    if len(image_bytes) > max_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Cover image exceeds {max_bytes // (1024*1024)}MB upload limit"
        )
    img = safe_open_image(image_bytes)
    # Apply EXIF orientation (phones store rotation in metadata)
    img = ImageOps.exif_transpose(img)
    if img.mode in ('RGBA', 'LA', 'P'):
        img = img.convert('RGB')

    # Resize to max 1920px on longest side for cover
    max_size = 1920
    img.thumbnail((max_size, max_size), PILImage.LANCZOS)
    buffer = BytesIO()
    img.save(buffer, format='JPEG', quality=85)
    buffer.seek(0)

    # Upload via storage_service so retry/backoff applies consistently
    cover_bytes = buffer.getvalue()
    object_key = storage_service.upload_cover(event_uuid, cover_bytes)

    # Update event
    event.cover_image = object_key
    db.commit()

    # Invalidate event info cache so guest page picks up the new cover
    cache_delete_pattern(f"event_info:{event.slug}")

    cover_url = generate_signed_cover_url(event_uuid)
    return {"message": "Cover image uploaded", "cover_image_url": cover_url}

@router.get("/{event_id}/qr")
async def get_event_qr_code(
    event_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get QR code image for Event guest link
    
    Requires ownership validation - only the event owner can access
    Returns a PNG image
    """
    # Parse event_id
    try:
        event_uuid = uuid.UUID(event_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid event ID format"
        )
    
    # Query event
    event = db.query(Event).filter(Event.id == event_uuid).first()
    
    if not event:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Event not found"
        )
    
    # Validate ownership (superadmin bypasses)
    if not current_user.is_superadmin and event.owner_user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to access this event"
        )

    # Generate guest link and QR code
    guest_link = f"{settings.frontend_url}/e/{event.slug}"
    qr_code_bytes = generate_qr_code(guest_link)
    
    return Response(content=qr_code_bytes, media_type="image/png")


# Photo upload models
class PhotoUploadResult(BaseModel):
    image_id: str
    filename: str
    size_bytes: int
    status: str

class PhotoUploadFailure(BaseModel):
    filename: str
    reason: str
    # category lets the UI show different messages per failure type. Keep
    # values stable — frontend keys off them.
    category: str = "upload_error"  # oversize | invalid_format | duplicate | upload_error


class PhotoUploadResponse(BaseModel):
    uploaded: List[PhotoUploadResult]
    failed: List[PhotoUploadFailure]

class PhotoListItem(BaseModel):
    image_id: str
    filename: str
    status: str
    face_count: int
    thumbnail_url: str
    download_url: str
    uploaded_at: datetime

class PhotoListResponse(BaseModel):
    photos: List[PhotoListItem]
    total: int
    page: int
    limit: int

class PhotoDeleteResponse(BaseModel):
    message: str
    image_id: str

class ReindexResponse(BaseModel):
    message: str
    queued_count: int

class AuditLogItem(BaseModel):
    log_id: str
    event_id: str
    actor_type: str
    action: str
    metadata: dict
    timestamp: datetime

class AuditLogListResponse(BaseModel):
    logs: List[AuditLogItem]
    total: int
    page: int
    limit: int

# Helper functions for photo processing
def compute_file_hash(file_data: bytes) -> str:
    """Compute SHA256 hash of file data"""
    return hashlib.sha256(file_data).hexdigest()

def validate_image_format(file_data: bytes, filename: str) -> bool:
    """Validate that file is a valid JPEG, PNG, or MPO image and not a
    decompression bomb. Returns False (logs reason) for any rejection so the
    caller can produce a single 400 response with the failed filenames.
    """
    try:
        img = safe_open_image(file_data)
        # Check format - MPO is multi-picture JPEG used by Samsung and other phones
        if img.format not in ['JPEG', 'PNG', 'MPO']:
            logger.warning(f"Rejected {filename}: format is '{img.format}', expected JPEG/PNG/MPO")
            return False
        return True
    except HTTPException as e:
        logger.warning(f"Rejected {filename}: {e.detail}")
        return False
    except Exception as e:
        logger.warning(f"Rejected {filename}: validation error: {e}")
        return False

from app.utils.thumbnail import generate_thumbnail

_GPS_IFD_TAG = 0x8825  # ExifTags.GPSInfo


def extract_exif_data(file_data: bytes) -> dict:
    """Extract EXIF metadata from image, stripping GPS to protect user privacy."""
    try:
        img = safe_open_image(file_data)
        exif_data = img.getexif()

        if not exif_data:
            return {}

        def make_json_safe(v):
            if isinstance(v, (bytes, bytearray)):
                return str(v)
            elif isinstance(v, (int, float, str, bool)) or v is None:
                return v
            elif isinstance(v, (list, tuple)):
                return [make_json_safe(i) for i in v]
            elif isinstance(v, dict):
                return {str(k): make_json_safe(val) for k, val in v.items()}
            else:
                return float(v) if hasattr(v, '__float__') else str(v)

        exif_dict = {}
        for tag_id, value in exif_data.items():
            if tag_id == _GPS_IFD_TAG:
                continue
            exif_dict[str(tag_id)] = make_json_safe(value)

        return exif_dict
    except Exception:
        return {}

# Photo endpoints
@router.post("/{event_id}/photos", response_model=PhotoUploadResponse, status_code=status.HTTP_201_CREATED)
async def upload_photos(
    event_id: str,
    files: List[UploadFile] = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Upload photos to an Event
    
    - **event_id**: UUID of the event
    - **files**: List of image files (JPEG or PNG)
    
    Returns list of uploaded photos and any duplicates detected
    """
    # Parse event_id
    try:
        event_uuid = uuid.UUID(event_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid event ID format"
        )
    
    # Query event and validate ownership
    event = db.query(Event).filter(Event.id == event_uuid).first()
    
    if not event:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Event not found"
        )
    
    # Validate ownership (superadmin bypasses)
    if not current_user.is_superadmin and event.owner_user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to upload photos to this event"
        )

    ensure_event_mutable(event, current_user)

    def _lock_and_get_photo_capacity():
        event_tier = (
            db.query(EventTier)
            .filter(EventTier.event_id == event_uuid)
            .with_for_update()
            .first()
        )
        user_tier = (
            db.query(UserTier)
            .filter(UserTier.user_id == current_user.id)
            .with_for_update()
            .first()
        )

        if not user_tier:
            user_tier = UserTier(
                user_id=current_user.id,
                tier_name="free",
                max_events=1,
                max_photos_per_event=50,
                price_cents=0,
                is_active=True,
                activated_at=datetime.utcnow()
            )
            db.add(user_tier)
            db.flush()

        limits = get_effective_limits(user_tier)
        effective_limit = event_tier.photo_limit if event_tier else limits["max_photos_per_event"]
        tier_label = event_tier.tier_name if event_tier else limits["tier_name"]

        current_photo_count = db.query(func.count(Image.id)).filter(
            Image.event_id == event_uuid
        ).scalar() or 0

        return current_photo_count, effective_limit, tier_label

    # Quota enforcement (superadmin bypasses).
    # Lock UserTier (and EventTier override) rows so two concurrent uploads cannot
    # both pass the limit check before either writes images.
    if not current_user.is_superadmin:
        current_photo_count, effective_limit, tier_label = _lock_and_get_photo_capacity()
        incoming_count = len(files)
        if current_photo_count + incoming_count > effective_limit:
            remaining = max(0, effective_limit - current_photo_count)
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "code": "PHOTO_LIMIT_EXCEEDED",
                    "message": f"Photo limit reached. You have {remaining} upload(s) remaining ({current_photo_count}/{effective_limit}).",
                    "current_count": current_photo_count,
                    "photo_limit": effective_limit,
                    "tier": tier_label,
                    "remaining": remaining,
                }
            )

    uploaded = []
    failed: List[PhotoUploadFailure] = []

    max_bytes = settings.max_upload_bytes
    for file in files:
        try:
            # Reject oversized uploads before reading entire payload into memory.
            # Prefer Content-Length when available; fall back to streaming with cap.
            content_length = getattr(file, "size", None)
            if content_length is not None and content_length > max_bytes:
                failed.append(PhotoUploadFailure(
                    filename=file.filename,
                    reason=f"File exceeds {max_bytes // (1024*1024)}MB upload limit",
                    category="oversize",
                ))
                continue

            # Read file data
            file_data = await file.read()
            if len(file_data) > max_bytes:
                failed.append(PhotoUploadFailure(
                    filename=file.filename,
                    reason=f"File exceeds {max_bytes // (1024*1024)}MB upload limit",
                    category="oversize",
                ))
                continue

            # Validate image format (incl. decompression-bomb guard)
            if not validate_image_format(file_data, file.filename):
                logger.warning(f"Upload rejected - invalid format: {file.filename} (size={len(file_data)}, content_type={file.content_type})")
                failed.append(PhotoUploadFailure(
                    filename=file.filename,
                    reason="Invalid image format. Only JPEG and PNG are supported, and the image must be under 50 megapixels.",
                    category="invalid_format",
                ))
                continue

            # Compute hash (stored for reference)
            file_hash = compute_file_hash(file_data)

            # Check for duplicate filename within this event
            existing = db.query(Image).filter(
                Image.event_id == event_uuid,
                Image.filename == file.filename
            ).first()

            if existing:
                logger.warning(f"Upload rejected - duplicate filename: {file.filename} (existing image_id={existing.id})")
                failed.append(PhotoUploadFailure(
                    filename=file.filename,
                    reason="File with this name already exists in event",
                    category="duplicate",
                ))
                continue
            
            # Get image dimensions (with decompression-bomb guard)
            img = safe_open_image(file_data)
            width, height = img.size
            
            # Extract EXIF data
            exif_data = extract_exif_data(file_data)
            # Strip EXIF/GPS from bytes before persisting; the DB-side metadata
            # is sanitized separately, but originals are served back to guests
            # when allow_downloads is on.
            original_bytes = strip_exif_bytes(file_data)
            if len(original_bytes) > max_bytes:
                failed.append(PhotoUploadFailure(
                    filename=file.filename,
                    reason=f"Processed file exceeds {max_bytes // (1024*1024)}MB upload limit",
                    category="oversize",
                ))
                continue

            if not current_user.is_superadmin:
                current_count, effective_limit, tier_label = _lock_and_get_photo_capacity()
                if current_count >= effective_limit:
                    remaining = max(0, effective_limit - current_count)
                    # No pending writes at this point (each successful iteration
                    # ends with commit). Commit releases the locks taken by the
                    # capacity check and is safe even if a future maintainer
                    # adds staged DB writes earlier in the iteration.
                    db.commit()
                    failed.append(PhotoUploadFailure(
                        filename=file.filename,
                        reason=f"Photo limit reached. You have {remaining} upload(s) remaining ({current_count}/{effective_limit}).",
                        category="upload_error",
                    ))
                    continue
            
            # Create image record
            image_id = uuid.uuid4()
            new_image = Image(
                id=image_id,
                event_id=event_uuid,
                filename=file.filename,
                file_hash=file_hash,
                size_bytes=len(original_bytes),
                width=width,
                height=height,
                exif_data=exif_data,
                status='pending',
                face_count=0
            )
            
            db.add(new_image)
            storage_service.upload_photo(
                event_id=event_uuid,
                image_id=image_id,
                photo_data=original_bytes,
                photo_type='original'
            )
            
            # Generate and store thumbnail
            thumbnail_data = generate_thumbnail(file_data)
            storage_service.upload_photo(
                event_id=event_uuid,
                image_id=image_id,
                photo_data=thumbnail_data,
                photo_type='thumb'
            )
            
            # Commit to database
            db.commit()
            
            # Log photo upload
            log_action(
                db=db,
                event_id=event_uuid,
                actor_type='admin',
                actor_id=current_user.id,
                action='upload',
                metadata={
                    'filename': file.filename,
                    'image_id': str(image_id),
                    'size_bytes': len(original_bytes)
                }
            )
            
            # Queue face indexing job. Failure here means the photo will sit at status='pending'
            # forever unless an admin runs the reindex tooling, so we audit-log the failure
            # for visibility instead of silently continuing.
            try:
                enqueue_face_indexing(str(image_id))
            except Exception as e:
                logger.error(
                    f"Failed to queue face indexing job for image {image_id}: {e}",
                    exc_info=True,
                )
                log_action(
                    db=db,
                    event_id=event_uuid,
                    actor_type='admin',
                    actor_id=current_user.id,
                    action='index_enqueue_failed',
                    metadata={
                        'image_id': str(image_id),
                        'filename': file.filename,
                        'error': str(e),
                    }
                )
            
            uploaded.append(PhotoUploadResult(
                image_id=str(image_id),
                filename=file.filename,
                size_bytes=len(file_data),
                status='pending'
            ))
            
        except Exception as e:
            logger.error(f"Upload failed for {file.filename}: {str(e)}", exc_info=True)
            db.rollback()
            failed.append(PhotoUploadFailure(
                filename=file.filename,
                reason=f"Upload failed: {str(e)}",
                category="upload_error",
            ))

    # Invalidate gallery cache for this event
    if uploaded:
        cache_delete_pattern(f"gallery:{event_uuid}:*")

    return PhotoUploadResponse(
        uploaded=uploaded,
        failed=failed
    )

@router.get("/{event_id}/photos", response_model=PhotoListResponse)
async def list_photos(
    event_id: str,
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    status_filter: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    List photos for an Event with pagination and filtering
    
    - **event_id**: UUID of the event
    - **page**: Page number (default: 1)
    - **limit**: Items per page (default: 50)
    - **status_filter**: Filter by status (pending, indexed, no_faces, failed)
    
    Returns paginated list of photos with presigned thumbnail URLs
    """
    # Parse event_id
    try:
        event_uuid = uuid.UUID(event_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid event ID format"
        )
    
    # Query event and validate ownership
    event = db.query(Event).filter(Event.id == event_uuid).first()
    
    if not event:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Event not found"
        )
    
    # Validate ownership (superadmin bypasses)
    if not current_user.is_superadmin and event.owner_user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to access this event"
        )

    # Build query
    query = db.query(Image).filter(Image.event_id == event_uuid)
    
    # Apply status filter if provided
    if status_filter:
        if status_filter not in ['pending', 'indexed', 'no_faces', 'failed']:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid status filter"
            )
        query = query.filter(Image.status == status_filter)
    
    # Get total count
    total = query.count()
    
    # Apply pagination
    offset = (page - 1) * limit
    images = query.order_by(Image.uploaded_at.desc()).offset(offset).limit(limit).all()
    
    # Build response with presigned URLs
    photo_list = []
    for image in images:
        thumbnail_url = storage_service.generate_url(
            event_id=event_uuid, image_id=image.id, photo_type='thumb'
        )
        download_url = storage_service.generate_url(
            event_id=event_uuid, image_id=image.id, photo_type='original'
        )

        photo_list.append(PhotoListItem(
            image_id=str(image.id),
            filename=image.filename,
            status=image.status,
            face_count=image.face_count,
            thumbnail_url=thumbnail_url,
            download_url=download_url,
            uploaded_at=image.uploaded_at
        ))
    
    return PhotoListResponse(
        photos=photo_list,
        total=total,
        page=page,
        limit=limit
    )

@router.delete("/{event_id}/photos/{image_id}", response_model=PhotoDeleteResponse)
async def delete_photo(
    event_id: str,
    image_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Delete a photo from an Event
    
    - **event_id**: UUID of the event
    - **image_id**: UUID of the image
    
    Requires ownership validation
    """
    # Parse UUIDs
    try:
        event_uuid = uuid.UUID(event_id)
        image_uuid = uuid.UUID(image_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid UUID format"
        )
    
    # Query event and validate ownership
    event = db.query(Event).filter(Event.id == event_uuid).first()
    
    if not event:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Event not found"
        )
    
    # Validate ownership (superadmin bypasses)
    if not current_user.is_superadmin and event.owner_user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to delete photos from this event"
        )

    # Query image
    image = db.query(Image).filter(
        Image.id == image_uuid,
        Image.event_id == event_uuid
    ).first()
    
    if not image:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Image not found"
        )
    
    # Delete face subjects from CompreFace
    from app.models import Face
    faces = db.query(Face).filter(Face.image_id == image_uuid).all()
    for face in faces:
        if face.compreface_subject_id:
            try:
                import httpx
                httpx.delete(
                    f"{get_compreface_url()}/api/v1/recognition/faces",
                    params={"subject": face.compreface_subject_id},
                    headers={"x-api-key": settings.compreface_api_key},
                    timeout=5.0
                )
            except Exception:
                pass

    # Delete from MinIO (both original and thumbnail)
    try:
        storage_service.delete_photo(
            event_id=event_uuid,
            image_id=image_uuid
        )
    except Exception as e:
        logger.warning(f"Failed to delete MinIO objects for image {image_uuid}: {e}")

    # Delete CompreFace subjects for this image's faces
    if settings.compreface_api_key:
        image_faces = db.query(Face).filter(Face.image_id == image_uuid).all()
        for face in image_faces:
            if face.compreface_subject_id:
                try:
                    httpx.delete(
                        f"{get_compreface_url()}/api/v1/recognition/faces",
                        headers={"x-api-key": settings.compreface_api_key},
                        params={"subject": face.compreface_subject_id},
                        timeout=10.0,
                    )
                except Exception as e:
                    logger.warning(f"Failed to delete CompreFace subject {face.compreface_subject_id}: {e}")

    # Delete from database (cascades to faces)
    db.delete(image)
    db.commit()
    
    # Log photo deletion
    log_action(
        db=db,
        event_id=event_uuid,
        actor_type='admin',
        actor_id=current_user.id,
        action='delete',
        metadata={
            'image_id': str(image_uuid),
            'filename': image.filename
        }
    )
    
    # Invalidate gallery and public share cache for this photo
    cache_delete_pattern(f"gallery:{event_uuid}:*")
    cache_delete_pattern(f"share:{event_uuid}:{image_uuid}")

    return PhotoDeleteResponse(
        message="Photo deleted",
        image_id=str(image_uuid)
    )


class BulkPhotoRequest(BaseModel):
    image_ids: List[str]


@router.post("/{event_id}/photos/bulk-delete")
async def bulk_delete_photos(
    event_id: str,
    request: BulkPhotoRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Delete multiple photos at once."""
    try:
        event_uuid = uuid.UUID(event_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid event ID")

    event = db.query(Event).filter(Event.id == event_uuid).first()
    if not event:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")
    if not current_user.is_superadmin and event.owner_user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized")

    if not request.image_ids:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No images specified")

    image_uuids = []
    for img_id in request.image_ids:
        try:
            image_uuids.append(uuid.UUID(img_id))
        except ValueError:
            pass

    images = db.query(Image).filter(Image.event_id == event_uuid, Image.id.in_(image_uuids)).all()
    deleted = 0
    deleted_image_ids = []
    for image in images:
        # Clean up CompreFace subjects
        if settings.compreface_api_key:
            faces = db.query(Face).filter(Face.image_id == image.id).all()
            for face in faces:
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

        # Delete from MinIO
        try:
            storage_service.delete_photo(event_id=event_uuid, image_id=image.id)
        except Exception as e:
            logger.warning(f"Failed to delete MinIO objects for image {image.id}: {e}")

        db.delete(image)
        deleted += 1
        deleted_image_ids.append(image.id)

    db.commit()

    log_action(
        db=db,
        event_id=event_uuid,
        actor_type='admin',
        actor_id=current_user.id,
        action='delete',
        metadata={'bulk_delete': True, 'count': deleted}
    )

    # Invalidate gallery and public share caches for deleted photos
    cache_delete_pattern(f"gallery:{event_uuid}:*")
    for image_id in deleted_image_ids:
        cache_delete_pattern(f"share:{event_uuid}:{image_id}")

    return {"message": f"Deleted {deleted} photos", "deleted": deleted}


@router.post("/{event_id}/photos/download-zip")
async def admin_download_zip(
    event_id: str,
    request: BulkPhotoRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Download selected photos as a ZIP file (admin)."""
    try:
        event_uuid = uuid.UUID(event_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid event ID")

    event = db.query(Event).filter(Event.id == event_uuid).first()
    if not event:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")
    if not current_user.is_superadmin and event.owner_user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized")

    if not request.image_ids:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No images specified")

    image_uuids = []
    for img_id in request.image_ids:
        try:
            image_uuids.append(uuid.UUID(img_id))
        except ValueError:
            pass

    images = db.query(Image).filter(Image.event_id == event_uuid, Image.id.in_(image_uuids)).all()
    if not images:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No valid images found")

    # Same caps as download-all-zip — a hand-crafted image_ids list with
    # thousands of UUIDs would otherwise tie up MinIO + a worker for minutes.
    total_bytes = sum((img.size_bytes or 0) for img in images)
    max_bytes = settings.bulk_download_max_bytes
    if total_bytes > max_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail={
                "code": "DOWNLOAD_TOO_LARGE",
                "message": (
                    f"Total download size {total_bytes // (1024*1024)} MB exceeds "
                    f"{max_bytes // (1024*1024)} MB limit. Download in smaller batches."
                ),
                "total_bytes": total_bytes,
                "max_bytes": max_bytes,
                "image_count": len(images),
            },
        )
    if len(images) > settings.bulk_download_max_images:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail={
                "code": "TOO_MANY_IMAGES",
                "message": f"Cannot bulk-download more than {settings.bulk_download_max_images} images at once.",
                "image_count": len(images),
                "max_images": settings.bulk_download_max_images,
            },
        )

    def generate_zip():
        data_queue = queue.Queue(maxsize=32)

        class QueueWriter:
            def write(self, data):
                data_queue.put(data)
                return len(data)
            def flush(self):
                pass
            def close(self):
                data_queue.put(None)

        writer = QueueWriter()

        def zip_worker():
            try:
                with zipfile.ZipFile(writer, 'w', zipfile.ZIP_STORED) as zf:
                    for image in images:
                        try:
                            photo_bytes = storage_service.get_photo(event_uuid, image.id, "original")
                            filename = safe_zip_filename(image.filename, f"photo_{image.id}.jpg")
                            zf.writestr(filename, photo_bytes)
                        except Exception as e:
                            logger.error(f"Failed to add image {image.id} to ZIP: {e}")
                            continue
            finally:
                writer.close()

        thread = threading.Thread(target=zip_worker, daemon=True)
        thread.start()

        while True:
            chunk = data_queue.get()
            if chunk is None:
                break
            yield chunk

        thread.join(timeout=5)

    return StreamingResponse(
        generate_zip(),
        media_type="application/zip",
        headers={"Content-Disposition": attachment_content_disposition(f"{event.name}_photos.zip", "photos.zip")}
    )


@router.post("/{event_id}/photos/download-all-zip")
async def admin_download_all_zip(
    event_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Download ALL photos for an event as a ZIP file (admin)."""
    try:
        event_uuid = uuid.UUID(event_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid event ID")

    event = db.query(Event).filter(Event.id == event_uuid).first()
    if not event:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")
    if not current_user.is_superadmin and event.owner_user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized")

    images = db.query(Image).filter(Image.event_id == event_uuid).all()
    if not images:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No photos found")

    # Pre-flight size check using stored size_bytes. Without this, a large
    # event could tie up MinIO + a worker for many minutes streaming a
    # multi-GB ZIP. Same caps as guest bulk download.
    total_bytes = sum((img.size_bytes or 0) for img in images)
    max_bytes = settings.bulk_download_max_bytes
    if total_bytes > max_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail={
                "code": "DOWNLOAD_TOO_LARGE",
                "message": (
                    f"Total download size {total_bytes // (1024*1024)} MB exceeds "
                    f"{max_bytes // (1024*1024)} MB limit. Use the photos page to download in batches."
                ),
                "total_bytes": total_bytes,
                "max_bytes": max_bytes,
                "image_count": len(images),
            },
        )
    if len(images) > settings.bulk_download_max_images:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail={
                "code": "TOO_MANY_IMAGES",
                "message": f"Cannot bulk-download more than {settings.bulk_download_max_images} images at once.",
                "image_count": len(images),
                "max_images": settings.bulk_download_max_images,
            },
        )

    def generate_zip():
        data_queue = queue.Queue(maxsize=32)

        class QueueWriter:
            def write(self, data):
                data_queue.put(data)
                return len(data)
            def flush(self):
                pass
            def close(self):
                data_queue.put(None)

        writer = QueueWriter()

        def zip_worker():
            try:
                with zipfile.ZipFile(writer, 'w', zipfile.ZIP_STORED) as zf:
                    for image in images:
                        try:
                            photo_bytes = storage_service.get_photo(event_uuid, image.id, "original")
                            filename = safe_zip_filename(image.filename, f"photo_{image.id}.jpg")
                            zf.writestr(filename, photo_bytes)
                        except Exception as e:
                            logger.error(f"Failed to add image {image.id} to ZIP: {e}")
                            continue
            finally:
                writer.close()

        thread = threading.Thread(target=zip_worker, daemon=True)
        thread.start()

        while True:
            chunk = data_queue.get()
            if chunk is None:
                break
            yield chunk

        thread.join(timeout=5)

    return StreamingResponse(
        generate_zip(),
        media_type="application/zip",
        headers={"Content-Disposition": attachment_content_disposition(f"{event.name}_all_photos.zip", "all_photos.zip")}
    )


@router.post("/{event_id}/reindex", response_model=ReindexResponse)
async def reindex_event(
    event_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Reindex all photos in an Event
    
    - **event_id**: UUID of the event
    
    Resets all image statuses to 'pending' and queues them for reprocessing.
    Requires ownership validation.
    """
    # Parse event_id
    try:
        event_uuid = uuid.UUID(event_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid event ID format"
        )
    
    # Query event and validate ownership
    event = db.query(Event).filter(Event.id == event_uuid).first()
    
    if not event:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Event not found"
        )
    
    # Validate ownership (superadmin bypasses)
    if not current_user.is_superadmin and event.owner_user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to reindex this event"
        )

    ensure_event_mutable(event, current_user)

    # Get all images for this event
    images = db.query(Image).filter(Image.event_id == event_uuid).all()

    # Delete old CompreFace subjects BEFORE re-registering to avoid duplicates
    old_faces = db.query(Face).filter(Face.event_id == event_uuid).all()
    if old_faces and settings.compreface_api_key:
        deleted_cf = 0
        for face in old_faces:
            if face.compreface_subject_id:
                try:
                    resp = httpx.delete(
                        f"{get_compreface_url()}/api/v1/recognition/faces",
                        headers={"x-api-key": settings.compreface_api_key},
                        params={"subject": face.compreface_subject_id},
                        timeout=10.0,
                    )
                    if resp.status_code in (200, 404):
                        deleted_cf += 1
                except Exception as e:
                    logger.warning(f"Failed to delete CompreFace subject {face.compreface_subject_id}: {e}")
        logger.info(f"Cleaned {deleted_cf}/{len(old_faces)} CompreFace subjects for event {event_uuid}")

    # Reset all image statuses to pending
    for image in images:
        image.status = 'pending'
        image.face_count = 0
        image.indexed_at = None

    # Delete all existing face records for this event
    db.query(Face).filter(Face.event_id == event_uuid).delete()

    db.commit()
    
    # Queue all images for reprocessing
    queued_count = 0
    for image in images:
        try:
            enqueue_face_indexing(str(image.id))
            queued_count += 1
        except Exception as e:
            # Log error but continue queuing other images
            logger.error(f"Failed to queue image {image.id} for reindexing: {e}")
    
    # Log reindex action
    log_action(
        db=db,
        event_id=event_uuid,
        actor_type='admin',
        actor_id=current_user.id,
        action='reindex',
        metadata={'queued_count': queued_count}
    )
    
    return ReindexResponse(
        message="Reindexing started",
        queued_count=queued_count
    )


@router.get("/{event_id}/logs", response_model=AuditLogListResponse)
async def get_audit_logs(
    event_id: str,
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    action: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get audit logs for an Event with pagination and filtering
    
    - **event_id**: UUID of the event
    - **page**: Page number (default: 1)
    - **limit**: Items per page (default: 50)
    - **action**: Filter by action type (optional)
    
    Returns paginated list of audit logs
    Requires ownership validation
    """
    # Parse event_id
    try:
        event_uuid = uuid.UUID(event_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid event ID format"
        )
    
    # Query event and validate ownership
    event = db.query(Event).filter(Event.id == event_uuid).first()
    
    if not event:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Event not found"
        )
    
    # Validate ownership (superadmin bypasses)
    if not current_user.is_superadmin and event.owner_user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to access logs for this event"
        )

    # Build query
    query = db.query(AuditLog).filter(AuditLog.event_id == event_uuid)
    
    # Apply action filter if provided
    if action:
        query = query.filter(AuditLog.action == action)
    
    # Get total count
    total = query.count()
    
    # Apply pagination
    offset = (page - 1) * limit
    logs = query.order_by(AuditLog.timestamp.desc()).offset(offset).limit(limit).all()
    
    # Build response
    log_list = []
    for log in logs:
        log_list.append(AuditLogItem(
            log_id=str(log.id),
            event_id=str(log.event_id),
            actor_type=log.actor_type,
            action=log.action,
            metadata=log.metadata_ or {},
            timestamp=log.timestamp
        ))
    
    return AuditLogListResponse(
        logs=log_list,
        total=total,
        page=page,
        limit=limit
    )


class EventDeleteResponse(BaseModel):
    message: str
    event_id: str


@router.delete("/{event_id}", response_model=EventDeleteResponse)
async def delete_event(
    event_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Delete an Event and all associated data
    
    - **event_id**: UUID of the event
    
    Deletes:
    - All images from MinIO (originals and thumbnails)
    - All database records (images, faces, sessions, audit logs) via cascade
    
    Requires ownership validation
    """
    # Parse event_id
    try:
        event_uuid = uuid.UUID(event_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid event ID format"
        )
    
    # Query event and validate ownership
    event = db.query(Event).filter(Event.id == event_uuid).first()
    
    if not event:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Event not found"
        )
    
    # Validate ownership (superadmin bypasses)
    if not current_user.is_superadmin and event.owner_user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to delete this event"
        )

    # Log event deletion before deleting (audit log will be deleted with cascade)
    log_action(
        db=db,
        event_id=event_uuid,
        actor_type='admin',
        actor_id=current_user.id,
        action='delete_event',
        metadata={
            'event_name': event.name,
            'photo_count': db.query(func.count(Image.id)).filter(Image.event_id == event_uuid).scalar() or 0
        }
    )
    
    # Drop CompreFace subjects before the DB cascade nukes face rows.
    try:
        delete_compreface_subjects_for_event(db, event_uuid)
    except Exception as e:
        logger.error(f"CompreFace cleanup failed for event {event_uuid}: {e}")

    # Delete all photos from MinIO
    try:
        storage_service.delete_event_photos(event_uuid)
    except Exception as e:
        # Log error but continue with database deletion
        logger.error(f"Failed to delete photos from MinIO for event {event_uuid}: {e}")

    # Invalidate caches
    slug = event.slug
    cache_delete_pattern(f"event_info:{slug}")
    cache_delete_pattern(f"gallery:{event_uuid}:*")
    cache_delete_pattern(f"share:{event_uuid}:*")

    # Delete event from database (cascades to images, faces, sessions, audit logs)
    db.delete(event)
    db.commit()

    return EventDeleteResponse(
        message="Event deleted successfully",
        event_id=str(event_uuid)
    )


@router.get("/{event_id}/analytics")
async def get_event_analytics(
    event_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get analytics for an event based on audit log data.

    Returns scan counts, unique guests, download counts, activity by day/hour.
    """
    try:
        event_uuid = uuid.UUID(event_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid event ID format")

    event = db.query(Event).filter(Event.id == event_uuid).first()
    if not event:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")
    if not current_user.is_superadmin and event.owner_user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized")

    # Total scans
    total_scans = db.query(func.count(AuditLog.id)).filter(
        AuditLog.event_id == event_uuid, AuditLog.action == 'scan'
    ).scalar() or 0

    # Unique guests (distinct actor_id where actor_type='guest')
    unique_guests = db.query(func.count(func.distinct(AuditLog.actor_id))).filter(
        AuditLog.event_id == event_uuid, AuditLog.actor_type == 'guest'
    ).scalar() or 0

    # Total downloads
    total_downloads = db.query(func.count(AuditLog.id)).filter(
        AuditLog.event_id == event_uuid, AuditLog.action == 'bulk_download'
    ).scalar() or 0

    # Total gallery views
    total_gallery_views = db.query(func.count(AuditLog.id)).filter(
        AuditLog.event_id == event_uuid, AuditLog.action == 'gallery_view'
    ).scalar() or 0

    # Scans by day (last 30 days)
    scans_by_day = db.query(
        func.date_trunc('day', AuditLog.timestamp).label('date'),
        func.count(AuditLog.id).label('count')
    ).filter(
        AuditLog.event_id == event_uuid,
        AuditLog.action == 'scan'
    ).group_by(
        func.date_trunc('day', AuditLog.timestamp)
    ).order_by(
        func.date_trunc('day', AuditLog.timestamp)
    ).limit(30).all()

    # Peak hours
    peak_hours = db.query(
        func.extract('hour', AuditLog.timestamp).label('hour'),
        func.count(AuditLog.id).label('count')
    ).filter(
        AuditLog.event_id == event_uuid,
        AuditLog.actor_type == 'guest'
    ).group_by(
        func.extract('hour', AuditLog.timestamp)
    ).order_by(
        func.extract('hour', AuditLog.timestamp)
    ).all()

    # Recent activity (last 10)
    recent = db.query(AuditLog).filter(
        AuditLog.event_id == event_uuid
    ).order_by(AuditLog.timestamp.desc()).limit(10).all()

    return {
        "total_scans": total_scans,
        "unique_guests": unique_guests,
        "total_downloads": total_downloads,
        "total_gallery_views": total_gallery_views,
        "scans_by_day": [
            {"date": row.date.isoformat() if row.date else None, "count": row.count}
            for row in scans_by_day
        ],
        "peak_hours": [
            {"hour": int(row.hour), "count": row.count}
            for row in peak_hours
        ],
        "recent_activity": [
            {
                "id": str(log.id),
                "action": log.action,
                "actor_type": log.actor_type,
                "timestamp": log.timestamp.isoformat(),
                "metadata": log.metadata_
            }
            for log in recent
        ]
    }
