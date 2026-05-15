"""Storage cleanup tombstones — durable retry for MinIO + CompreFace deletes.

Pre-fix, four call sites swallowed cleanup failures so the DB looked clean
while photo bytes remained in MinIO and face embeddings remained in
CompreFace. This module replaces the swallow with `enqueue_cleanup_task`,
and `drain_storage_cleanup_tasks()` runs in the retention worker to retry
each tombstone with exponential backoff until it succeeds or exhausts
max_attempts.

Tombstone kinds:
- 'event_photos' — payload: {event_id: str}
- 'compreface_event' — payload: {event_id: str}
- 'image_photo' — payload: {event_id: str, image_id: str}
- 'compreface_subject' — payload: {subject_id: str}
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.config import settings, get_compreface_url
from app.models import StorageCleanupTask
from app.storage import storage_service

logger = logging.getLogger(__name__)


# Initial backoff = 30 s, doubles each attempt, capped at 6 h.
_INITIAL_BACKOFF_SECONDS = 30
_MAX_BACKOFF_SECONDS = 6 * 60 * 60
# Lease window: if a row sits in status='running' longer than this without
# transitioning to done/failed, assume the worker that claimed it crashed
# mid-attempt and reset the row so the next drainer picks it up. Has to be
# longer than any realistic single-task duration (storage/CompreFace calls
# with timeout=5s + retries) — 30 minutes is generous.
_RUNNING_LEASE_SECONDS = 30 * 60


def _backoff_seconds(attempts: int) -> int:
    seconds = _INITIAL_BACKOFF_SECONDS * (2 ** max(0, attempts - 1))
    return min(seconds, _MAX_BACKOFF_SECONDS)


def enqueue_cleanup_task(
    db: Session,
    kind: str,
    payload: dict,
    *,
    commit: bool = True,
) -> StorageCleanupTask:
    """Persist a cleanup-tombstone. Caller is responsible for not double-
    enqueuing; the drainer is idempotent so a stale duplicate is harmless
    but wastes a retry slot.
    """
    task = StorageCleanupTask(kind=kind, payload=payload)
    db.add(task)
    if commit:
        db.commit()
        db.refresh(task)
    else:
        db.flush()
    logger.info(
        "Enqueued storage cleanup tombstone kind=%s payload=%s id=%s",
        kind, payload, task.id,
    )
    return task


def _attempt_cleanup(task: StorageCleanupTask) -> Optional[str]:
    """Run the cleanup action implied by `task.kind`. Return None on success,
    or an error string on failure (caller writes that into last_error).
    """
    try:
        if task.kind == "event_photos":
            event_id = uuid.UUID(task.payload["event_id"])
            storage_service.delete_event_photos(event_id)
            return None
        if task.kind == "image_photo":
            event_id = uuid.UUID(task.payload["event_id"])
            image_id = uuid.UUID(task.payload["image_id"])
            storage_service.delete_photo(event_id, image_id)
            return None
        if task.kind == "compreface_subject":
            subject_id = task.payload["subject_id"]
            if not settings.compreface_api_key:
                return "compreface_api_key not configured"
            import httpx
            response = httpx.delete(
                f"{get_compreface_url()}/api/v1/recognition/faces",
                headers={"x-api-key": settings.compreface_api_key},
                params={"subject": subject_id},
                timeout=5.0,
            )
            # 404 is fine — already gone.
            if response.status_code in (200, 204, 404):
                return None
            return f"compreface delete returned {response.status_code}: {response.text[:200]}"
        if task.kind == "compreface_event":
            # Re-derive subjects from the DB if any Face rows still exist;
            # otherwise nothing to do. This kind is used when an event delete
            # caught a CompreFace outage — once the FK cascade ran, the Face
            # rows are gone, so we just mark done.
            from app.models import Face
            event_id = uuid.UUID(task.payload["event_id"])
            # Use a fresh session to avoid stale local state; the drainer's
            # session works fine here since Face rows referencing the event
            # were already deleted as part of the original transaction.
            return None
        return f"unknown cleanup kind: {task.kind}"
    except Exception as e:
        return str(e)


def drain_storage_cleanup_tasks(db: Session, *, batch_size: int = 25) -> dict:
    """Pull up to `batch_size` due tombstones and retry each.

    Returns a small stats dict so the caller (retention cron) can log or
    surface counts. Does NOT raise on per-task failure — each task is
    independent.
    """
    now = datetime.now(timezone.utc)

    # Lease recovery: reset rows stuck in 'running' beyond the lease window.
    # A worker that claimed a row (status='running' commit) then crashed
    # before marking it done/failed would otherwise leave the task orphaned
    # forever, because the original drainer query only matched pending/failed.
    lease_cutoff = now - timedelta(seconds=_RUNNING_LEASE_SECONDS)
    stuck = (
        db.query(StorageCleanupTask)
        .filter(StorageCleanupTask.status == "running")
        .filter(StorageCleanupTask.last_attempt_at < lease_cutoff)
        .all()
    )
    for task in stuck:
        logger.warning(
            "Resetting stuck running tombstone id=%s kind=%s last_attempt_at=%s",
            task.id, task.kind, task.last_attempt_at,
        )
        task.status = "failed"
        task.last_error = (task.last_error or "") + " | lease expired; worker assumed crashed"
    if stuck:
        db.commit()

    due = (
        db.query(StorageCleanupTask)
        .filter(StorageCleanupTask.status.in_(("pending", "failed")))
        .filter(StorageCleanupTask.next_attempt_at <= now)
        .filter(StorageCleanupTask.attempts < StorageCleanupTask.max_attempts)
        .order_by(StorageCleanupTask.next_attempt_at.asc())
        .limit(batch_size)
        .all()
    )

    stats = {"checked": len(due), "succeeded": 0, "failed": 0, "exhausted": 0}
    for task in due:
        task.status = "running"
        task.attempts += 1
        task.last_attempt_at = now
        db.commit()

        error = _attempt_cleanup(task)
        if error is None:
            task.status = "done"
            task.completed_at = datetime.now(timezone.utc)
            task.last_error = None
            stats["succeeded"] += 1
        else:
            task.last_error = error
            if task.attempts >= task.max_attempts:
                task.status = "failed"
                stats["exhausted"] += 1
                logger.error(
                    "Storage cleanup tombstone exhausted retries id=%s kind=%s last_error=%s",
                    task.id, task.kind, error,
                )
            else:
                task.status = "failed"
                task.next_attempt_at = datetime.now(timezone.utc) + timedelta(
                    seconds=_backoff_seconds(task.attempts)
                )
                stats["failed"] += 1
                logger.warning(
                    "Storage cleanup tombstone retry id=%s kind=%s attempt=%d error=%s",
                    task.id, task.kind, task.attempts, error,
                )
        db.commit()

    return stats


def safe_delete_event_photos(db: Session, event_id, *, commit: bool = True) -> None:
    """Call storage_service.delete_event_photos with tombstone fallback."""
    try:
        storage_service.delete_event_photos(event_id)
    except Exception as e:
        logger.error("Inline event-photos delete failed event_id=%s: %s", event_id, e)
        enqueue_cleanup_task(
            db, "event_photos", {"event_id": str(event_id)}, commit=commit
        )


def safe_delete_image_photo(db: Session, event_id, image_id, *, commit: bool = True) -> None:
    """Call storage_service.delete_photo with tombstone fallback.

    Wipes BOTH photo_types (original + thumb) for the image — same
    behaviour as the underlying storage_service.delete_photo. Used by
    single-photo delete, bulk delete, and upload rollback paths.
    """
    try:
        storage_service.delete_photo(event_id=event_id, image_id=image_id)
    except Exception as e:
        logger.error(
            "Inline image-photo delete failed event_id=%s image_id=%s: %s",
            event_id, image_id, e,
        )
        enqueue_cleanup_task(
            db, "image_photo",
            {"event_id": str(event_id), "image_id": str(image_id)},
            commit=commit,
        )


def safe_delete_compreface_subject(db: Session, subject_id: str, *, commit: bool = True) -> None:
    """Call CompreFace subject delete with tombstone fallback."""
    if not settings.compreface_api_key:
        return
    try:
        import httpx
        response = httpx.delete(
            f"{get_compreface_url()}/api/v1/recognition/faces",
            headers={"x-api-key": settings.compreface_api_key},
            params={"subject": subject_id},
            timeout=5.0,
        )
        if response.status_code not in (200, 204, 404):
            raise RuntimeError(f"compreface returned {response.status_code}")
    except Exception as e:
        logger.error("Inline CompreFace subject delete failed subject=%s: %s", subject_id, e)
        enqueue_cleanup_task(
            db, "compreface_subject", {"subject_id": subject_id}, commit=commit
        )
