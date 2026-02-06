from datetime import datetime, timedelta
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import text, func
from pydantic import BaseModel
import uuid
import base64
import logging
import zipfile
from io import BytesIO

from app.auth import verify_password, create_event_token, get_event_from_token, EventTokenPayload
from app.database import get_db
from app.models import Event, GuestSession, Face, Image
from app.storage import storage_service
from app.rate_limiter import rate_limiter
from app.audit import log_action
from app.config import settings
import httpx

logger = logging.getLogger(__name__)


async def recognize_with_compreface(image_bytes: bytes, api_key: str, det_prob_threshold: float = 0.5) -> list:
    """Recognize faces using CompreFace API."""
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            files = {"file": ("image.jpg", image_bytes, "image/jpeg")}
            params = {
                "det_prob_threshold": det_prob_threshold,
                "prediction_count": 100,
            }
            headers = {"x-api-key": api_key}

            response = await client.post(
                f"{settings.compreface_api_url}/api/v1/recognition/recognize",
                headers=headers,
                files=files,
                params=params,
            )

            if response.status_code == 200:
                result = response.json()
                return result.get("result", [])
            else:
                logger.error(f"CompreFace recognition failed: {response.status_code} - {response.text}")
                return []

    except Exception as e:
        logger.error(f"Error calling CompreFace: {e}")
        return []

router = APIRouter(tags=["guest"])

# Pydantic models
class EventInfoResponse(BaseModel):
    event_id: str
    name: str
    date: Optional[str] = None
    requires_passcode: bool
    location: Optional[str] = None
    description: Optional[str] = None
    cover_image_url: Optional[str] = None

class PasscodeRequest(BaseModel):
    passcode: str = None

class EventTokenResponse(BaseModel):
    event_token: str
    event_id: str
    event_name: str
    allow_downloads: bool
    expires_in: int

@router.get("/e/{slug}", response_model=EventInfoResponse)
async def get_event_by_slug(slug: str, db: Session = Depends(get_db)):
    """
    Retrieve Event information by slug
    
    - **slug**: Unique event slug
    
    Returns event information including whether a passcode is required
    """
    # Find event by slug
    event = db.query(Event).filter(Event.slug == slug).first()
    
    if not event:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Event not found"
        )
    
    cover_image_url = None
    if event.cover_image:
        from app.config import settings as _settings
        _protocol = "https" if _settings.minio_external_secure else "http"
        cover_image_url = f"{_protocol}://{_settings.minio_external_endpoint}/{_settings.minio_bucket}/{event.cover_image}"

    return EventInfoResponse(
        event_id=str(event.id),
        name=event.name,
        date=event.date.isoformat() if event.date else None,
        requires_passcode=event.passcode_hash is not None,
        location=event.location,
        description=event.description,
        cover_image_url=cover_image_url
    )

@router.post("/e/{slug}/auth", response_model=EventTokenResponse)
async def authenticate_guest(
    slug: str,
    passcode_data: PasscodeRequest,
    db: Session = Depends(get_db)
):
    """
    Authenticate a guest for an event
    
    - **slug**: Unique event slug
    - **passcode**: Event passcode (required if event has passcode)
    
    Returns an Event_Token scoped to the event
    """
    # Find event by slug
    event = db.query(Event).filter(Event.slug == slug).first()
    
    if not event:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Event not found"
        )
    
    # Verify passcode if required
    if event.passcode_hash:
        if not passcode_data.passcode:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Passcode required"
            )
        
        if not verify_password(passcode_data.passcode, event.passcode_hash):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid passcode"
            )
    
    # Create guest session
    session_id = uuid.uuid4()
    expires_at = datetime.utcnow() + timedelta(hours=1)
    
    # Generate event token
    event_token = create_event_token(event.id, session_id)
    
    # Store session in database
    guest_session = GuestSession(
        id=session_id,
        event_id=event.id,
        session_token=event_token,
        expires_at=expires_at
    )
    
    db.add(guest_session)
    db.commit()
    
    # Log guest access
    log_action(
        db=db,
        event_id=event.id,
        actor_type='guest',
        actor_id=session_id,
        action='access',
        metadata={'event_slug': slug}
    )
    
    return EventTokenResponse(
        event_token=event_token,
        event_id=str(event.id),
        event_name=event.name,
        allow_downloads=event.allow_downloads,
        expires_in=3600  # 1 hour in seconds
    )


