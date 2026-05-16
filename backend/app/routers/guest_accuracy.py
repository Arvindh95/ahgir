"""Enhanced guest scan route using accuracy-focused match scoring.

This router intentionally defines POST /scan and is included before the legacy
Guest router. It reuses the existing auth, sanitization, rate limiting, and URL
helpers, but replaces the final ranking/filtering step with the scoring helper.
"""

from __future__ import annotations

import asyncio
import base64
import logging
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.auth import EventTokenPayload, get_event_from_token
from app.database import get_db
from app.models import Event, Face, Image
from app.rate_limiter import rate_limiter, scan_ip_rate_limiter
from app.config import settings
from app.routers import guest as _guest_legacy
from app.routers.guest import (
    CompreFaceUpstreamError,
    FaceMatch,
    FaceScanRequest,
    FaceScanResponse,
    NoFaceDetectedError,
    _guest_photo_urls,
    _log_scan_outcome,
    _sanitize_scan_frame,
)
# NOTE: _recognize_single_frame is intentionally NOT imported by name. Call
# it as `_guest_legacy._recognize_single_frame(...)` so test patches against
# `app.routers.guest._recognize_single_frame` propagate to this router too.
# A `from ... import _recognize_single_frame` would bind a separate name
# here and bypass those patches.
from app.face_match_scoring import (
    CandidateMatch,
    MatchScoringConfig,
    aggregate_face_matches,
)

logger = logging.getLogger(__name__)
router = APIRouter(tags=["guest-accuracy"])


def _scoring_config() -> MatchScoringConfig:
    """Use MatchScoringConfig defaults (0.87 / 0.90 / 0.93 tiered thresholds).

    The face_similarity_threshold* env vars are flat 0.90 across all tiers in
    config.py today, so coupling them in here just flattens the tiering. The
    dataclass defaults already encode the intended adaptive thresholds; if
    future tuning needs env-driven tier overrides, introduce dedicated env
    vars rather than reusing the flat ones.
    """
    return MatchScoringConfig(
        medium_face_px=getattr(settings, "face_size_medium_px", 60),
        large_face_px=getattr(settings, "face_size_large_px", 150),
    )


def _decode_and_sanitize_frames(scan_request: FaceScanRequest) -> list[bytes]:
    max_b64 = settings.max_scan_frame_bytes * 4 // 3 + 16
    max_total = settings.max_scan_total_bytes

    def _decode_frame(data: str) -> bytes:
        if not isinstance(data, str):
            raise ValueError("frame must be a string")
        if len(data) > max_b64:
            raise ValueError(f"frame exceeds {settings.max_scan_frame_bytes} bytes")
        if data.startswith("data:"):
            comma = data.find(",")
            if comma == -1:
                raise ValueError("invalid data URL")
            data = data[comma + 1:]
        decoded = base64.b64decode(data, validate=False)
        if len(decoded) > settings.max_scan_frame_bytes:
            raise ValueError(f"frame exceeds {settings.max_scan_frame_bytes} bytes")
        return decoded

    primary = _sanitize_scan_frame(_decode_frame(scan_request.image))
    all_frames = [primary]
    running_total = len(primary)

    if scan_request.additional_frames:
        for frame_data in scan_request.additional_frames[:4]:
            try:
                sanitized = _sanitize_scan_frame(_decode_frame(frame_data))
            except HTTPException:
                continue
            except Exception:
                continue
            if running_total + len(sanitized) > max_total:
                logger.warning("Scan request truncated: total frame size exceeds cap")
                break
            all_frames.append(sanitized)
            running_total += len(sanitized)

    logger.info("Received %s scan frames, %s bytes (sanitized)", len(all_frames), running_total)
    return all_frames


def _fetch_face_rows(db: Session, subject_ids: list[str]) -> dict[str, object]:
    """Return subject_id -> Face-like mapping, including optional migration fields.

    The SQL migration adds quality / cluster columns. During rolling deploys the
    columns may not exist yet, so we fall back to ORM rows. The scoring helper
    handles both ORM rows and dictionaries.
    """
    if not subject_ids:
        return {}
    try:
        rows = db.execute(
            text(
                """
                SELECT
                    compreface_subject_id,
                    bbox,
                    quality_score,
                    face_min_side_px,
                    blur_score,
                    brightness_score,
                    crop_clipped,
                    face_cluster_id
                FROM faces
                WHERE compreface_subject_id = ANY(:subject_ids)
                """
            ),
            {"subject_ids": subject_ids},
        ).mappings().all()
        return {row["compreface_subject_id"]: dict(row) for row in rows}
    except Exception as exc:
        logger.warning("Falling back to ORM Face rows for scoring metadata: %s", exc)
        return {
            f.compreface_subject_id: f
            for f in db.query(Face).filter(Face.compreface_subject_id.in_(subject_ids)).all()
            if f.compreface_subject_id
        }


