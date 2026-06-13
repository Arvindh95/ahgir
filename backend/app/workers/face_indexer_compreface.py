"""Face indexing worker using CompreFace API."""

import uuid
import logging
import asyncio
import httpx
from datetime import datetime
from sqlalchemy.orm import Session
from typing import Optional
from PIL import Image as PILImage, ImageOps
import io

from app.database import SessionLocal
from app.models import Image, Face
from app.storage import storage_service
from app.config import settings, get_compreface_url
from app.utils.thumbnail import generate_thumbnail
from app.utils.image_safety import safe_open as safe_open_image
from app.cache import cache_delete_pattern
from app.face_quality import compute_face_quality_metrics
from app.body_crop import derive_upper_body_bbox
from app.reid_client import compute_embedding as compute_reid_embedding


class CompreFaceUpstreamError(Exception):
    """Transient / upstream / auth failure talking to CompreFace.

    Raised so the outer worker handler marks the image as failed and re-raises
    for RQ to retry. Distinct from logical 4xx rejections (e.g. "More than
    one face in crop") which the worker handles by retrying with a tighter
    crop or skipping the face — those are not transient and a retry of the
    whole job wouldn't help.
    """

logger = logging.getLogger(__name__)


def _run_async(coro):
    """Run async function in sync context."""
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop.run_until_complete(coro)


async def _add_face_to_compreface(
    image_data: bytes,
    subject_id: str,
    api_key: str,
    det_prob_threshold: float = 0.5
) -> dict:
    """Add a face to CompreFace recognition service."""
    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            files = {"file": ("image.jpg", image_data, "image/jpeg")}
            params = {
                "subject": subject_id,
                "det_prob_threshold": det_prob_threshold,
            }
            headers = {"x-api-key": api_key}

            response = await client.post(
                f"{get_compreface_url()}/api/v1/recognition/faces",
                headers=headers,
                files=files,
                params=params,
            )

            if response.status_code == 201:
                return response.json()

            # 4xx (except auth) is treated as logical rejection — caller can
            # decide to retry with a tighter crop, skip the face, etc.
            # 5xx / 401 / 403 / 429 are upstream failures that warrant a job
            # retry: raise so the outer try in the worker marks the image
            # failed and RQ requeues.
            status = response.status_code
            if status in (401, 403, 429) or 500 <= status < 600:
                msg = f"CompreFace add_face upstream failure: {status} - {response.text}"
                logger.error(msg)
                raise CompreFaceUpstreamError(msg)

            logger.error(f"CompreFace add_face logical failure: {status} - {response.text}")
            return {"error": response.text, "status_code": status}

    except (httpx.TimeoutException, httpx.NetworkError, httpx.HTTPError) as e:
        # Timeouts and other transport errors are always transient.
        logger.error(f"Network error adding face to CompreFace: {e}")
        raise CompreFaceUpstreamError(f"network error: {e}") from e
    except CompreFaceUpstreamError:
        raise
    except Exception as e:
        # Anything else (incl. JSON decode of a corrupt response) is also
        # transient from our point of view.
        logger.error(f"Unexpected error adding face to CompreFace: {e}")
        raise CompreFaceUpstreamError(f"unexpected: {e}") from e


async def _detect_faces_compreface(
    image_data: bytes,
    api_key: str,
    det_prob_threshold: float = 0.5,
    face_plugins: Optional[str] = "gender",
) -> list:
    """Detect faces in an image using CompreFace Detection service.

    ``face_plugins`` is forwarded to CompreFace; when "gender" is included
    (and the gender plugin is loaded in compreface-core) each result has a
    ``gender`` field we can use to filter cross-gender false matches.
    """
    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            files = {"file": ("image.jpg", image_data, "image/jpeg")}
            params: dict = {
                "det_prob_threshold": det_prob_threshold,
                "limit": 200,  # Support large group photos
            }
            if face_plugins:
                params["face_plugins"] = face_plugins
            headers = {"x-api-key": api_key}

            response = await client.post(
                f"{get_compreface_url()}/api/v1/detection/detect",
                headers=headers,
                files=files,
                params=params,
            )

            if response.status_code == 200:
                result = response.json()
                # 200 with an empty result is legitimate "no faces detected".
                # Anything else is an upstream problem — see _add_face_to_compreface
                # comment for the rationale.
                return result.get("result", [])

            status = response.status_code
            msg = f"CompreFace detect failed: {status} - {response.text}"
            logger.error(msg)
            raise CompreFaceUpstreamError(msg)

    except (httpx.TimeoutException, httpx.NetworkError, httpx.HTTPError) as e:
        logger.error(f"Network error detecting faces with CompreFace: {e}")
        raise CompreFaceUpstreamError(f"network error: {e}") from e
    except CompreFaceUpstreamError:
        raise
    except Exception as e:
        logger.error(f"Unexpected error detecting faces with CompreFace: {e}")
        raise CompreFaceUpstreamError(f"unexpected: {e}") from e


