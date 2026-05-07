from datetime import datetime, timedelta
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import text, func
from pydantic import BaseModel
import uuid
import base64
import hashlib
import logging
from app.utils.filename import attachment_content_disposition, safe_zip_filename
import zipfile
import queue
import threading
from io import BytesIO

from app.auth import verify_password, create_event_token, get_event_from_token, EventTokenPayload
from app.database import get_db
from app.models import Event, GuestSession, Face, Image
from app.storage import storage_service, generate_signed_cover_url
from app.rate_limiter import rate_limiter, auth_rate_limiter, share_rate_limiter, event_passcode_rate_limiter
from app.audit import log_action
from app.config import settings, get_compreface_url
from app.cache import cache_get, cache_set
import httpx
import asyncio

logger = logging.getLogger(__name__)


async def recognize_with_compreface(image_bytes: bytes, api_key: str, det_prob_threshold: float = 0.5) -> list:
    """Recognize faces using CompreFace API."""
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            files = {"file": ("image.jpg", image_bytes, "image/jpeg")}
            params = {
                "det_prob_threshold": det_prob_threshold,
                "prediction_count": 500,
            }
            headers = {"x-api-key": api_key}

            response = await client.post(
                f"{get_compreface_url()}/api/v1/recognition/recognize",
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
    # Check cache first
    cache_key = f"event_info:{slug}"
    cached = cache_get(cache_key)
    if cached:
        return EventInfoResponse(**cached)

    # Find event by slug
    event = db.query(Event).filter(Event.slug == slug).first()

    # Treat frozen/expired events as not-found from a guest's perspective.
    # Frozen means the photographer is on a tier that no longer covers this
    # event slot — public access to it must stop, just like uploads/reindex.
    if not event or event.status != 'active':
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Event not found"
        )

    cover_image_url = None
    if event.cover_image:
        cover_image_url = generate_signed_cover_url(event.id)

    result = EventInfoResponse(
        event_id=str(event.id),
        name=event.name,
        date=event.date.isoformat() if event.date else None,
        requires_passcode=event.passcode_hash is not None,
        location=event.location,
        description=event.description,
        cover_image_url=cover_image_url
    )
    cache_set(cache_key, result.model_dump(), ttl_seconds=300)
    return result