async def _scan_with_enhanced_scoring(
    all_frames: list[bytes],
    event_id: uuid.UUID,
    session_id: uuid.UUID,
    event: Event,
    db: Session,
) -> FaceScanResponse:
    frame_results_raw = await asyncio.gather(
        *[
            _guest_legacy._recognize_single_frame(frame, settings.compreface_api_key)
            for frame in all_frames
        ],
        return_exceptions=True,
    )

    frame_results: list[list] = []
    upstream_failures = 0
    for result in frame_results_raw:
        if isinstance(result, CompreFaceUpstreamError):
            upstream_failures += 1
            continue
        if isinstance(result, BaseException):
            raise result
        frame_results.append(result)

    frames_with_face = sum(1 for result in frame_results if result)
    if not frame_results and upstream_failures:
        _log_scan_outcome(
            db,
            event_id,
            session_id,
            outcome="upstream_error",
            frame_count=len(all_frames),
            detail=f"{upstream_failures} frame(s) failed upstream",
        )
        raise CompreFaceUpstreamError("all frames failed against recognizer")
    if frames_with_face == 0:
        _log_scan_outcome(db, event_id, session_id, outcome="no_face", frame_count=len(all_frames))
        raise NoFaceDetectedError("no face detected in any submitted frame")

    candidates: list[CandidateMatch] = []
    # Pull a broad candidate set; adaptive/quality thresholds are applied by
    # aggregate_face_matches after it can see indexed face metadata.
    broad_floor = min(
        getattr(settings, "face_similarity_threshold", 0.90),
        0.84,
    )
    for frame_index, recognition_results in enumerate(frame_results):
        for face_result in recognition_results:
            for subject in face_result.get("subjects", []):
                similarity = float(subject.get("similarity", 0) or 0)
                if similarity < broad_floor:
                    continue
                subject_id = subject.get("subject", "")
                parts = subject_id.split("/")
                if len(parts) < 2 or parts[0] != str(event_id):
                    continue
                candidates.append(CandidateMatch(
                    subject_id=subject_id,
                    image_id=parts[1],
                    similarity=similarity,
                    frame_index=frame_index,
                ))

    if not candidates:
        _log_scan_outcome(db, event_id, session_id, outcome="no_matches", frame_count=len(all_frames))
        return FaceScanResponse(matches=[], scan_id=str(uuid.uuid4()), total_matches=0)

    faces_by_subject = _fetch_face_rows(db, list({c.subject_id for c in candidates}))
    scored = aggregate_face_matches(candidates, faces_by_subject, _scoring_config())

    if not scored:
        _log_scan_outcome(
            db,
            event_id,
            session_id,
            outcome="filtered",
            frame_count=len(all_frames),
            detail=f"{len(candidates)} candidate(s) all filtered by enhanced scoring",
        )
        return FaceScanResponse(matches=[], scan_id=str(uuid.uuid4()), total_matches=0)

    image_ids = [uuid.UUID(match.image_id) for match in scored]
    visible_image_ids = {
        row[0]
        for row in db.query(Image.id).filter(
            Image.id.in_(image_ids),
            Image.event_id == event_id,
            Image.status == "indexed",
        ).all()
    }

    face_matches: list[FaceMatch] = []
    for match in scored:
        image_uuid = uuid.UUID(match.image_id)
        if image_uuid not in visible_image_ids:
            continue
        try:
            thumbnail_url, original_url, download_url = _guest_photo_urls(
                event_id,
                image_uuid,
                event.allow_downloads,
            )
            face_matches.append(FaceMatch(
                image_id=match.image_id,
                similarity=match.similarity,
                thumbnail_url=thumbnail_url,
                original_url=original_url,
                download_url=download_url,
                face_bbox=match.bbox,
            ))
        except Exception as exc:
            logger.error("Failed to generate URL for image %s: %s", match.image_id, exc)

    similarity_avg = sum(m.similarity for m in face_matches) / len(face_matches) if face_matches else 0.0
    _log_scan_outcome(
        db,
        event_id,
        session_id,
        outcome="matched" if face_matches else "no_matches",
        frame_count=len(all_frames),
        match_count=len(face_matches),
        similarity_avg=similarity_avg,
        detail="enhanced_scoring",
    )

    return FaceScanResponse(
        matches=face_matches,
        scan_id=str(uuid.uuid4()),
        total_matches=len(face_matches),
    )


@router.post("/scan", response_model=FaceScanResponse)
async def scan_face_enhanced(
    scan_request: FaceScanRequest,
    request: Request,
    event_token: EventTokenPayload = Depends(get_event_from_token),
    db: Session = Depends(get_db),
):
    event_id = uuid.UUID(event_token.event_id)
    session_id = uuid.UUID(event_token.session_id)

    rate_limiter.enforce_rate_limit(str(session_id), action="scan")
    client_ip = request.client.host if request.client else "unknown"
    scan_ip_rate_limiter.enforce_rate_limit(f"{event_id}:{client_ip}", action="scan_ip")

    event = db.query(Event).filter(Event.id == event_id).first()
    if not event:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")

    try:
        all_frames = _decode_and_sanitize_frames(scan_request)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail=str(exc))
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Failed to decode scan frames: %s", exc)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid base64 image data")

    try:
        return await _scan_with_enhanced_scoring(all_frames, event_id, session_id, event, db)
    except NoFaceDetectedError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No face detected. Try better lighting, remove sunglasses, and face the camera directly.",
        )
    except CompreFaceUpstreamError as exc:
        logger.error("Scan failed due to CompreFace upstream error: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Face recognition service is temporarily unavailable. Please try again in a moment.",
        )