def index_photo_compreface(image_id: str, api_key: str, db_session: Optional[Session] = None) -> dict:
    """
    Process a photo and register faces with CompreFace.

    This is the main RQ job handler that:
    1. Downloads photo from MinIO
    2. Detects faces using CompreFace Detection service
    3. Adds each face to CompreFace Recognition service
    4. Stores face metadata in database
    5. Updates image status

    Args:
        image_id: UUID string of the image to process
        api_key: CompreFace API key for the recognition service
        db_session: Optional database session (for testing)

    Returns:
        Dictionary with processing results
    """
    db: Optional[Session] = None
    should_close_db = False

    # Get detection API key (separate from recognition)
    detection_api_key = settings.compreface_detection_api_key

    try:
        # Parse image_id
        try:
            image_uuid = uuid.UUID(image_id)
        except ValueError:
            logger.error(f"Invalid image_id format: {image_id}")
            return {
                'image_id': image_id,
                'status': 'failed',
                'face_count': 0,
                'error': 'Invalid image_id format'
            }

        # Create database session if not provided
        if db_session is None:
            db = SessionLocal()
            should_close_db = True
        else:
            db = db_session

        # Fetch + row-lock the image. with_for_update() blocks any concurrent
        # face-indexer job from racing us through the wipe-and-reinsert
        # flow below. Without this, two RQ workers picking up the same
        # image_id (which can happen if a retry fires before the failure
        # is marked) both clear Face rows then both insert new ones,
        # producing duplicate compreface_subject_id values.
        image = db.query(Image).filter(Image.id == image_uuid).with_for_update().first()

        if not image:
            logger.error(f"Image not found: {image_id}")
            return {
                'image_id': image_id,
                'status': 'failed',
                'face_count': 0,
                'error': 'Image not found'
            }

        # If a parallel worker already finished this image while we were
        # waiting on the lock, bail out idempotently. Returning the live
        # status keeps callers (RQ retries especially) from treating a
        # successful first attempt as a failure when they reawake later.
        if image.status == 'indexed':
            logger.info(
                f"Image {image_id} already indexed (status={image.status}, "
                f"face_count={image.face_count}); skipping duplicate job"
            )
            return {
                'image_id': image_id,
                'status': image.status,
                'face_count': image.face_count,
            }

        logger.info(f"Processing image {image_id} for event {image.event_id}")

        # Wipe any Face rows left over from a prior failed attempt at this
        # same image_id. Without this, a job retry can stack duplicate Face
        # rows (and duplicate compreface_subject_id values) for the same
        # face on the same photo. The CompreFace-side subjects with the
        # exact same subject_id will simply overwrite themselves on the
        # add_face POST, so we only need to clear the DB side here.
        # NOTE: we still commit here so the delete is durable even if the
        # subsequent compreface calls take a while; the row lock above is
        # released when we commit, but by then image.status has been
        # implicitly held inside our session and the new INSERTs go through
        # the unique partial index on compreface_subject_id as a final
        # backstop.
        existing_faces = db.query(Face).filter(Face.image_id == image_uuid).count()
        if existing_faces:
            logger.info(
                f"Clearing {existing_faces} stale Face row(s) from prior attempt "
                f"for image {image_id}"
            )
            db.query(Face).filter(Face.image_id == image_uuid).delete()
            db.commit()

        # Download photo from MinIO
        try:
            photo_bytes = storage_service.get_photo(
                event_id=image.event_id,
                image_id=image.id,
                photo_type='original'
            )
        except Exception as e:
            logger.error(f"Failed to download photo {image_id}: {str(e)}")
            image.status = 'failed'
            db.commit()
            return {
                'image_id': image_id,
                'status': 'failed',
                'face_count': 0,
                'error': f'Failed to download photo: {str(e)}'
            }

        # Generate thumbnail if missing
        try:
            storage_service.get_photo(
                event_id=image.event_id, image_id=image.id, photo_type='thumb'
            )
        except FileNotFoundError:
            try:
                thumb_bytes = generate_thumbnail(photo_bytes)
                storage_service.upload_photo(
                    event_id=image.event_id, image_id=image.id,
                    photo_data=thumb_bytes, photo_type='thumb'
                )
                logger.info(f"Generated missing thumbnail for image {image_id}")
            except Exception as e:
                logger.warning(f"Failed to generate thumbnail for {image_id}: {e}")
        except Exception:
            pass  # Thumbnail exists or other error, continue

        # Apply EXIF orientation so face detection works on upright images
        pil_img = safe_open_image(photo_bytes)
        pil_img = ImageOps.exif_transpose(pil_img)
        if pil_img.mode in ('RGBA', 'LA', 'P'):
            pil_img = pil_img.convert('RGB')
        oriented_buf = io.BytesIO()
        pil_img.save(oriented_buf, format='JPEG', quality=95)
        oriented_buf.seek(0)
        oriented_bytes = oriented_buf.getvalue()

        # Step 1: Detect all faces using Detection service
        logger.info(f"Detecting faces in image {image_id} using CompreFace Detection")
        faces = _run_async(_detect_faces_compreface(
            oriented_bytes,
            detection_api_key,
            det_prob_threshold=settings.face_min_detection_probability
        ))
        logger.info(f"Detected {len(faces)} faces in image {image_id}")

        # Step 2: Crop and add each detected face to Recognition service
        # Use the EXIF-corrected image for cropping
        img = pil_img

        face_count = 0
        attempted_adds = 0  # faces that passed the quality filter and we tried to upload to CompreFace
        upstream_failures = 0  # transient/auth/5xx errors during add_face — counted so we raise if ALL adds failed transiently
        skipped_low_quality = 0
        for idx, face_data in enumerate(faces):
            box = face_data.get("box", {})
            # CompreFace normally nests probability under "box", but some mocks
            # and older deployments expose it at the top level.
            probability = box.get("probability", face_data.get("probability", 0))

            x_min = int(box.get("x_min", 0))
            y_min = int(box.get("y_min", 0))
            x_max = int(box.get("x_max", 0))
            y_max = int(box.get("y_max", 0))

            face_w = x_max - x_min
            face_h = y_max - y_min
            min_side = min(face_w, face_h)
            if probability < settings.face_min_detection_probability or min_side < settings.face_min_crop_pixels:
                skipped_low_quality += 1
                logger.info(
                    f"Skipping face {idx} in image {image_id}: "
                    f"prob={probability:.2f} (min {settings.face_min_detection_probability}), "
                    f"size={face_w}x{face_h} (min {settings.face_min_crop_pixels}px)"
                )
                continue

            # Pad each face crop so the embedder gets more context (hair,
            # ears, jaw line). 0.4 = 40% on each side; tuned via
            # settings.face_crop_padding_factor.
            width = x_max - x_min
            height = y_max - y_min
            pad_factor = settings.face_crop_padding_factor
            padding_x = int(width * pad_factor)
            padding_y = int(height * pad_factor)

            crop_x1 = max(0, x_min - padding_x)
            crop_y1 = max(0, y_min - padding_y)
            crop_x2 = min(img.width, x_max + padding_x)
            crop_y2 = min(img.height, y_max + padding_y)

            # Compute technical-quality metrics on the padded crop. These
            # populate the migration columns the scan-side scorer reads to
            # decide whether to raise / lower the cosine-similarity threshold
            # for this indexed face. Costs ~one extra 64x64 grayscale pass
            # plus a crop, so well under 1ms per face.
            try:
                quality_metrics = compute_face_quality_metrics(
                    img,
                    [x_min, y_min, x_max, y_max],
                    [crop_x1, crop_y1, crop_x2, crop_y2],
                )
            except Exception as exc:
                # Quality metrics are an accuracy nice-to-have, not a hard
                # requirement — if the helper raises on a weird image, the
                # face still gets indexed without them and the scorer falls
                # back to detection-probability-only thresholds.
                logger.warning(
                    f"compute_face_quality_metrics failed for face {idx} "
                    f"in image {image_id}: {exc}"
                )
                quality_metrics = None

            # Crop face
            face_img = img.crop((crop_x1, crop_y1, crop_x2, crop_y2))

            # Convert to RGB if image has alpha channel
            if face_img.mode in ('RGBA', 'LA', 'P'):
                face_img = face_img.convert('RGB')

            # Convert cropped face to bytes
            face_bytes = io.BytesIO()
            face_img.save(face_bytes, format='JPEG', quality=95)
            face_bytes.seek(0)
            cropped_face_data = face_bytes.getvalue()

            # Create subject ID: event_id/image_id/face_idx
            subject_id = f"{image.event_id}/{image_id}/{idx}"

            # Add cropped face to CompreFace recognition service. Upstream
            # / transient failures raise CompreFaceUpstreamError; logical
            # rejections (4xx that aren't auth) return {"error": ...} which
            # we handle below.
            attempted_adds += 1
            try:
                result = _run_async(_add_face_to_compreface(
                    cropped_face_data,
                    subject_id,
                    api_key,
                    det_prob_threshold=0.5
                ))

                # If multiple faces in crop (nearby faces), retry with no padding
                if "error" in result and "More than one face" in str(result.get("error", "")):
                    logger.info(f"Retrying face {idx} with no padding (multiple faces in crop)")
                    face_img_tight = img.crop((x_min, y_min, x_max, y_max))
                    if face_img_tight.mode in ('RGBA', 'LA', 'P'):
                        face_img_tight = face_img_tight.convert('RGB')
                    tight_buf = io.BytesIO()
                    face_img_tight.save(tight_buf, format='JPEG', quality=95)
                    tight_buf.seek(0)
                    result = _run_async(_add_face_to_compreface(
                        tight_buf.getvalue(),
                        subject_id,
                        api_key,
                        det_prob_threshold=0.5
                    ))
            except CompreFaceUpstreamError as e:
                # Don't bail out on the first transient failure — the next
                # face might succeed and we can still index a subset. But
                # remember it: if EVERY add fails this way we raise at the
                # end so RQ retries the whole image rather than persisting
                # a no_faces / partial-success state.
                upstream_failures += 1
                logger.warning(f"Upstream failure adding face {idx} for image {image_id}: {e}")
                continue

            if "error" not in result:
                # Store face metadata in our database
                bbox = [x_min, y_min, x_max, y_max]

                # Pull the gender plugin output if present. CompreFace returns:
                #   { "gender": { "value": "male", "probability": 0.98 } }
                # We persist only the label; the probability is informational.
                gender_payload = face_data.get("gender") or {}
                gender_value = gender_payload.get("value") if isinstance(gender_payload, dict) else None
                if isinstance(gender_value, str):
                    gender_value = gender_value.lower()
                else:
                    gender_value = None

                # Compute the per-face Re-ID body embedding. Derives an upper-
                # body crop from the same `img` already in memory, ships it to
                # the reid-api sidecar, and writes the returned 512-d vector
                # into the Face row. Any failure (sidecar down, timeout,
                # degenerate crop, missing model) is fail-soft — leaves
                # reid_embedding NULL and the scan-time Re-ID gate falls back
                # to face-only matching for that candidate. Same `img` /
                # bbox geometry MUST flow through derive_upper_body_bbox so
                # the probe-side crop at scan time matches.
                reid_embedding_value: Optional[list[float]] = None
                if settings.reid_enabled_indexing:
                    try:
                        body_bbox = derive_upper_body_bbox(
                            [x_min, y_min, x_max, y_max],
                            img.width,
                            img.height,
                        )
                        body_crop_img = img.crop(body_bbox)
                        if body_crop_img.mode in ('RGBA', 'LA', 'P'):
                            body_crop_img = body_crop_img.convert('RGB')
                        body_buf = io.BytesIO()
                        body_crop_img.save(body_buf, format='JPEG', quality=90)
                        reid_embedding_value = _run_async(
                            compute_reid_embedding(body_buf.getvalue())
                        )
                    except Exception as reid_exc:
                        # Indexer must never fail because Re-ID failed. Log and
                        # write NULL — the backfill job can fill it in later.
                        logger.warning(
                            f"Re-ID embedding failed for face {idx} of image {image_id}: {reid_exc}"
                        )
                        reid_embedding_value = None

                # We store the CompreFace subject_id as the embedding reference
                # (CompreFace manages actual embeddings internally)
                face = Face(
                    image_id=image.id,
                    event_id=image.event_id,
                    embedding=[0.0] * 512,  # Placeholder - CompreFace manages embeddings
                    bbox=bbox,
                    quality_score=probability,
                    compreface_subject_id=subject_id,  # Store CompreFace reference
                    gender=gender_value,
                    face_min_side_px=quality_metrics.face_min_side_px if quality_metrics else None,
                    blur_score=quality_metrics.blur_score if quality_metrics else None,
                    brightness_score=quality_metrics.brightness_score if quality_metrics else None,
                    crop_clipped=quality_metrics.crop_clipped if quality_metrics else False,
                    reid_embedding=reid_embedding_value,
                )
                db.add(face)
                face_count += 1
                logger.info(
                    f"Added face {idx} for image {image_id} "
                    f"(subject: {subject_id}, gender: {gender_value})"
                )
            else:
                logger.warning(f"Failed to add face {idx} to CompreFace: {result.get('error')}")

        if skipped_low_quality:
            logger.info(f"Skipped {skipped_low_quality} low-quality faces in image {image_id}")

        # Distinguish "no faces" from "all add_face attempts failed transiently".
        # The latter must NOT persist as no_faces — that hides the failure and
        # guest scans will never match this image until somebody manually
        # reindexes. Raise so the outer handler marks the image failed and
        # RQ retries the whole job.
        if attempted_adds > 0 and face_count == 0 and upstream_failures > 0:
            raise CompreFaceUpstreamError(
                f"All {attempted_adds} add_face attempts failed upstream "
                f"for image {image_id} ({upstream_failures} transient errors). "
                "Raising so RQ retries the whole job."
            )

        if face_count > 0:
            image.status = 'indexed'
            image.face_count = face_count
            image.indexed_at = datetime.utcnow()
            logger.info(f"Successfully indexed {face_count} faces for image {image_id}")
        else:
            # Either detection genuinely returned 0 faces, or every detected
            # face was skipped as low-quality. Both are legitimate no_faces.
            image.status = 'no_faces'
            image.face_count = 0
            image.indexed_at = datetime.utcnow()
            logger.info(f"No faces detected in image {image_id}")

        db.commit()

        # Invalidate guest-facing caches for this event so the gallery and
        # share endpoints reflect the freshly-indexed (or no_faces) image
        # immediately. Without this, scans return stale results / share
        # pages return missing thumbnails for up to the cache TTL after
        # indexing completes.
        try:
            cache_delete_pattern(f"gallery:{image.event_id}:*")
            cache_delete_pattern(f"share:{image.event_id}:*")
        except Exception as e:
            logger.warning(f"cache invalidation failed for event {image.event_id}: {e}")

        return {
            'image_id': image_id,
            'status': image.status,
            'face_count': face_count
        }

    except Exception as e:
        logger.error(f"Unexpected error processing image {image_id}: {str(e)}", exc_info=True)

        if db:
            # ROLLBACK pending uncommitted changes BEFORE we touch the image
            # status. Otherwise any Face rows added in the loop above get
            # flushed alongside our status update, leaving orphaned face
            # records that point to an image marked 'failed'. On retry those
            # rows would also produce duplicate compreface_subject_id values.
            try:
                db.rollback()
            except Exception as rollback_err:
                logger.warning(f"db.rollback failed for image {image_id}: {rollback_err}")

            try:
                image = db.query(Image).filter(Image.id == uuid.UUID(image_id)).first()
                if image:
                    image.status = 'failed'
                    db.commit()
            except Exception:
                pass

        raise

    finally:
        if db and should_close_db:
            db.close()