@router.post("/e/{slug}/auth", response_model=EventTokenResponse)
async def authenticate_guest(
    slug: str,
    passcode_data: PasscodeRequest,
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Authenticate a guest for an event

    - **slug**: Unique event slug
    - **passcode**: Event passcode (required if event has passcode)

    Returns an Event_Token scoped to the event
    """
    client_ip = request.client.host if request.client else "unknown"
    auth_rate_limiter.enforce_rate_limit(client_ip, action="guest_auth")
    # Per-event passcode limiter: caps guesses per slug regardless of source IP, so a
    # rotating-IP attacker cannot brute-force a weak passcode.
    event_passcode_rate_limiter.enforce_rate_limit(slug, action="event_passcode")

    # Find event by slug
    event = db.query(Event).filter(Event.slug == slug).first()

    if not event or event.status != 'active':
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
    
    # Store session in database. We persist a SHA-256 of the JWT — never
    # the raw token. Validation is by session_id (PK), so the field exists
    # only to satisfy the legacy NOT NULL+UNIQUE constraint without giving
    # a DB leak the bearer credential it needs to impersonate guests.
    token_hash = hashlib.sha256(event_token.encode("utf-8")).hexdigest()
    guest_session = GuestSession(
        id=session_id,
        event_id=event.id,
        session_token=token_hash,
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
    image: str  # Base64 encoded image (primary frame)
    additional_frames: Optional[List[str]] = None  # Extra frames for multi-angle scan


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


def _guest_photo_urls(event_id: uuid.UUID, image_id: uuid.UUID, allow_downloads: bool) -> tuple[str, str, Optional[str]]:
    """Return guest-safe URLs: original bytes are only signed when downloads are enabled."""
    thumbnail_url = storage_service.generate_url(
        event_id=event_id, image_id=image_id, photo_type="thumb"
    )
    if not allow_downloads:
        return thumbnail_url, thumbnail_url, None

    original_url = storage_service.generate_url(
        event_id=event_id, image_id=image_id, photo_type="original"
    )
    return thumbnail_url, original_url, original_url


def _scrub_gallery_payload(payload: dict) -> dict:
    """Protect legacy cached gallery payloads that may contain original URLs."""
    if payload.get("allow_downloads") is not False:
        return payload
    scrubbed = dict(payload)
    scrubbed["photos"] = []
    for photo in payload.get("photos", []):
        safe_photo = dict(photo)
        safe_photo["download_url"] = None
        if safe_photo.get("thumbnail_url"):
            safe_photo["original_url"] = safe_photo["thumbnail_url"]
        scrubbed["photos"].append(safe_photo)
    return scrubbed


async def _recognize_single_frame(image_bytes: bytes, api_key: str) -> list:
    """Recognize faces in a single frame, using largest face only."""
    results = await recognize_with_compreface(image_bytes, api_key, det_prob_threshold=0.5)
    if not results:
        results = await recognize_with_compreface(image_bytes, api_key, det_prob_threshold=0.3)
    if not results:
        return []

    # Only use the LARGEST detected face to avoid matching background people
    if len(results) > 1:
        def _face_area(fr):
            box = fr.get("box", {})
            w = box.get("x_max", 0) - box.get("x_min", 0)
            h = box.get("y_max", 0) - box.get("y_min", 0)
            return w * h
        results = [max(results, key=_face_area)]
        logger.info("Multiple faces in frame, using largest only")

    return results


async def _scan_with_compreface(
    all_frames: List[bytes],
    event_id: uuid.UUID,
    session_id: uuid.UUID,
    event: Event,
    db: Session
) -> FaceScanResponse:
    """Perform face scan using CompreFace, processing multiple frames in parallel."""
    api_key = settings.compreface_api_key

    # Process all frames in parallel
    frame_tasks = [_recognize_single_frame(frame, api_key) for frame in all_frames]
    frame_results = await asyncio.gather(*frame_tasks)

    logger.info(f"Multi-scan: processed {len(all_frames)} frames, "
                f"faces found in {sum(1 for r in frame_results if r)} frames")

    # Collect all subjects across all frames, keeping highest similarity per image
    # key: image_id -> {similarity, subject_id, face_bbox}
    best_matches: dict = {}
    similarity_threshold = settings.face_similarity_threshold

    for recognition_results in frame_results:
        for face_result in recognition_results:
            subjects = face_result.get("subjects", [])
            for subject in subjects:
                subject_id = subject.get("subject", "")
                similarity = subject.get("similarity", 0)

                if similarity < similarity_threshold:
                    continue

                parts = subject_id.split("/")
                if len(parts) >= 2:
                    result_event_id = parts[0]
                    result_image_id = parts[1]

                    if result_event_id != str(event_id):
                        continue

                    # Keep highest similarity per image across all frames
                    existing = best_matches.get(result_image_id)
                    if existing is None or similarity > existing["similarity"]:
                        best_matches[result_image_id] = {
                            "image_id": result_image_id,
                            "similarity": similarity,
                            "subject_id": subject_id,
                        }

    if not best_matches:
        logger.warning("No matching faces found across all frames")
        return FaceScanResponse(
            matches=[],
            scan_id=str(uuid.uuid4()),
            total_matches=0
        )

    # Verify images exist and get bboxes
    matches = []
    for match_data in best_matches.values():
        result_image_id = match_data["image_id"]
        image_exists = db.query(Image.id).filter(
            Image.id == uuid.UUID(result_image_id),
            Image.event_id == event_id
        ).first()
        if not image_exists:
            continue

        face = db.query(Face).filter(
            Face.compreface_subject_id == match_data["subject_id"]
        ).first()
        bbox = face.bbox if face else [0, 0, 0, 0]

        matches.append({
            "image_id": result_image_id,
            "similarity": match_data["similarity"],
            "face_bbox": bbox
        })

    logger.info(f"Found {len(matches)} matches from {len(all_frames)} frames")

    scan_id = str(uuid.uuid4())

    # Generate URLs for matched photos
    face_matches = []
    for match in matches:
        image_uuid = uuid.UUID(match["image_id"])
        try:
            thumbnail_url, original_url, download_url = _guest_photo_urls(
                event_id, image_uuid, event.allow_downloads
            )

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
            'frame_count': len(all_frames),
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

    # Decode base64 images (handle data URL format) with per-frame size cap.
    # Without this cap a guest can send arbitrarily large base64 strings and
    # exhaust memory or saturate the CompreFace upstream — Caddyfile.prod has
    # no body cap, and direct backend access in dev also bypasses any proxy.
    max_b64 = settings.max_scan_frame_bytes * 4 // 3 + 16  # base64 inflation factor
    max_total = settings.max_scan_total_bytes

    def _decode_frame(data: str) -> bytes:
        if not isinstance(data, str):
            raise ValueError("frame must be a string")
        if len(data) > max_b64:
            raise ValueError(f"frame exceeds {settings.max_scan_frame_bytes} bytes")
        if data.startswith('data:'):
            comma = data.find(',')
            if comma == -1:
                raise ValueError("invalid data URL")
            data = data[comma + 1:]
        decoded = base64.b64decode(data, validate=False)
        if len(decoded) > settings.max_scan_frame_bytes:
            raise ValueError(f"frame exceeds {settings.max_scan_frame_bytes} bytes")
        return decoded

    try:
        all_frames = [_decode_frame(scan_request.image)]
        running_total = len(all_frames[0])
        if scan_request.additional_frames:
            for frame_data in scan_request.additional_frames[:4]:  # Max 5 total frames
                try:
                    decoded = _decode_frame(frame_data)
                except Exception:
                    continue  # Skip invalid frames
                if running_total + len(decoded) > max_total:
                    logger.warning("Scan request truncated: total frame size exceeds cap")
                    break
                all_frames.append(decoded)
                running_total += len(decoded)
        logger.info(f"Received {len(all_frames)} scan frames, {running_total} bytes")
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to decode image: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid base64 image data"
        )

    # Use CompreFace for face recognition (multi-frame)
    return await _scan_with_compreface(
        all_frames, event_id, session_id, event, db
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

    # Pre-validate total size from DB to reject before streaming
    max_bytes = settings.bulk_download_max_bytes
    total_size = sum(img.size_bytes or 0 for img in images)
    if total_size > max_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Total download size exceeds {max_bytes // (1024 * 1024)} MB limit. Please select fewer images."
        )

    # Audit log
    log_action(
        db=db,
        event_id=event_id,
        actor_type='guest',
        actor_id=session_id,
        action='bulk_download',
        metadata={'image_count': len(images)}
    )

    # Stream ZIP without buffering everything in memory
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
                            photo_bytes = storage_service.get_photo(event_id, image.id, "original")
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

    # NOTE: allow_downloads is immutable today (no PATCH endpoint touches it). If a
    # future endpoint adds a toggle, it MUST cache_delete_pattern(f"gallery:{event_id}:*")
    # to avoid stale download_url in cached payloads.
    cache_key = f"gallery:{event_token.event_id}:p{page}:l{limit}"
    cached = cache_get(cache_key)
    if cached:
        if page == 1:
            event = db.query(Event).filter(Event.id == event_id).first()
            if event:
                log_action(db=db, event_id=event_id, actor_type='guest',
                           actor_id=session_id, action='gallery_view',
                           metadata={'total_photos': cached.get('total', 0)})
        return GalleryResponse(**_scrub_gallery_payload(cached))

    # Verify event exists (cache miss path)
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

    # Generate URLs (ownership verified by event_id filter in query above)
    photos = []
    for image in images:
        try:
            thumbnail_url, original_url, download_url = _guest_photo_urls(
                event_id, image.id, event.allow_downloads
            )

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

    result = GalleryResponse(
        photos=photos,
        total=total,
        page=page,
        limit=limit,
        event_name=event.name,
        allow_downloads=event.allow_downloads
    )
    cache_set(cache_key, result.model_dump(), ttl_seconds=120)
    return result


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
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Get photo share info for OG meta tags (public, no auth required).

    Returns event name, photo URLs, and event slug for the share page.
    """
    client_ip = request.client.host if request.client else "unknown"
    share_rate_limiter.enforce_rate_limit(client_ip, action="share")

    try:
        event_uuid = uuid.UUID(event_id)
        image_uuid = uuid.UUID(image_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid ID format")

    # Cache-first. Status/delete/freeze paths all call cache_delete_pattern so
    # a stale payload only persists if those invalidation paths regress; the
    # 60s TTL caps the blast radius. Skipping the DB on the hot path keeps
    # crawlers and OG previews cheap.
    # Use the canonical lowercase UUID form so any-case URLs hit the same
    # cache key as the writer-side `str(uuid)` form used for invalidation.
    cache_key = f"share:{event_uuid}:{image_uuid}"
    cached = cache_get(cache_key)
    if cached:
        return ShareInfoResponse(**cached)

    # Verify image and event (and that the event is still serving guests).
    event = db.query(Event).filter(Event.id == event_uuid).first()
    if not event or event.status != 'active':
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")

    image = db.query(Image.id).filter(Image.id == image_uuid, Image.event_id == event_uuid).first()
    if not image:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Photo not found")

    thumbnail_url, image_url, _download_url = _guest_photo_urls(
        event_uuid, image_uuid, event.allow_downloads
    )

    result = ShareInfoResponse(
        event_name=event.name,
        image_url=image_url,
        thumbnail_url=thumbnail_url,
        event_slug=event.slug
    )
    cache_set(cache_key, result.model_dump(), ttl_seconds=60)
    return result


