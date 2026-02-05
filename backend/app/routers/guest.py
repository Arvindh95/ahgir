from datetime import datetime, timedelta
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import text
from pydantic import BaseModel
import uuid
import base64
import logging

from app.auth import verify_password, create_event_token, get_event_from_token, EventTokenPayload
from app.database import get_db
from app.models import Event, GuestSession, Face, Image
from app.face_detection import face_detector
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

    Uses CompreFace for recognition when available, falls back to InsightFace.

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

    # Try CompreFace first if configured
    if settings.compreface_api_key:
        logger.info("Using CompreFace for face recognition")
        return await _scan_with_compreface(
            image_bytes, event_id, session_id, event, db
        )

    # Fall back to InsightFace
    logger.info("Using InsightFace for face recognition (CompreFace not configured)")
    
    # Detect face and compute embedding
    try:
        # Use 'small' config for selfies - very lenient detection
        faces = face_detector.detect_faces(image_bytes, config_name='small')
        logger.info(f"First detection attempt: {len(faces)} faces found")

        if len(faces) == 0:
            # Try again with extremely low threshold for difficult webcam images
            faces = face_detector.detect_faces(
                image_bytes,
                min_face_size=15,
                det_threshold=0.05  # Very low threshold
            )
            logger.info(f"Second detection attempt (low threshold): {len(faces)} faces found")

        if len(faces) == 0:
            # No face detected in the scan image
            logger.warning("No face detected in selfie after multiple attempts")
            return FaceScanResponse(
                matches=[],
                scan_id=str(uuid.uuid4()),
                total_matches=0
            )
        
        # Use the first detected face
        query_embedding, _, _ = faces[0]
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Face detection failed: {str(e)}"
        )
    
    # Perform vector similarity search using pgvector
    # Very low threshold to see all potential matches
    similarity_threshold = 0.2

    # Convert embedding to list for SQL query
    embedding_list = query_embedding.tolist()

    logger.info(f"Searching for faces in event {event_id} with threshold {similarity_threshold}")
    logger.info(f"Query embedding length: {len(embedding_list)}")

    # Debug: Show top similarities without threshold filter
    debug_query = text("""
        SELECT
            f.id as face_id,
            1 - (f.embedding <=> CAST(:query_embedding AS vector)) as similarity
        FROM faces f
        JOIN images i ON f.image_id = i.id
        WHERE i.event_id = :event_id
            AND i.status = 'indexed'
        ORDER BY similarity DESC
        LIMIT 5
    """)
    debug_result = db.execute(
        debug_query,
        {
            "query_embedding": str(embedding_list),
            "event_id": str(event_id)
        }
    )
    for row in debug_result:
        logger.info(f"DEBUG - Face {row.face_id}: similarity = {row.similarity:.4f}")

    # Query faces table using pgvector cosine similarity
    # The <=> operator computes cosine distance, so 1 - distance = similarity
    # Use CAST() instead of :: to avoid SQLAlchemy parameter parsing issues
    query = text("""
        SELECT
            f.id as face_id,
            f.image_id,
            f.bbox,
            1 - (f.embedding <=> CAST(:query_embedding AS vector)) as similarity
        FROM faces f
        JOIN images i ON f.image_id = i.id
        WHERE i.event_id = :event_id
            AND i.status = 'indexed'
            AND 1 - (f.embedding <=> CAST(:query_embedding AS vector)) > :threshold
        ORDER BY similarity DESC
        LIMIT 50
    """)

    result = db.execute(
        query,
        {
            "query_embedding": str(embedding_list),
            "event_id": str(event_id),
            "threshold": similarity_threshold
        }
    )

    # Process results (presigned URLs will be added in next subtask)
    matches = []
    for row in result:
        matches.append({
            "image_id": str(row.image_id),
            "similarity": float(row.similarity),
            "face_bbox": row.bbox
        })

    logger.info(f"Found {len(matches)} matches above threshold {similarity_threshold}")
    
    scan_id = str(uuid.uuid4())
    
    # Generate presigned URLs for matched photos
    face_matches = []
    for match in matches:
        image_id = uuid.UUID(match["image_id"])
        
        # Generate presigned URLs with 15 minute expiry
        try:
            thumbnail_url = storage_service.generate_presigned_url(
                event_id=event_id,
                image_id=image_id,
                photo_type="thumb",
                expiry_minutes=15,
                db=db,
                validate_event=True
            )
            
            original_url = storage_service.generate_presigned_url(
                event_id=event_id,
                image_id=image_id,
                photo_type="original",
                expiry_minutes=15,
                db=db,
                validate_event=True
            )
            
            # Add download URL only if allow_downloads is enabled
            download_url = None
            if event.allow_downloads:
                download_url = original_url  # Same as original URL
            
            face_matches.append(FaceMatch(
                image_id=match["image_id"],
                similarity=match["similarity"],
                thumbnail_url=thumbnail_url,
                original_url=original_url,
                download_url=download_url,
                face_bbox=match["face_bbox"]
            ))
            
        except Exception as e:
            # Skip this match if URL generation fails
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
            'similarity_avg': sum(m.similarity for m in face_matches) / len(face_matches) if face_matches else 0
        }
    )
    
    return FaceScanResponse(
        matches=face_matches,
        scan_id=scan_id,
        total_matches=len(face_matches)
    )


