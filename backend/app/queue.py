"""RQ queue configuration and job management."""

import redis
from rq import Queue
from app.config import settings

# Import worker functions at module level so RQ can serialize them properly
from app.workers.face_indexer_compreface import index_photo_compreface
from app.workers.retention_policy import check_and_delete_expired_events

# Initialize Redis connection
redis_conn = redis.from_url(settings.redis_url)

# Create RQ queue for face indexing jobs
face_indexing_queue = Queue('face_indexing', connection=redis_conn)

# Create RQ queue for retention policy jobs
retention_queue = Queue('retention', connection=redis_conn)


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
        result_ttl='1h'
    )

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
