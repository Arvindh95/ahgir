"""CompreFace subject cleanup helpers."""
import logging
from typing import Iterable, Tuple

import httpx
from sqlalchemy.orm import Session

from app.config import settings, get_compreface_url
from app.models import Face

logger = logging.getLogger(__name__)


def _delete_subject_ids(subject_ids: Iterable[str], event_id) -> Tuple[int, int]:
    if not settings.compreface_api_key:
        return 0, 0

    deleted = 0
    failed = 0
    for sid in sorted(set(sid for sid in subject_ids if sid)):
        try:
            response = httpx.delete(
                f"{get_compreface_url()}/api/v1/recognition/faces",
                params={"subject": sid},
                headers={"x-api-key": settings.compreface_api_key},
                timeout=10.0,
            )
            if response.status_code in (200, 404):
                deleted += 1
            else:
                failed += 1
                logger.warning(
                    "Failed to delete CompreFace subject %s for event %s: HTTP %s %s",
                    sid,
                    event_id,
                    response.status_code,
                    response.text,
                )
        except Exception as e:
            failed += 1
            logger.warning(
                f"Failed to delete CompreFace subject {sid} for event {event_id}: {e}"
            )

    return deleted, failed


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

    deleted, failed = _delete_subject_ids(subject_ids, event_id)
    logger.info(
        f"Event {event_id}: deleted {deleted}/{len(set(subject_ids))} CompreFace subjects "
        f"({failed} failures)"
    )
    return deleted, failed
