"""RQ queue configuration and job management."""

import logging
from typing import Optional

import redis
from rq import Queue, Retry
from app.config import settings

# Import worker functions at module level so RQ can serialize them properly
from app.workers.face_indexer_compreface import index_photo_compreface
from app.workers.retention_policy import (
    check_and_delete_expired_events,
    process_overdue_subscriptions,
    drain_storage_cleanups,
)
from app.email import send_verification_email, send_password_reset_email

logger = logging.getLogger(__name__)

# Initialize Redis connection
redis_conn = redis.from_url(settings.redis_url)

# Create RQ queues
face_indexing_queue = Queue('face_indexing', connection=redis_conn)
retention_queue = Queue('retention', connection=redis_conn)
default_queue = Queue('default', connection=redis_conn)


class JobAlreadyQueued(Exception):
    """Raised when enqueue_face_indexing sees the deterministic job_id is
    already present in the queue / registries. Callers can catch this to
    treat duplicate enqueue attempts as a no-op rather than an error.
    """


def enqueue_face_indexing(image_id: str) -> str:
    """
    Enqueue a face indexing job for an image using CompreFace.

    The job id is deterministic (``index:{image_id}``) so two callers
    racing on the same image — typically the upload path plus the
    daily stale-pending reconciler — don't both stuff the queue with
    duplicate jobs. Within the ``failure_ttl`` / ``result_ttl`` window
    after a previous run, RQ rejects the duplicate. Outside that
    window the prior hash has aged out and a fresh enqueue is allowed,
    which is what we want for genuinely re-running an image days
    later.

    Args:
        image_id: UUID string of the image to process

    Returns:
        Job ID string

    Raises:
        JobAlreadyQueued: a job with this deterministic id is already
            queued / started / deferred / scheduled. Callers should
            usually log + skip rather than escalate.
    """
    job_id = f"index:{image_id}"
    try:
        job = face_indexing_queue.enqueue(
            index_photo_compreface,
            image_id,
            settings.compreface_api_key,
            job_id=job_id,
            job_timeout='10m',
            failure_ttl='1d',
            result_ttl='1h',
            retry=Retry(max=3, interval=[30, 120, 300])
        )
    except Exception as e:
        # RQ versions differ on the exception class for duplicate job_id.
        # Matching on the message is portable enough; if the error is
        # unrelated, re-raise so the caller still sees the real failure.
        message = str(e).lower()
        if "already exists" in message or "duplicate" in message:
            raise JobAlreadyQueued(
                f"Face-indexing job for image {image_id} already queued"
            ) from e
        raise

    return job.id


def enqueue_email(to_email: str, verify_url: str) -> str:
    """
    Enqueue a verification email to be sent in the background.

    Args:
        to_email: Recipient email address
        verify_url: Verification URL to include in the email

    Returns:
        Job ID string
    """
    job = default_queue.enqueue(
        send_verification_email,
        to_email,
        verify_url,
        job_timeout='2m',
        failure_ttl='1d',
        result_ttl='1h'
    )
    logger.info(f"Enqueued verification email job {job.id} for {to_email}")
    return job.id


def enqueue_password_reset_email(to_email: str, reset_url: str) -> str:
    """Enqueue a password reset email to be sent in the background."""
    job = default_queue.enqueue(
        send_password_reset_email,
        to_email,
        reset_url,
        job_timeout='2m',
        failure_ttl='1d',
        result_ttl='1h'
    )
    logger.info(f"Enqueued password reset email job {job.id} for {to_email}")
    return job.id


def get_failed_jobs() -> list:
    """Get failed jobs from all queue registries."""
    from rq.job import Job
    from rq.registry import FailedJobRegistry

    results = []
    for queue in [face_indexing_queue, retention_queue, default_queue]:
        registry = FailedJobRegistry(queue=queue)
        for job_id in registry.get_job_ids():
            try:
                job = Job.fetch(job_id, connection=redis_conn)
                results.append({
                    "id": job.id,
                    "queue": queue.name,
                    "func_name": job.func_name if job.func_name else "unknown",
                    "enqueued_at": job.enqueued_at.isoformat() if job.enqueued_at else None,
                    "ended_at": job.ended_at.isoformat() if job.ended_at else None,
                    "error": job.exc_info.strip() if job.exc_info else None,
                })
            except Exception:
                results.append({"id": job_id, "queue": queue.name, "error": "Could not fetch job details"})
    return results


