"""Health check endpoints for monitoring service status."""

import os
import time
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, status
from sqlalchemy import text
from minio.error import S3Error
import redis

from app.database import engine
from app.storage import storage_service
from app.rate_limiter import redis_client
from app.config import settings
from app.compreface_client import CompreFaceClient
from app.routers.admin import get_superadmin_user

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
            "redis": {"status": "unknown"},
            "compreface": {"status": "unknown"}
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
    
    # Check CompreFace connectivity
    try:
        client = CompreFaceClient()
        is_healthy = await client.health_check()
        health_status["services"]["compreface"]["status"] = "healthy" if is_healthy else "unhealthy"
        if not is_healthy:
            all_healthy = False
    except Exception as e:
        health_status["services"]["compreface"]["status"] = "unhealthy"
        health_status["services"]["compreface"]["error"] = str(e)
        all_healthy = False

    # Set overall status
    if not all_healthy:
        health_status["status"] = "unhealthy"

    # In production, strip raw error strings — they can leak internal hostnames,
    # connection strings, or stack details. Status verdict alone is enough for LB probes.
    if settings.environment.lower() == "production":
        for svc in health_status["services"].values():
            svc.pop("error", None)

    return health_status


@router.get("/health/load", status_code=status.HTTP_200_OK)
async def load_metrics(_superadmin=Depends(get_superadmin_user)):
    """Operator-only load snapshot: queue depth, backlog, latency, system load.

    Use this to spot capacity pressure before users feel it. Returns a 0-100
    load_score so you can graph one number; sub-fields explain *why* the score
    is what it is.

    Score thresholds (rule of thumb):
      <30  green    — comfortably idle
      30-60 yellow  — warm, watch trending
      60-85 orange  — under pressure, consider scaling
      >85  red      — degraded, scale immediately

    Compose of score:
      queue depth >50         → +30
      oldest pending >10 min  → +25
      CompreFace p95 >500ms   → +20
      load_avg >0.7*cores     → +25
    """
    from app.queue import face_indexing_queue, retention_queue, default_queue

    out = {
        "checked_at": datetime.utcnow().isoformat() + "Z",
        "queues": {},
        "indexing_backlog": {},
        "compreface": {},
        "redis": {},
        "system": {},
        "scan_rate": {},
        "load_score": 0,
        "verdict": "green",
    }

    score = 0

    # 1. RQ queue depths
    try:
        q_face = face_indexing_queue.count
        q_retention = retention_queue.count
        q_default = default_queue.count
        out["queues"] = {
            "face_indexing": q_face,
            "retention": q_retention,
            "default": q_default,
        }
        if q_face > 50:
            score += 30
        elif q_face > 20:
            score += 15
    except Exception as e:
        out["queues"]["error"] = str(e)

    # 2. Image indexing backlog (pending + how stale)
    try:
        with engine.connect() as conn:
            row = conn.execute(text("""
                SELECT
                    COUNT(*) FILTER (WHERE status = 'pending') AS pending,
                    COUNT(*) FILTER (WHERE status = 'failed')  AS failed,
                    EXTRACT(EPOCH FROM (NOW() - MIN(uploaded_at) FILTER (WHERE status = 'pending'))) AS oldest_pending_age_seconds
                FROM images
            """)).fetchone()
            pending = int(row.pending or 0)
            failed = int(row.failed or 0)
            oldest_age = float(row.oldest_pending_age_seconds or 0)
            out["indexing_backlog"] = {
                "pending": pending,
                "failed": failed,
                "oldest_pending_age_minutes": round(oldest_age / 60, 1),
            }
            if oldest_age > 600:  # 10 min
                score += 25
            elif oldest_age > 300:  # 5 min
                score += 12
    except Exception as e:
        out["indexing_backlog"]["error"] = str(e)

    # 3. CompreFace ping latency
    try:
        t0 = time.perf_counter()
        client = CompreFaceClient()
        is_healthy = await client.health_check()
        latency_ms = round((time.perf_counter() - t0) * 1000, 1)
        out["compreface"] = {"healthy": is_healthy, "ping_ms": latency_ms}
        if latency_ms > 500:
            score += 20
        elif latency_ms > 200:
            score += 10
    except Exception as e:
        out["compreface"]["error"] = str(e)

    # 4. Redis info
    try:
        info = redis_client.info(section="memory")
        clients_info = redis_client.info(section="clients")
        out["redis"] = {
            "used_memory_mb": round(info.get("used_memory", 0) / 1024 / 1024, 1),
            "connected_clients": clients_info.get("connected_clients", 0),
        }
    except Exception as e:
        out["redis"]["error"] = str(e)

    # 5. System load average + cores
    try:
        load1, load5, load15 = os.getloadavg()
        cores = os.cpu_count() or 1
        out["system"] = {
            "load_avg_1m": round(load1, 2),
            "load_avg_5m": round(load5, 2),
            "load_avg_15m": round(load15, 2),
            "cpu_cores": cores,
            "load_per_core_1m": round(load1 / cores, 2),
        }
        if load1 > cores * 0.85:
            score += 25
        elif load1 > cores * 0.65:
            score += 12
    except Exception as e:
        out["system"]["error"] = str(e)

    # 6. Recent scan rate (5 min window)
    try:
        with engine.connect() as conn:
            row = conn.execute(text("""
                SELECT COUNT(*) AS scans
                FROM audit_logs
                WHERE action = 'scan'
                  AND timestamp > NOW() - INTERVAL '5 minutes'
            """)).fetchone()
            out["scan_rate"] = {"scans_last_5min": int(row.scans or 0)}
    except Exception as e:
        out["scan_rate"]["error"] = str(e)

    # Final score + verdict
    out["load_score"] = min(100, score)
    if score < 30:
        out["verdict"] = "green"
    elif score < 60:
        out["verdict"] = "yellow"
    elif score < 85:
        out["verdict"] = "orange"
    else:
        out["verdict"] = "red"

    return out


@router.get("/health/debug/event/{event_slug}", status_code=status.HTTP_200_OK)
async def debug_event_faces(event_slug: str, _superadmin=Depends(get_superadmin_user)):
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
async def reindex_event_images(event_slug: str, status_filter: str = "no_faces", _superadmin=Depends(get_superadmin_user)):
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
