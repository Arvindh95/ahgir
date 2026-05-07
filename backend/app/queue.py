"""RQ queue configuration and job management."""

import logging
import redis
from rq import Queue, Retry
from app.config import settings

# Import worker functions at module level so RQ can serialize them properly
from app.workers.face_indexer_compreface import index_photo_compreface
from app.workers.retention_policy import check_and_delete_expired_events, process_overdue_subscriptions
from app.email import send_verification_email, send_password_reset_email

logger = logging.getLogger(__name__)

# Initialize Redis connection
redis_conn = redis.from_url(settings.redis_url)

# Create RQ queues
face_indexing_queue = Queue('face_indexing', connection=redis_conn)
retention_queue = Queue('retention', connection=redis_conn)
default_queue = Queue('default', connection=redis_conn)


def enqueue_face_indexing(image_id: str) -> str:
    """
    Enqueue a face indexing job for an image using CompreFace.

    Args:
        image_id: UUID string of the image to process

    Returns:
        Job ID string
    """
    job = face_indexing_queue.enqueue(
        index_photo_compreface,
        image_id,
        settings.compreface_api_key,
        job_timeout='10m',
        failure_ttl='1d',
        result_ttl='1h',
        retry=Retry(max=3, interval=[30, 120, 300])
    )

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