# Face scanning models
class FaceScanRequest(BaseModel):
    image: str  # Base64 encoded image


class FaceMatch(BaseModel):
    image_id: str
    similarity: float
    thumbnail_url: str
    original_url: str
    download_url: Optional[str] = None
    face_bbox: List[float]


class FaceScanResponse(BaseModel):
    matches: List[FaceMatch]
    scan_id: str
    total_matches: int


async def _scan_with_compreface(
    image_bytes: bytes,
    event_id: uuid.UUID,
    session_id: uuid.UUID,
    event: Event,
    db: Session
) -> FaceScanResponse:
    """Internal helper to perform face scan using CompreFace."""
    api_key = settings.compreface_api_key

    # Call CompreFace recognition
    recognition_results = await recognize_with_compreface(image_bytes, api_key, det_prob_threshold=0.5)

    # If no results, try with lower threshold
    if not recognition_results:
        recognition_results = await recognize_with_compreface(image_bytes, api_key, det_prob_threshold=0.3)

    if not recognition_results:
        logger.warning("No face detected by CompreFace")
        return FaceScanResponse(
            matches=[],
            scan_id=str(uuid.uuid4()),
            total_matches=0
        )

    # Process recognition results
    # CompreFace returns subjects in format: event_id/image_id/face_idx
    matches = []
    seen_images = set()

    for face_result in recognition_results:
        subjects = face_result.get("subjects", [])

        for subject in subjects:
            subject_id = subject.get("subject", "")
            similarity = subject.get("similarity", 0)

            # Filter out low similarity matches (false positives)
            # Use threshold from settings, default to 0.6 (60%)
            similarity_threshold = settings.face_similarity_threshold
            if similarity < similarity_threshold:
                logger.debug(f"Skipping match with similarity {similarity:.2f} below threshold {similarity_threshold}")
                continue

            # Parse subject_id: event_id/image_id/face_idx
            parts = subject_id.split("/")
            if len(parts) >= 2:
                result_event_id = parts[0]
                result_image_id = parts[1]

                # Only include results from this event
                if result_event_id == str(event_id) and result_image_id not in seen_images:
                    seen_images.add(result_image_id)

                    # Get face bbox from database
                    face = db.query(Face).filter(
                        Face.compreface_subject_id == subject_id
                    ).first()

                    bbox = face.bbox if face else [0, 0, 0, 0]

                    matches.append({
                        "image_id": result_image_id,
                        "similarity": similarity,
                        "face_bbox": bbox
                    })

    logger.info(f"Found {len(matches)} matches from CompreFace")

    scan_id = str(uuid.uuid4())

    # Generate presigned URLs for matched photos
    face_matches = []
    for match in matches:
        image_uuid = uuid.UUID(match["image_id"])

        try:
            thumbnail_url = storage_service.generate_presigned_url(
                event_id=event_id,
                image_id=image_uuid,
                photo_type="thumb",
                expiry_minutes=15,
                db=db,
                validate_event=True
            )

            original_url = storage_service.generate_presigned_url(
                event_id=event_id,
                image_id=image_uuid,
                photo_type="original",
                expiry_minutes=15,
                db=db,
                validate_event=True
            )

            download_url = None
            if event.allow_downloads:
                download_url = original_url

            face_matches.append(FaceMatch(
                image_id=match["image_id"],
                similarity=match["similarity"],
                thumbnail_url=thumbnail_url,
                original_url=original_url,
                download_url=download_url,
                face_bbox=match["face_bbox"]
            ))

        except Exception as e:
            logger.error(f"Failed to generate URL for image {match['image_id']}: {e}")
            continue

    # Log face scan
    log_action(
        db=db,
        event_id=event_id,
        actor_type='guest',
        actor_id=session_id,
        action='scan',
        metadata={
            'match_count': len(face_matches),
            'similarity_avg': sum(m.similarity for m in face_matches) / len(face_matches) if face_matches else 0,
            'recognition_engine': 'compreface'
        }
    )

    return FaceScanResponse(
        matches=face_matches,
        scan_id=scan_id,
        total_matches=len(face_matches)
    )


