from datetime import datetime, timedelta

from app.utils.time import to_utc_iso
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import text, func
from pydantic import BaseModel, Field
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
from app.rate_limiter import (
    rate_limiter,
    scan_ip_rate_limiter,
    download_ip_rate_limiter,
    auth_rate_limiter,
    share_rate_limiter,
    event_passcode_rate_limiter,
    event_passcode_ip_rate_limiter,
)
from app.audit import log_action
from app.config import settings, get_compreface_url
from app.cache import cache_get, cache_set
import httpx
import asyncio

logger = logging.getLogger(__name__)


class CompreFaceUpstreamError(Exception):
    """CompreFace is unreachable, returning 5xx/auth-failing, or timed out.

    Distinct from a successful response that found no face: an upstream
    error must bubble up so the API returns 502 instead of silently
    pretending the scan succeeded with zero matches.
    """


class NoFaceDetectedError(Exception):
    """CompreFace explicitly reports no usable face in the submitted image."""


async def recognize_with_compreface(
    image_bytes: bytes,
    api_key: str,
    det_prob_threshold: float = 0.5,
    face_plugins: Optional[str] = "gender",
) -> list:
    """Recognize faces using CompreFace API.

    Passes ``face_plugins`` through to CompreFace so each face result
    carries plugin output (``gender``: {value, probability}) that the
    scan handler uses to reject cross-gender false positives.

    Raises:
        NoFaceDetectedError: CompreFace returned 400 (no usable face).
        CompreFaceUpstreamError: auth failure, server error, timeout, or
            network failure. Caller must surface this rather than treat
            it as an empty match list.
    """
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            files = {"file": ("image.jpg", image_bytes, "image/jpeg")}
            params: dict = {
                "det_prob_threshold": det_prob_threshold,
                "prediction_count": 500,
            }
            if face_plugins:
                params["face_plugins"] = face_plugins
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

            # CompreFace reports "no usable face" via 400 with a message
            # body. Treat that as a per-frame no-face signal rather than
            # an upstream outage.
            if response.status_code == 400:
                logger.info(
                    f"CompreFace returned 400 (no face): {response.text[:200]}"
                )
                raise NoFaceDetectedError(response.text[:200] or "no face detected")

            # 401/403 means our API key is bad; 429 means CompreFace itself
            # rate-limited us; 5xx is its problem. All of these are upstream
            # failures the guest can't fix and the caller must raise on.
            logger.error(
                f"CompreFace recognition failed: {response.status_code} - {response.text[:500]}"
            )
            raise CompreFaceUpstreamError(
                f"CompreFace HTTP {response.status_code}"
            )

    except (NoFaceDetectedError, CompreFaceUpstreamError):
        raise
    except (httpx.TimeoutException, httpx.NetworkError, httpx.HTTPError) as e:
        logger.error(f"CompreFace transport error: {e}")
        raise CompreFaceUpstreamError(str(e))
    except Exception as e:
        logger.error(f"Unexpected error calling CompreFace: {e}")
        raise CompreFaceUpstreamError(str(e))

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
    # Cap passcode length at parse time so a huge JSON payload can't
    # reach bcrypt / hash compare. Event passcodes are typed by hand
    # and never long; 256 chars is generous and well below anything
    # that risks DoS on the hash compare. Optional so the auth flow
    # can still 401 with "Passcode required" for events that have one.
    passcode: Optional[str] = Field(default=None, max_length=256)

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

    # Find event by slug
    event = db.query(Event).filter(Event.slug == slug).first()

    if not event or event.status != 'active':
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Event not found"
        )

    # Verify passcode if required. The per-event passcode limiter only counts
    # FAILED attempts on events that actually require a passcode — otherwise a
    # busy no-passcode event or a heavily-trafficked event could legitimately
    # exhaust 10 entries/hour with successful guest auths and lock everyone
    # else out. By moving the enforce call inside the failure branches the
    # budget is consumed only by wrong/missing passcode attempts, which is
    # the threat we actually care about.
    if event.passcode_hash:
        # Two-tier passcode failure throttling:
        #   1. event_passcode_ip_rate_limiter (per slug+client_ip) trips first
        #      when a SINGLE bad actor is brute-forcing. Tight ceiling
        #      protects them from locking other guests out.
        #   2. event_passcode_rate_limiter (per slug) catches rotating-IP
        #      distributed attacks where no single IP exceeds its tier-1 bucket.
        # Both enforce calls happen on failure paths only, so successful
        # auths never consume either budget.
        def _record_passcode_failure() -> None:
            event_passcode_ip_rate_limiter.enforce_rate_limit(
                f"{slug}:{client_ip}", action="event_passcode_fail_ip"
            )
            event_passcode_rate_limiter.enforce_rate_limit(
                slug, action="event_passcode_fail"
            )

        if not passcode_data.passcode:
            _record_passcode_failure()
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Passcode required"
            )

        if not verify_password(passcode_data.passcode, event.passcode_hash):
            # Recording the failure is what raises 429 once one of the
            # two failure budgets is exhausted; until then it returns
            # and we raise the normal 401. A successful passcode never
            # touches either limiter.
            _record_passcode_failure()
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
# Bound the base64 string length BEFORE Pydantic accepts the payload, so
# a multi-GB body can't be parsed into memory first and rejected later.
# Per-frame cap: max_scan_frame_bytes * 4/3 (base64 inflation) + slack for
# data: URL header. Frame count cap: 4 additional (5 total).
_MAX_FRAME_B64_LEN = (settings.max_scan_frame_bytes * 4 // 3) + 256


class FaceScanRequest(BaseModel):
    image: str = Field(..., max_length=_MAX_FRAME_B64_LEN)  # Base64 encoded image (primary frame)
    additional_frames: Optional[List[str]] = Field(
        default=None,
        max_length=4,
        description="Extra frames for multi-angle scan; capped to 4 additional (5 total).",
    )


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
    """Recognize faces in a single frame, using largest face only.

    Returns an empty list when CompreFace can see the image but cannot
    find a usable face (NoFaceDetectedError after the lower-threshold
    retry). Lets CompreFaceUpstreamError propagate so the caller can
    distinguish "no face" from "recognizer is down."
    """
    try:
        results = await recognize_with_compreface(image_bytes, api_key, det_prob_threshold=0.5)
    except NoFaceDetectedError:
        results = []

    if not results:
        try:
            results = await recognize_with_compreface(image_bytes, api_key, det_prob_threshold=0.3)
        except NoFaceDetectedError:
            results = []

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


def _log_scan_outcome(
    db: Session,
    event_id: uuid.UUID,
    session_id: uuid.UUID,
    *,
    outcome: str,
    frame_count: int,
    match_count: int = 0,
    similarity_avg: float = 0.0,
    detail: Optional[str] = None,
) -> None:
    """Single source of truth for scan-attempt audit logging.

    Every code path in the scan flow must call this — success, no-face,
    no-matches, filtered, upstream-error — so analytics can count real
    scan attempts instead of just successful matches.
    """
    metadata: dict = {
        "outcome": outcome,
        "match_count": match_count,
        "frame_count": frame_count,
        "similarity_avg": similarity_avg,
        "recognition_engine": "compreface",
    }
    if detail:
        metadata["detail"] = detail
    log_action(
        db=db,
        event_id=event_id,
        actor_type="guest",
        actor_id=session_id,
        action="scan",
        metadata=metadata,
    )


async def _scan_with_compreface(
    all_frames: List[bytes],
    event_id: uuid.UUID,
    session_id: uuid.UUID,
    event: Event,
    db: Session
) -> FaceScanResponse:
    """Perform face scan using CompreFace, processing multiple frames in parallel.

    Raises:
        NoFaceDetectedError: every submitted frame came back without a
            usable face. The scan endpoint translates this into 400.
        CompreFaceUpstreamError: at least one frame failed because the
            recognizer is unreachable / auth-failing / 5xx-ing. The scan
            endpoint translates this into 502 so the guest sees a real
            error instead of an empty match list.
    """
    api_key = settings.compreface_api_key

    # Process all frames in parallel. return_exceptions so a per-frame
    # upstream failure doesn't abort frames that did succeed — but we
    # still bubble the upstream error if NO frame succeeded.
    frame_tasks = [_recognize_single_frame(frame, api_key) for frame in all_frames]
    frame_results_raw = await asyncio.gather(*frame_tasks, return_exceptions=True)

    frame_results: list[list] = []
    upstream_failures = 0
    for r in frame_results_raw:
        if isinstance(r, CompreFaceUpstreamError):
            upstream_failures += 1
            continue
        if isinstance(r, BaseException):
            # Genuine programming error — let it propagate; uvicorn will 500.
            raise r
        frame_results.append(r)

    frames_with_face = sum(1 for r in frame_results if r)

    if not frame_results and upstream_failures:
        # Every frame hit an upstream error; nothing succeeded.
        _log_scan_outcome(
            db, event_id, session_id,
            outcome="upstream_error",
            frame_count=len(all_frames),
            detail=f"{upstream_failures} frame(s) failed upstream",
        )
        raise CompreFaceUpstreamError("all frames failed against recognizer")

    if frames_with_face == 0:
        # Recognizer reachable, but no face was found in any submitted
        # frame. Distinct from "found a face but no matching photos."
        _log_scan_outcome(
            db, event_id, session_id,
            outcome="no_face",
            frame_count=len(all_frames),
        )
        raise NoFaceDetectedError("no face detected in any submitted frame")

    logger.info(f"Multi-scan: processed {len(all_frames)} frames, "
                f"faces found in {frames_with_face} frames, "
                f"upstream failures: {upstream_failures}")

    # Determine the guest's gender from CompreFace plugin output across all
    # frames. Each frame already filtered to its largest face, so we take a
    # simple majority vote; ties or all-null leave guest_gender = None, in
    # which case gender filtering is skipped.
    guest_gender_votes: list[str] = []
    for recognition_results in frame_results:
        for face_result in recognition_results:
            gender_payload = face_result.get("gender")
            if isinstance(gender_payload, dict):
                value = gender_payload.get("value")
                if isinstance(value, str):
                    guest_gender_votes.append(value.lower())
    guest_gender: Optional[str] = None
    if guest_gender_votes:
        from collections import Counter
        guest_gender = Counter(guest_gender_votes).most_common(1)[0][0]
    logger.info(
        f"Guest gender vote: {guest_gender_votes} -> {guest_gender}"
    )

    # Collect every candidate match that clears the LOWEST tier — we will
    # re-check each against a stricter, size-aware threshold once we look up
    # the indexed Face row.
    baseline_threshold = settings.face_similarity_threshold
    candidates: list[dict] = []

    for recognition_results in frame_results:
        for face_result in recognition_results:
            for subject in face_result.get("subjects", []):
                similarity = subject.get("similarity", 0)
                if similarity < baseline_threshold:
                    continue
                subject_id = subject.get("subject", "")
                parts = subject_id.split("/")
                if len(parts) < 2 or parts[0] != str(event_id):
                    continue
                candidates.append({
                    "subject_id": subject_id,
                    "image_id": parts[1],
                    "similarity": similarity,
                })

    if not candidates:
        logger.warning("No matching faces found across all frames")
        _log_scan_outcome(
            db, event_id, session_id,
            outcome="no_matches",
            frame_count=len(all_frames),
        )
        return FaceScanResponse(
            matches=[],
            scan_id=str(uuid.uuid4()),
            total_matches=0
        )

    # Batch-fetch the Face rows so we can compute per-face min_side without N
    # queries.
    subject_ids = list({c["subject_id"] for c in candidates})
    faces_by_subject = {
        f.compreface_subject_id: f
        for f in db.query(Face).filter(Face.compreface_subject_id.in_(subject_ids)).all()
    }

    def _required_threshold(min_side_px: float) -> float:
        """Size-aware similarity floor for false-positive suppression."""
        if min_side_px >= settings.face_size_large_px:
            return settings.face_similarity_threshold
        if min_side_px >= settings.face_size_medium_px:
            return settings.face_similarity_threshold_medium
        return settings.face_similarity_threshold_small

    # Image-id -> best (highest-similarity) qualifying match.
    best_matches: dict = {}
    rejected_by_gender = 0
    for c in candidates:
        face = faces_by_subject.get(c["subject_id"])
        if face is None or not face.bbox or len(face.bbox) < 4:
            # No bbox = can't tier; require strictest floor.
            min_side = 0.0
        else:
            min_side = min(face.bbox[2] - face.bbox[0], face.bbox[3] - face.bbox[1])

        if c["similarity"] < _required_threshold(min_side):
            continue

        # Cross-gender filter: reject matches where guest's gender is known
        # AND the indexed face has a different gender. Both must be set —
        # missing values leave the candidate alone so we don't break events
        # indexed before the gender plugin was enabled.
        if (
            settings.face_gender_filter_enabled
            and guest_gender
            and face is not None
            and face.gender
            and face.gender != guest_gender
        ):
            rejected_by_gender += 1
            continue

        existing = best_matches.get(c["image_id"])
        if existing is None or c["similarity"] > existing["similarity"]:
            best_matches[c["image_id"]] = {
                "image_id": c["image_id"],
                "similarity": c["similarity"],
                "subject_id": c["subject_id"],
                "bbox": face.bbox if face and face.bbox else [0, 0, 0, 0],
            }
    if rejected_by_gender:
        logger.info(f"Rejected {rejected_by_gender} candidates via gender filter")

    if not best_matches:
        logger.info(
            f"All {len(candidates)} candidates filtered out by size-tiered threshold"
        )
        _log_scan_outcome(
            db, event_id, session_id,
            outcome="filtered",
            frame_count=len(all_frames),
            detail=f"{len(candidates)} candidate(s) all filtered",
        )
        return FaceScanResponse(
            matches=[],
            scan_id=str(uuid.uuid4()),
            total_matches=0
        )

    # Verify images still exist + status is indexed.
    matches = []
    for match_data in best_matches.values():
        result_image_id = match_data["image_id"]
        image_exists = db.query(Image.id).filter(
            Image.id == uuid.UUID(result_image_id),
            Image.event_id == event_id,
            Image.status == 'indexed'
        ).first()
        if not image_exists:
            continue
        matches.append({
            "image_id": result_image_id,
            "similarity": match_data["similarity"],
            "face_bbox": match_data["bbox"],
        })

    matches.sort(key=lambda match: match["similarity"], reverse=True)
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

    # Log successful scan (matched at least one photo)
    similarity_avg = (
        sum(m.similarity for m in face_matches) / len(face_matches)
        if face_matches else 0.0
    )
    _log_scan_outcome(
        db, event_id, session_id,
        outcome="matched" if face_matches else "no_matches",
        frame_count=len(all_frames),
        match_count=len(face_matches),
        similarity_avg=similarity_avg,
    )

    return FaceScanResponse(
        matches=face_matches,
        scan_id=scan_id,
        total_matches=len(face_matches)
    )


@router.post("/scan", response_model=FaceScanResponse)
async def scan_face(
    scan_request: FaceScanRequest,
    request: Request,
    event_token: EventTokenPayload = Depends(get_event_from_token),
    db: Session = Depends(get_db)
):
    """
    Scan a guest's face and find matching photos from the event.

    Uses CompreFace for face recognition.

    - **image**: Base64 encoded face image from camera

    Returns matched photos with presigned URLs

    Rate limited to 30 scans per hour per session AND 30 scans per hour
    per event+client-IP pair. The second limiter prevents a guest from
    re-authenticating to obtain a fresh session_id and reset the per-
    session budget — re-auth still gets a new session token but the IP
    budget rolls over and continues counting against the same client.
    """
    # Parse event_id from token
    event_id = uuid.UUID(event_token.event_id)
    session_id = uuid.UUID(event_token.session_id)

    # Per-session limiter (existing).
    rate_limiter.enforce_rate_limit(str(session_id), action="scan")

    # Per (event, IP) limiter. Key on event_id so one user scanning across
    # different events isn't penalised. "unknown" is the FastAPI fallback
    # when request.client is None (e.g., under some test clients) — that's
    # fine; the limit still applies, it just collapses unknown-IP traffic
    # into one bucket per event.
    client_ip = request.client.host if request.client else "unknown"
    scan_ip_rate_limiter.enforce_rate_limit(
        f"{event_id}:{client_ip}", action="scan_ip"
    )

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

    # Use CompreFace for face recognition (multi-frame). Translate the
    # two domain exceptions into HTTP responses the frontend already
    # understands: 400 for "no usable face in your selfie" (so the user
    # gets retry guidance) and 502 for "the recognizer is down" (so we
    # don't hide an outage as a successful zero-match scan).
    try:
        return await _scan_with_compreface(
            all_frames, event_id, session_id, event, db
        )
    except NoFaceDetectedError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No face detected. Try better lighting, remove sunglasses, and face the camera directly."
        )
    except CompreFaceUpstreamError as e:
        logger.error(f"Scan failed due to CompreFace upstream error: {e}")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Face recognition service is temporarily unavailable. Please try again in a moment."
        )


