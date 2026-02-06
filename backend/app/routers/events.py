"""
Event management router
"""
from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File
from fastapi.responses import Response
from sqlalchemy.orm import Session
from sqlalchemy import func
from pydantic import BaseModel
import uuid
import qrcode
from io import BytesIO
import secrets
import string
import hashlib
from PIL import Image as PILImage

from app.auth import get_current_user, hash_password
from app.database import get_db
from app.models import User, Event, Image, AuditLog
from app.storage import storage_service
from app.queue import enqueue_face_indexing
from app.audit import log_action
from app.config import settings

router = APIRouter(prefix="/events", tags=["events"])

# Pydantic models
class EventCreate(BaseModel):
    name: str
    date: Optional[str] = None  # ISO date string
    passcode: Optional[str] = None
    location: Optional[str] = None
    description: Optional[str] = None
    allow_downloads: bool = True
    retention_days: int = 90

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
    status: EventStatusResponse
    created_at: datetime

# Helper functions
def generate_slug(name: str, db: Session) -> str:
    """Generate a unique slug for an event"""
    # Create base slug from name
    base_slug = name.lower()
    base_slug = ''.join(c if c.isalnum() or c == ' ' else '' for c in base_slug)
    base_slug = '-'.join(base_slug.split())
    
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
    
    # Generate cover image URL if exists
    cover_image_url = None
    if event.cover_image:
        _protocol = "https" if settings.minio_external_secure else "http"
        cover_image_url = f"{_protocol}://{settings.minio_external_endpoint}/{settings.minio_bucket}/{event.cover_image}"

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
        status=status_info,
        created_at=event.created_at
    )

class EventUpdate(BaseModel):
    slug: Optional[str] = None
    location: Optional[str] = None
    description: Optional[str] = None

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

    # Validate file type
    if not file.content_type or not file.content_type.startswith('image/'):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="File must be an image")

    # Read and process image
    image_bytes = await file.read()
    img = PILImage.open(BytesIO(image_bytes))
    if img.mode in ('RGBA', 'LA', 'P'):
        img = img.convert('RGB')

    # Resize to max 1920px on longest side for cover
    max_size = 1920
    img.thumbnail((max_size, max_size), PILImage.LANCZOS)
    buffer = BytesIO()
    img.save(buffer, format='JPEG', quality=85)
    buffer.seek(0)

    # Upload to MinIO
    object_key = f"events/{event_uuid}/cover.jpg"
    from minio import Minio
    minio_client = Minio(
        settings.minio_endpoint,
        access_key=settings.minio_access_key,
        secret_key=settings.minio_secret_key,
        secure=settings.minio_secure
    )
    minio_client.put_object(
        settings.minio_bucket,
        object_key,
        buffer,
        length=buffer.getbuffer().nbytes,
        content_type="image/jpeg"
    )

    # Update event
    event.cover_image = object_key
    db.commit()

    _protocol = "https" if settings.minio_external_secure else "http"
    cover_url = f"{_protocol}://{settings.minio_external_endpoint}/{settings.minio_bucket}/{object_key}"
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

class PhotoDuplicate(BaseModel):
    filename: str
    reason: str

class PhotoUploadResponse(BaseModel):
    uploaded: List[PhotoUploadResult]
    duplicates: List[PhotoDuplicate]

class PhotoListItem(BaseModel):
    image_id: str
    filename: str
    status: str
    face_count: int
    thumbnail_url: str
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
    """Validate that file is a valid JPEG or PNG image"""
    try:
        img = PILImage.open(BytesIO(file_data))
        # Check format
        if img.format not in ['JPEG', 'PNG']:
            return False
        # Verify it's a valid image by trying to load it
        img.verify()
        return True
    except Exception:
        return False

from app.utils.thumbnail import generate_thumbnail

def extract_exif_data(file_data: bytes) -> dict:
    """Extract EXIF metadata from image"""
    try:
        img = PILImage.open(BytesIO(file_data))
        exif_data = img.getexif()
        
        if not exif_data:
            return {}
        
        # Convert EXIF data to dict with string keys
        exif_dict = {}
        for tag_id, value in exif_data.items():
            # Convert value to string if it's not JSON serializable
            if isinstance(value, (bytes, bytearray)):
                value = str(value)
            exif_dict[str(tag_id)] = value
        
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

    uploaded = []
    duplicates = []
    
    for file in files:
        try:
            # Read file data
            file_data = await file.read()
            
            # Validate image format
            if not validate_image_format(file_data, file.filename):
                duplicates.append(PhotoDuplicate(
                    filename=file.filename,
                    reason="Invalid image format. Only JPEG and PNG are supported."
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
                duplicates.append(PhotoDuplicate(
                    filename=file.filename,
                    reason="File with this name already exists in event"
                ))
                continue
            
            # Get image dimensions
            img = PILImage.open(BytesIO(file_data))
            width, height = img.size
            
            # Extract EXIF data
            exif_data = extract_exif_data(file_data)
            
            # Create image record
            image_id = uuid.uuid4()
            new_image = Image(
                id=image_id,
                event_id=event_uuid,
                filename=file.filename,
                file_hash=file_hash,
                size_bytes=len(file_data),
                width=width,
                height=height,
                exif_data=exif_data,
                status='pending',
                face_count=0
            )
            
            db.add(new_image)
            
            # Store original in MinIO
            storage_service.upload_photo(
                event_id=event_uuid,
                image_id=image_id,
                photo_data=file_data,
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
                    'size_bytes': len(file_data)
                }
            )
            
            # Queue face indexing job
            try:
                enqueue_face_indexing(str(image_id))
            except Exception as e:
                # Log error but don't fail the upload
                print(f"Failed to queue face indexing job for {image_id}: {str(e)}")
            
            uploaded.append(PhotoUploadResult(
                image_id=str(image_id),
                filename=file.filename,
                size_bytes=len(file_data),
                status='pending'
            ))
            
        except Exception as e:
            db.rollback()
            duplicates.append(PhotoDuplicate(
                filename=file.filename,
                reason=f"Upload failed: {str(e)}"
            ))
    
    return PhotoUploadResponse(
        uploaded=uploaded,
        duplicates=duplicates
    )

@router.get("/{event_id}/photos", response_model=PhotoListResponse)
async def list_photos(
    event_id: str,
    page: int = 1,
    limit: int = 50,
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
        
        photo_list.append(PhotoListItem(
            image_id=str(image.id),
            filename=image.filename,
            status=image.status,
            face_count=image.face_count,
            thumbnail_url=thumbnail_url,
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
    
    # Delete from MinIO (both original and thumbnail)
    try:
        storage_service.delete_photo(
            event_id=event_uuid,
            image_id=image_uuid
        )
    except Exception as e:
        # Log error but continue with database deletion
        pass
    
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
    
    return PhotoDeleteResponse(
        message="Photo deleted",
        image_id=str(image_uuid)
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

    # Get all images for this event
    images = db.query(Image).filter(Image.event_id == event_uuid).all()
    
    # Reset all image statuses to pending
    for image in images:
        image.status = 'pending'
        image.face_count = 0
        image.indexed_at = None
    
    # Delete all existing face records for this event
    from app.models import Face
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
            print(f"Failed to queue image {image.id} for reindexing: {str(e)}")
    
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
    page: int = 1,
    limit: int = 50,
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
    
    # Delete all photos from MinIO
    try:
        storage_service.delete_event_photos(event_uuid)
    except Exception as e:
        # Log error but continue with database deletion
        print(f"Failed to delete photos from MinIO for event {event_uuid}: {str(e)}")
    
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
    if event.owner_user_id != current_user.id:
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