@router.post("/scan", response_model=FaceScanResponse)
async def scan_face(
    scan_request: FaceScanRequest,
    event_token: EventTokenPayload = Depends(get_event_from_token),
    db: Session = Depends(get_db)
):
    """
    Scan a guest's face and find matching photos from the event.

    Uses CompreFace for face recognition.

    - **image**: Base64 encoded face image from camera

    Returns matched photos with presigned URLs

    Rate limited to 30 scans per hour per session.
    """
    # Parse event_id from token
    event_id = uuid.UUID(event_token.event_id)
    session_id = uuid.UUID(event_token.session_id)

    # Enforce rate limit
    rate_limiter.enforce_rate_limit(str(session_id), action="scan")

    # Verify event exists
    event = db.query(Event).filter(Event.id == event_id).first()
    if not event:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Event not found"
        )

    # Decode base64 image (handle data URL format)
    try:
        image_data = scan_request.image
        if image_data.startswith('data:'):
            image_data = image_data.split(',')[1]
        image_bytes = base64.b64decode(image_data)
        logger.info(f"Received scan image: {len(image_bytes)} bytes")
    except Exception as e:
        logger.error(f"Failed to decode image: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid base64 image data"
        )

    # Use CompreFace for face recognition
    logger.info("Using CompreFace for face recognition")
    return await _scan_with_compreface(
        image_bytes, event_id, session_id, event, db
    )


# ─── Bulk Download (ZIP) ─────────────────────────────────────────────────────

class BulkDownloadRequest(BaseModel):
    image_ids: List[str]


@router.post("/download-zip")
async def download_zip(
    request: BulkDownloadRequest,
    event_token: EventTokenPayload = Depends(get_event_from_token),
    db: Session = Depends(get_db)
):
    """
    Download multiple photos as a ZIP file.

    - **image_ids**: List of image UUID strings to include

    Returns a ZIP file containing the requested photos.
    Rate limited to 10 downloads per hour per session.
    """
    event_id = uuid.UUID(event_token.event_id)
    session_id = uuid.UUID(event_token.session_id)

    # Enforce rate limit
    rate_limiter.enforce_rate_limit(str(session_id), action="download")

    # Verify event exists and allows downloads
    event = db.query(Event).filter(Event.id == event_id).first()
    if not event:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")
    if not event.allow_downloads:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Downloads are not enabled for this event")

    # Validate image_ids
    if not request.image_ids:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No images specified")

    max_images = settings.bulk_download_max_images
    if len(request.image_ids) > max_images:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Maximum {max_images} images per download"
        )

    # Parse and validate UUIDs
    image_uuids = []
    for img_id in request.image_ids:
        try:
            image_uuids.append(uuid.UUID(img_id))
        except ValueError:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid image ID: {img_id}")

    # Verify all images belong to the event
    images = db.query(Image).filter(Image.event_id == event_id, Image.id.in_(image_uuids)).all()
    if not images:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No valid images found")

    # Create ZIP in memory
    zip_buffer = BytesIO()
    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
        for image in images:
            try:
                photo_bytes = storage_service.get_photo(event_id, image.id, "original")
                filename = image.filename or f"photo_{image.id}.jpg"
                zf.writestr(filename, photo_bytes)
            except Exception as e:
                logger.error(f"Failed to add image {image.id} to ZIP: {e}")
                continue

    zip_buffer.seek(0)

    # Audit log
    log_action(
        db=db,
        event_id=event_id,
        actor_type='guest',
        actor_id=session_id,
        action='bulk_download',
        metadata={'image_count': len(images)}
    )

    safe_name = event.name.replace(' ', '_').replace('"', '')
    return StreamingResponse(
        zip_buffer,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{safe_name}_photos.zip"'}
    )


# ─── Gallery ─────────────────────────────────────────────────────────────────

class GalleryPhoto(BaseModel):
    image_id: str
    thumbnail_url: str
    original_url: str
    download_url: Optional[str] = None
    filename: str
    uploaded_at: str