def retry_failed_job(job_id: str) -> str:
    """Requeue a failed job."""
    from rq.job import Job

    job = Job.fetch(job_id, connection=redis_conn)
    job.requeue()
    return job.id


def enqueue_retention_check() -> str:
    """
    Enqueue a retention policy check job.

    This job checks for expired events and deletes them.
    Should be scheduled to run periodically (e.g., daily).

    Returns:
        Job ID string
    """
    job = retention_queue.enqueue(
        check_and_delete_expired_events,
        job_timeout='30m',  # 30 minute timeout
        failure_ttl='7d',   # Keep failed jobs for 7 days
        result_ttl='7d'     # Keep results for 7 days
    )

    return job.id


def enqueue_subscription_processor() -> str:
    """Enqueue the subscription past-due grace-period downgrade job."""
    job = retention_queue.enqueue(
        process_overdue_subscriptions,
        job_timeout='10m',
        failure_ttl='7d',
        result_ttl='7d',
    )
    return job.id


def enqueue_storage_cleanup_drain() -> str:
    """Enqueue the storage-cleanup tombstone drainer.

    The drainer pulls up to N due tombstones, retries each (MinIO /
    CompreFace), and either marks them done or backs off for the next
    cycle. Cheap to run frequently — empty tombstone table is a single
    indexed query.
    """
    job = retention_queue.enqueue(
        drain_storage_cleanups,
        job_timeout='10m',
        failure_ttl='7d',
        result_ttl='7d',
    )
    return job.id


def enqueue_event_reindex(event_id: str, actor_user_id: Optional[str] = None) -> str:
    """Enqueue an asynchronous full-event reindex.

    The HTTP /events/{id}/reindex endpoint used to do the work inline,
    which could exceed the HTTP timeout on large events. This helper
    pushes the same work onto the retention queue (lower priority than
    face_indexing, so an in-progress reindex doesn't starve the
    per-image jobs the reindex itself enqueues).
    """
    from typing import Optional as _Optional  # local alias for the def signature
    from app.workers.reindex_event import reindex_event_task
    job = retention_queue.enqueue(
        reindex_event_task,
        event_id,
        actor_user_id,
        job_id=f"reindex:{event_id}",
        job_timeout="30m",
        failure_ttl="7d",
        result_ttl="7d",
    )
    return job.id


def enqueue_reid_backfill(event_id: Optional[str] = None) -> str:
    """Enqueue a Phase 1 Re-ID backfill of NULL faces.reid_embedding rows.

    Scoped to one event when ``event_id`` is given, else every event. Runs on
    the retention queue (lower priority than face_indexing) so a long backfill
    never starves live per-image indexing. The job id is deterministic per
    scope (``reid_backfill:{event|all}``) so an operator double-tapping the
    admin button doesn't stack two concurrent backfills over the same rows.
    """
    from app.workers.reid_backfill import backfill_reid_embeddings
    job = retention_queue.enqueue(
        backfill_reid_embeddings,
        event_id,
        job_id=f"reid_backfill:{event_id or 'all'}",
        job_timeout="2h",
        failure_ttl="7d",
        result_ttl="7d",
    )
    return job.id


def enqueue_stale_pending_reconciler() -> str:
    """Enqueue the stale-pending-images reconciler.

    Backstop for the rare upload path where the Image row is committed but
    the face-indexing enqueue silently failed (worker crashed between commit
    and enqueue, etc). Picks up images stuck at status='pending' for more
    than 30 minutes and re-enqueues them.
    """
    from app.workers.retention_policy import requeue_stale_pending_indexing
    job = retention_queue.enqueue(
        requeue_stale_pending_indexing,
        job_timeout='10m',
        failure_ttl='7d',
        result_ttl='7d',
    )
    return job.id
