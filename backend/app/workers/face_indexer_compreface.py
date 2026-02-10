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
    det_prob_threshold: float = 0.5
) -> list:
    """Detect faces in an image using CompreFace Detection service."""
    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            files = {"file": ("image.jpg", image_data, "image/jpeg")}
            params = {
                "det_prob_threshold": det_prob_threshold,
                "limit": 200,  # Support large group photos
            }
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
        pil_img = PILImage.open(io.BytesIO(photo_bytes))
        pil_img = ImageOps.exif_transpose(pil_img)
        if pil_img.mode in ('RGBA', 'LA', 'P'):
            pil_img = pil_img.convert('RGB')
        oriented_buf = io.BytesIO()
        pil_img.save(oriented_buf, format='JPEG', quality=95)
        oriented_buf.seek(0)
        oriented_bytes = oriented_buf.getvalue()

        # Step 1: Detect all faces using Detection service
        logger.info(f"Detecting faces in image {image_id} using CompreFace Detection")
        faces = _run_async(_detect_faces_compreface(oriented_bytes, detection_api_key, det_prob_threshold=0.5))
        logger.info(f"Detected {len(faces)} faces in image {image_id}")

        # If no faces detected, try with lower threshold
        if len(faces) == 0:
            faces = _run_async(_detect_faces_compreface(oriented_bytes, detection_api_key, det_prob_threshold=0.3))
            logger.info(f"Detected {len(faces)} faces with lower threshold")

        # Step 2: Crop and add each detected face to Recognition service
        # Use the EXIF-corrected image for cropping
        img = pil_img

        face_count = 0
        for idx, face_data in enumerate(faces):
            box = face_data.get("box", {})
            probability = face_data.get("probability", 0)

            # Crop face from image with padding
            x_min = int(box.get("x_min", 0))
            y_min = int(box.get("y_min", 0))
            x_max = int(box.get("x_max", 0))
            y_max = int(box.get("y_max", 0))

            # Add 20% padding around face
            width = x_max - x_min
            height = y_max - y_min
            padding_x = int(width * 0.2)
            padding_y = int(height * 0.2)

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

                # We store the CompreFace subject_id as the embedding reference
                # (CompreFace manages actual embeddings internally)
                face = Face(
                    image_id=image.id,
                    event_id=image.event_id,
                    embedding=[0.0] * 512,  # Placeholder - CompreFace manages embeddings
                    bbox=bbox,
                    quality_score=probability,
                    compreface_subject_id=subject_id  # Store CompreFace reference
                )
                db.add(face)
                face_count += 1
                logger.info(f"Added face {idx} for image {image_id} (subject: {subject_id})")
            else:
                logger.warning(f"Failed to add face {idx} to CompreFace: {result.get('error')}")

        # Update image status
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
