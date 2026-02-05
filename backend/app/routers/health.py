"""Health check endpoints for monitoring service status."""

from fastapi import APIRouter, status
from sqlalchemy import text
from minio.error import S3Error
import redis

from app.database import engine
from app.storage import storage_service
from app.rate_limiter import redis_client
from app.config import settings

router = APIRouter(tags=["health"])


@router.get("/health", status_code=status.HTTP_200_OK)
async def health_check():
    """
    Comprehensive health check endpoint.
    
    Checks connectivity to:
    - PostgreSQL database
    - MinIO object storage
    - Redis cache
    
    Returns:
        dict: Health status of all services
    """
    health_status = {
        "status": "healthy",
        "services": {
            "database": {"status": "unknown"},
            "minio": {"status": "unknown"},
            "redis": {"status": "unknown"}
        }
    }
    
    all_healthy = True
    
    # Check database connectivity
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        health_status["services"]["database"]["status"] = "healthy"
    except Exception as e:
        health_status["services"]["database"]["status"] = "unhealthy"
        health_status["services"]["database"]["error"] = str(e)
        all_healthy = False
    
    # Check MinIO connectivity
    try:
        # Try to check if bucket exists (this verifies connection)
        storage_service.client.bucket_exists(settings.minio_bucket)
        health_status["services"]["minio"]["status"] = "healthy"
    except S3Error as e:
        health_status["services"]["minio"]["status"] = "unhealthy"
        health_status["services"]["minio"]["error"] = str(e)
        all_healthy = False
    except Exception as e:
        health_status["services"]["minio"]["status"] = "unhealthy"
        health_status["services"]["minio"]["error"] = str(e)
        all_healthy = False
    
    # Check Redis connectivity
    try:
        redis_client.ping()
        health_status["services"]["redis"]["status"] = "healthy"
    except redis.RedisError as e:
        health_status["services"]["redis"]["status"] = "unhealthy"
        health_status["services"]["redis"]["error"] = str(e)
        all_healthy = False
    except Exception as e:
        health_status["services"]["redis"]["status"] = "unhealthy"
        health_status["services"]["redis"]["error"] = str(e)
        all_healthy = False
    
    # Set overall status
    if not all_healthy:
        health_status["status"] = "unhealthy"
    
    return health_status


@router.get("/health/debug/event/{event_slug}", status_code=status.HTTP_200_OK)
async def debug_event_faces(event_slug: str):
    """
    Debug endpoint to check face indexing status for an event.

    Returns counts of images and faces for the specified event.
    """
    from app.database import SessionLocal

    db = SessionLocal()
    try:
        # First, look up the event by slug to get the UUID
        event = db.execute(text("""
            SELECT id FROM events WHERE slug = :slug
        """), {"slug": event_slug}).fetchone()

        if not event:
            return {"error": f"Event with slug '{event_slug}' not found"}

        event_id = event.id

        # Get image counts by status
        image_stats = db.execute(text("""
            SELECT status, COUNT(*) as count
            FROM images
            WHERE event_id = :event_id
            GROUP BY status
        """), {"event_id": event_id}).fetchall()

        # Get face count
        face_count = db.execute(text("""
            SELECT COUNT(*) as count
            FROM faces
            WHERE event_id = :event_id
        """), {"event_id": event_id}).fetchone()

        # Get sample face embedding info
        sample_face = db.execute(text("""
            SELECT id, image_id, quality_score, array_length(bbox, 1) as bbox_len
            FROM faces
            WHERE event_id = :event_id
            LIMIT 1
        """), {"event_id": event_id}).fetchone()

        return {
            "event_slug": event_slug,
            "event_id": str(event_id),
            "image_stats": {row.status: row.count for row in image_stats},
            "total_faces": face_count.count if face_count else 0,
            "sample_face": {
                "id": str(sample_face.id),
                "image_id": str(sample_face.image_id),
                "quality_score": sample_face.quality_score,
                "bbox_length": sample_face.bbox_len
            } if sample_face else None
        }
    finally:
        db.close()


@router.post("/health/debug/reindex/{event_slug}", status_code=status.HTTP_200_OK)
async def reindex_event_images(event_slug: str, status_filter: str = "no_faces"):
    """
    Debug endpoint to re-trigger indexing for images in an event.

    Args:
        event_slug: The event slug to reindex
        status_filter: Only reindex images with this status (default: no_faces)

    Returns:
        dict: Number of images queued for reindexing
    """
    from app.database import SessionLocal
    from app.queue import enqueue_face_indexing

    db = SessionLocal()
    try:
        # First, look up the event by slug to get the UUID
        event = db.execute(text("""
            SELECT id FROM events WHERE slug = :slug
        """), {"slug": event_slug}).fetchone()

        if not event:
            return {"error": f"Event with slug '{event_slug}' not found"}

        event_id = event.id

        # Get images with the specified status
        images = db.execute(text("""
            SELECT id, filename
            FROM images
            WHERE event_id = :event_id AND status = :status
        """), {"event_id": event_id, "status": status_filter}).fetchall()

        # Reset status to pending and queue for reindexing
        queued = []
        for img in images:
            # Reset status to pending
            db.execute(text("""
                UPDATE images SET status = 'pending', face_count = 0, indexed_at = NULL
                WHERE id = :image_id
            """), {"image_id": img.id})

            # Delete any existing faces for this image
            db.execute(text("""
                DELETE FROM faces WHERE image_id = :image_id
            """), {"image_id": img.id})

            # Queue for reindexing
            enqueue_face_indexing(str(img.id))
            queued.append({"id": str(img.id), "filename": img.filename})

        db.commit()

        return {
            "event_slug": event_slug,
            "event_id": str(event_id),
            "status_filter": status_filter,
            "queued_count": len(queued),
            "queued_images": queued
        }
    finally:
        db.close()
