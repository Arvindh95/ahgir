"""CompreFace subject cleanup helpers."""
import logging
from typing import Tuple

import httpx
from sqlalchemy.orm import Session

from app.config import settings, get_compreface_url
from app.models import Face

logger = logging.getLogger(__name__)


def delete_compreface_subjects_for_event(db: Session, event_id) -> Tuple[int, int]:
    """Delete every CompreFace subject registered against ``event_id``.

    Returns ``(deleted, failed)``. No-op (and returns ``(0, 0)``) when
    ``COMPREFACE_API_KEY`` is unset.
    """
    if not settings.compreface_api_key:
        return 0, 0

    subject_ids = [
        sid for (sid,) in db.query(Face.compreface_subject_id)
        .filter(Face.event_id == event_id, Face.compreface_subject_id.isnot(None))
        .all()
    ]

    deleted = 0
    failed = 0
    for sid in subject_ids:
        try:
            httpx.delete(
                f"{get_compreface_url()}/api/v1/recognition/faces",
                params={"subject": sid},
                headers={"x-api-key": settings.compreface_api_key},
                timeout=10.0,
            )
            deleted += 1
        except Exception as e:
            failed += 1
            logger.warning(
                f"Failed to delete CompreFace subject {sid} for event {event_id}: {e}"
            )

    logger.info(
        f"Event {event_id}: deleted {deleted}/{len(subject_ids)} CompreFace subjects "
        f"({failed} failures)"
    )
    return deleted, failed
