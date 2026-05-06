"""Signed photo streaming route.

The signed URL itself is the bearer credential — no JWT required, so plain <img src=...>
works in browsers. Signature is HMAC over (event_id, image_id, photo_type, expires) with
a 15-minute default expiry.
"""

import logging
import uuid
from io import BytesIO
from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import StreamingResponse

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
):
    """Stream photo bytes from MinIO if the signature is valid and not expired."""
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
