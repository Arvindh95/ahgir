"""Background reindex task.

The owner-facing ``POST /events/{id}/reindex`` endpoint used to do the
heavy work inline:
  1. Load every Image + Face row for the event.
  2. Delete each CompreFace subject one-by-one via HTTP (10s timeout
     per call).
  3. Reset image statuses + delete face rows.
  4. Enqueue per-image face_indexing jobs.

For an event with several hundred photos that loop could take many
minutes and tie up an API worker. The endpoint sometimes timed out
before reaching the enqueue loop, leaving the event in a partially-
reset state.

This task moves the same work into the ``retention`` RQ queue. The
HTTP endpoint enqueues this task and returns immediately. Per-image
progress is already visible via the existing event status (the
frontend polls /events/{id}).
"""
import logging
import uuid
from typing import Optional

import httpx
from sqlalchemy.orm import Session

from app.config import get_compreface_url, settings
from app.database import SessionLocal
from app.event_status import invalidate_event_public_cache
from app.audit import log_action
from app.cache import cache_delete_pattern
from app.models import Event, Face, Image

logger = logging.getLogger(__name__)


def reindex_event_task(
    event_id: str,
    actor_user_id: Optional[str] = None,
    db: Session = None,
) -> dict:
    """Perform a full event reindex.

    Args:
        event_id: UUID string of the event to reindex.
        actor_user_id: UUID string of the operator who triggered the
            reindex. Recorded on the audit row.

    Returns:
        Dict with ``queued_count`` and per-step counts.
    """
    from app.queue import enqueue_face_indexing  # avoid circular import

    db_provided = db is not None
    if not db_provided:
        db = SessionLocal()

    try:
        try:
            event_uuid = uuid.UUID(event_id)
            actor_uuid = uuid.UUID(actor_user_id) if actor_user_id else None
        except (ValueError, TypeError):
            logger.error(f"reindex_event_task: invalid uuid event_id={event_id} actor={actor_user_id}")
            return {"error": "invalid uuids"}

        event = db.query(Event).filter(Event.id == event_uuid).first()
        if not event:
            logger.warning(f"reindex_event_task: event {event_uuid} no longer exists")
            return {"error": "event not found"}

        # Step 1: drop CompreFace subjects for every existing face.
        old_faces = db.query(Face).filter(Face.event_id == event_uuid).all()
        cf_deleted = 0
        cf_failed = 0
        if old_faces and settings.compreface_api_key:
            for face in old_faces:
                if not face.compreface_subject_id:
                    continue
                try:
                    resp = httpx.delete(
                        f"{get_compreface_url()}/api/v1/recognition/faces",
                        headers={"x-api-key": settings.compreface_api_key},
                        params={"subject": face.compreface_subject_id},
                        timeout=10.0,
                    )
                    if resp.status_code in (200, 404):
                        cf_deleted += 1
                    else:
                        cf_failed += 1
                except Exception as e:
                    cf_failed += 1
                    logger.warning(
                        f"reindex_event_task: failed to delete CompreFace subject "
                        f"{face.compreface_subject_id}: {e}"
                    )
            logger.info(
                f"reindex_event_task: CompreFace cleanup for event {event_uuid}: "
                f"deleted={cf_deleted} failed={cf_failed}"
            )

        # Step 2: bulk reset image statuses (one UPDATE instead of N).
        image_ids = [row.id for row in (
            db.query(Image.id).filter(Image.event_id == event_uuid).all()
        )]
        if image_ids:
            db.query(Image).filter(Image.id.in_(image_ids)).update(
                {
                    Image.status: "pending",
                    Image.face_count: 0,
                    Image.indexed_at: None,
                },
                synchronize_session=False,
            )

        # Step 3: bulk delete face rows.
        deleted_faces = db.query(Face).filter(Face.event_id == event_uuid).delete(
            synchronize_session=False
        )

        db.commit()

        # Step 4: invalidate guest-facing caches before any new
        # face_indexing job can produce results that race the cache.
        cache_delete_pattern(f"gallery:{event_uuid}:*")
        cache_delete_pattern(f"share:{event_uuid}:*")
        invalidate_event_public_cache(event)

        # Step 5: enqueue per-image face_indexing jobs.
        queued_count = 0
        for image_id in image_ids:
            try:
                enqueue_face_indexing(str(image_id))
                queued_count += 1
            except Exception as e:
                logger.error(
                    f"reindex_event_task: failed to enqueue image {image_id}: {e}"
                )

        # Audit the completion. The endpoint already wrote a "reindex_
        # requested" row before enqueueing this task; this row marks
        # the work as actually done.
        log_action(
            db=db,
            event_id=event_uuid,
            actor_type="admin" if actor_uuid else "system",
            actor_id=actor_uuid,
            action="reindex_completed",
            metadata={
                "queued_count": queued_count,
                "cf_deleted": cf_deleted,
                "cf_failed": cf_failed,
                "deleted_faces": deleted_faces,
                "image_count": len(image_ids),
            },
        )

        logger.info(
            f"reindex_event_task: event {event_uuid} done — "
            f"queued={queued_count} cf_deleted={cf_deleted} cf_failed={cf_failed} "
            f"deleted_faces={deleted_faces}"
        )
        return {
            "queued_count": queued_count,
            "cf_deleted": cf_deleted,
            "cf_failed": cf_failed,
            "deleted_faces": deleted_faces,
            "image_count": len(image_ids),
        }
    finally:
        if not db_provided:
            db.close()
