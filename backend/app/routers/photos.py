"""Signed photo streaming route.

The signed URL itself is the bearer credential — no JWT required, so plain <img src=...>
works in browsers. Signature is HMAC over (event_id, image_id, photo_type, expires) with
a 15-minute default expiry.
"""

import logging
import uuid
from io import BytesIO
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Event, Image
from app.storage import storage_service, verify_signed_url

logger = logging.getLogger(__name__)
router = APIRouter(tags=["photos"])


@router.get("/photos/{event_id}/{image_id}/{photo_type}")
async def get_photo_signed(
    event_id: str,
    image_id: str,
    photo_type: str,
    expires: int = Query(...),
    sig: str = Query(...),
    db: Session = Depends(get_db),
):
    """Stream photo bytes from MinIO if the signature is valid AND the
    event is still serving guests AND the image is in a guest-visible
    state.

    Pre-fix this route accepted any unexpired signature without
    re-checking event/image state, so a URL minted before an event
    froze/expired kept streaming bytes for the full 15-minute signature
    window. The DB check below closes that window: as soon as the
    photographer freezes / deletes / marks-non-public, the next request
    returns 404 even if the signature is still valid.
    """
    if not verify_signed_url(event_id, image_id, photo_type, expires, sig):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid or expired photo URL",
        )

    try:
        event_uuid = uuid.UUID(event_id)
        image_uuid = uuid.UUID(image_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid event_id or image_id format",
        )

    # Live state check: deny if the event has been frozen / expired /
    # deleted, or if the image has been deleted or moved out of the
    # guest-visible states. Cheap (PK + indexed-event_id lookup).
    event = db.query(Event).filter(Event.id == event_uuid).first()
    if not event or event.status != 'active':
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Photo not found")

    # Covers are event-scoped (one per event) and use event_id as a
    # sentinel in the image_id slot — see generate_signed_cover_url.
    # They don't have a row in the images table, so skip the Image
    # status lookup for cover requests. The event-active check above
    # is sufficient gating: as soon as the event is frozen / expired,
    # the cover stops serving too.
    if photo_type != "cover":
        image = (
            db.query(Image.id)
            .filter(
                Image.id == image_uuid,
                Image.event_id == event_uuid,
                Image.status.in_(('indexed', 'no_faces')),
            )
            .first()
        )
        if not image:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Photo not found")

    try:
        photo_bytes = storage_service.get_photo(event_uuid, image_uuid, photo_type)
    except FileNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Photo not found")
    except Exception as e:
        logger.error(f"Failed to fetch photo {image_id}: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Storage error")

    headers = {
        # Browser may cache for the URL's lifetime; once URL expires the browser must
        # re-fetch a fresh signed URL anyway. private=do not let CDN/proxies cache.
        "Cache-Control": "private, max-age=900",
        "Content-Disposition": f'inline; filename="{image_id}.jpg"',
    }
    return StreamingResponse(BytesIO(photo_bytes), media_type="image/jpeg", headers=headers)