class GalleryResponse(BaseModel):
    photos: List[GalleryPhoto]
    total: int
    page: int
    limit: int
    event_name: str
    allow_downloads: bool


@router.get("/gallery", response_model=GalleryResponse)
async def get_gallery(
    page: int = Query(1, ge=1),
    limit: int = Query(24, ge=1, le=50),
    event_token: EventTokenPayload = Depends(get_event_from_token),
    db: Session = Depends(get_db)
):
    """
    Browse all indexed event photos with pagination.

    - **page**: Page number (default 1)
    - **limit**: Photos per page (default 24, max 50)

    Returns a paginated list of all event photos.
    """
    event_id = uuid.UUID(event_token.event_id)
    session_id = uuid.UUID(event_token.session_id)

    # Verify event exists
    event = db.query(Event).filter(Event.id == event_id).first()
    if not event:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")

    # Query total count
    total = db.query(func.count(Image.id)).filter(
        Image.event_id == event_id,
        Image.status.in_(['indexed', 'no_faces'])
    ).scalar()

    # Query paginated photos
    offset = (page - 1) * limit
    images = db.query(Image).filter(
        Image.event_id == event_id,
        Image.status.in_(['indexed', 'no_faces'])
    ).order_by(Image.uploaded_at.desc()).offset(offset).limit(limit).all()

    # Generate URLs
    photos = []
    for image in images:
        try:
            thumbnail_url = storage_service.generate_presigned_url(
                event_id=event_id, image_id=image.id, photo_type="thumb",
                expiry_minutes=15, db=db, validate_event=True
            )
            original_url = storage_service.generate_presigned_url(
                event_id=event_id, image_id=image.id, photo_type="original",
                expiry_minutes=15, db=db, validate_event=True
            )
            download_url = original_url if event.allow_downloads else None

            photos.append(GalleryPhoto(
                image_id=str(image.id),
                thumbnail_url=thumbnail_url,
                original_url=original_url,
                download_url=download_url,
                filename=image.filename or f"photo_{image.id}.jpg",
                uploaded_at=image.uploaded_at.isoformat() if image.uploaded_at else ""
            ))
        except Exception as e:
            logger.error(f"Failed to generate URL for gallery image {image.id}: {e}")
            continue

    # Audit log (first page only)
    if page == 1:
        log_action(
            db=db,
            event_id=event_id,
            actor_type='guest',
            actor_id=session_id,
            action='gallery_view',
            metadata={'total_photos': total}
        )

    return GalleryResponse(
        photos=photos,
        total=total,
        page=page,
        limit=limit,
        event_name=event.name,
        allow_downloads=event.allow_downloads
    )


# ─── Share ────────────────────────────────────────────────────────────────────

class ShareInfoResponse(BaseModel):
    event_name: str
    image_url: str
    thumbnail_url: str
    event_slug: str


@router.get("/share/{event_id}/{image_id}", response_model=ShareInfoResponse)
async def get_share_info(
    event_id: str,
    image_id: str,
    db: Session = Depends(get_db)
):
    """
    Get photo share info for OG meta tags (public, no auth required).

    Returns event name, photo URLs, and event slug for the share page.
    """
    try:
        event_uuid = uuid.UUID(event_id)
        image_uuid = uuid.UUID(image_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid ID format")

    # Verify image and event
    image = db.query(Image).filter(Image.id == image_uuid, Image.event_id == event_uuid).first()
    if not image:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Photo not found")

    event = db.query(Event).filter(Event.id == event_uuid).first()
    if not event:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")

    image_url = storage_service.generate_presigned_url(
        event_id=event_uuid, image_id=image_uuid, photo_type="original",
        expiry_minutes=60, db=db, validate_event=False
    )
    thumbnail_url = storage_service.generate_presigned_url(
        event_id=event_uuid, image_id=image_uuid, photo_type="thumb",
        expiry_minutes=60, db=db, validate_event=False
    )

    return ShareInfoResponse(
        event_name=event.name,
        image_url=image_url,
        thumbnail_url=thumbnail_url,
        event_slug=event.slug
    )


