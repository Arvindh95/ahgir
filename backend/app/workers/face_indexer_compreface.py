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
            else:
                logger.error(f"CompreFace add_face failed: {response.status_code} - {response.text}")
                return {"error": response.text, "status_code": response.status_code}

    except Exception as e:
        logger.error(f"Error adding face to CompreFace: {e}")
        return {"error": str(e)}


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
                return result.get("result", [])
            else:
                logger.error(f"CompreFace detect failed: {response.status_code} - {response.text}")
                return []

    except Exception as e:
        logger.error(f"Error detecting faces with CompreFace: {e}")
        return []


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

        # Fetch image record
        image = db.query(Image).filter(Image.id == image_uuid).first()

        if not image:
            logger.error(f"Image not found: {image_id}")
            return {
                'image_id': image_id,
                'status': 'failed',
                'face_count': 0,
                'error': 'Image not found'
            }

        logger.info(f"Processing image {image_id} for event {image.event_id}")

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

            # Add cropped face to CompreFace recognition service
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

        if face_count > 0:
            image.status = 'indexed'
            image.face_count = face_count
            image.indexed_at = datetime.utcnow()
            logger.info(f"Successfully indexed {face_count} faces for image {image_id}")
        else:
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
