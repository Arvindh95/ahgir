"""Face indexing worker job handler."""

import uuid
import logging
from datetime import datetime
from sqlalchemy.orm import Session
from typing import Optional

from app.database import SessionLocal
from app.models import Image, Face
from app.storage import storage_service
from app.face_detection import face_detector
from app.retry_utils import exponential_backoff
from app.exceptions import FaceDetectionFailedError, StorageError

logger = logging.getLogger(__name__)


def index_photo(image_id: str, max_retries: int = 3, db_session: Optional[Session] = None) -> dict:
    """
    Process a photo and extract face embeddings.
    
    This is the main RQ job handler that:
    1. Downloads photo from MinIO
    2. Detects faces using InsightFace
    3. Stores face embeddings in database
    4. Updates image status
    
    Args:
        image_id: UUID string of the image to process
        max_retries: Maximum number of retry attempts (default: 3)
        db_session: Optional database session (for testing)
    
    Returns:
        Dictionary with processing results:
            - image_id: UUID string
            - status: Final status (indexed, no_faces, or failed)
            - face_count: Number of faces detected
            - error: Error message if failed (optional)
    
    Raises:
        Exception: If processing fails after all retries
    """
    db: Optional[Session] = None
    should_close_db = False
    
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
        
        # Download photo from MinIO with retry logic
        try:
            photo_bytes = storage_service.get_photo(
                event_id=image.event_id,
                image_id=image.id,
                photo_type='original'
            )
        except StorageError as e:
            logger.error(f"Failed to download photo {image_id} after retries: {str(e)}")
            image.status = 'failed'
            db.commit()
            return {
                'image_id': image_id,
                'status': 'failed',
                'face_count': 0,
                'error': f'Failed to download photo: {str(e)}'
            }
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
        
        # Detect faces using InsightFace with retry logic
        @exponential_backoff(max_retries=3, base_delay=1.0, exceptions=(Exception,))
        def detect_faces_with_retry(photo_data: bytes):
            """Detect faces with retry logic."""
            return face_detector.detect_faces(photo_data)
        
        try:
            faces = detect_faces_with_retry(photo_bytes)
            logger.info(f"Detected {len(faces)} faces in image {image_id}")
        except Exception as e:
            logger.error(f"Face detection failed for {image_id} after retries: {str(e)}")
            image.status = 'failed'
            db.commit()
            raise FaceDetectionFailedError(f"Face detection failed after retries: {str(e)}")
        
        # Store face embeddings in database
        if len(faces) > 0:
            for embedding, bbox, quality_score in faces:
                face = Face(
                    image_id=image.id,
                    event_id=image.event_id,
                    embedding=embedding.tolist(),
                    bbox=bbox,
                    quality_score=quality_score
                )
                db.add(face)
            
            # Update image status to indexed
            image.status = 'indexed'
            image.face_count = len(faces)
            image.indexed_at = datetime.utcnow()
            
            logger.info(f"Successfully indexed {len(faces)} faces for image {image_id}")
        else:
            # No faces detected
            image.status = 'no_faces'
            image.face_count = 0
            image.indexed_at = datetime.utcnow()
            
            logger.info(f"No faces detected in image {image_id}")
        
        # Commit changes
        db.commit()
        
        return {
            'image_id': image_id,
            'status': image.status,
            'face_count': image.face_count
        }
        
    except Exception as e:
        logger.error(f"Unexpected error processing image {image_id}: {str(e)}", exc_info=True)
        
        # Try to update status to failed
        if db:
            try:
                image = db.query(Image).filter(Image.id == uuid.UUID(image_id)).first()
                if image:
                    image.status = 'failed'
                    db.commit()
            except Exception:
                pass
        
        # Re-raise exception for RQ retry logic
        raise
        
    finally:
        if db and should_close_db:
            db.close()