# ─── Bulk Download (ZIP) ─────────────────────────────────────────────────────

class BulkDownloadRequest(BaseModel):
    # Pre-parse caps so a multi-million-element list can't be deserialised
    # in the first place. The list cap matches the route-level
    # bulk_download_max_images check (still kept as defense-in-depth);
    # each ID is bounded to a generous UUID-string length.
    image_ids: List[str] = Field(
        ...,
        max_length=settings.bulk_download_max_images,
    )


@router.post("/download-zip")
async def download_zip(
    request: BulkDownloadRequest,
    http_request: Request,
    event_token: EventTokenPayload = Depends(get_event_from_token),
    db: Session = Depends(get_db)
):
    """
    Download multiple photos as a ZIP file.

    - **image_ids**: List of image UUID strings to include

    Returns a ZIP file containing the requested photos.
    Rate limited per session AND per (event_id, client_ip) — re-authing
    to mint a fresh session_id resets the per-session budget but the
    per-IP one carries over, so a guest can't trivially loop the zip
    download by rolling sessions.
    """
    event_id = uuid.UUID(event_token.event_id)
    session_id = uuid.UUID(event_token.session_id)

    # Enforce both rate limits before any DB work.
    rate_limiter.enforce_rate_limit(str(session_id), action="download")

    client_ip = http_request.client.host if http_request.client else "unknown"
    download_ip_rate_limiter.enforce_rate_limit(
        f"{event_id}:{client_ip}", action="download_ip"
    )

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
                uploaded_at=to_utc_iso(image.uploaded_at) or ""
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

    # Restrict to guest-visible statuses, matching the gallery filter.
    # Without this an attacker who knew an image UUID could trigger a
    # public signed URL via the share endpoint even when the image was
    # in 'pending' (mid-upload), 'failed' (worker errored), or had been
    # bounced back to 'pending' by a reindex — none of which should be
    # publicly previewable.
    image = (
        db.query(Image.id)
        .filter(
            Image.id == image_uuid,
            Image.event_id == event_uuid,
            Image.status.in_(('indexed', 'no_faces')),
        )
        .first()
    )
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


