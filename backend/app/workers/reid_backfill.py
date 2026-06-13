"""Phase 1 Re-ID backfill worker.

Populates ``faces.reid_embedding`` for rows left NULL — legacy faces indexed
before Phase 0 existed, plus any face whose embedding failed fail-soft at
index time (sidecar down, timeout, degenerate crop). The scan-time Re-ID gate
(Phase 3) treats a NULL embedding as "no Re-ID signal — fall back to face-only
for this candidate", so every NULL we fill tightens the family-lookalike gate
for that face.

Idempotent by construction: the worker only ever reads and writes rows where
``reid_embedding IS NULL``, so re-running it is safe and simply picks up
whatever is still NULL (e.g. faces skipped on a previous pass because the
sidecar was down). Monitor progress by watching the NULL count trend to zero:

    SELECT count(*) FROM faces WHERE reid_embedding IS NULL;

Strategy — page over IMAGES, not faces. A single event photo can hold many
faces; downloading the original once per image and cropping every NULL face
from it in memory avoids re-fetching the same MinIO object N times. The crop
geometry comes from the shared ``body_crop.derive_upper_body_bbox`` — the SAME
function the indexer and the scan probe use, so backfilled embeddings land in
the identical region of the Re-ID manifold as freshly-indexed ones. A mismatch
here would silently wreck recall.
"""
from __future__ import annotations

import asyncio
import io
import json
import logging
import uuid
from typing import Optional

from PIL import ImageOps
from sqlalchemy.orm import Session

from app.body_crop import derive_upper_body_bbox
from app.config import settings
from app.database import SessionLocal
from app.models import Face, Image
from app.reid_client import compute_embedding as compute_reid_embedding
from app.storage import storage_service
from app.utils.image_safety import safe_open as safe_open_image

logger = logging.getLogger(__name__)

# Sentinel returned by derive_upper_body_bbox when the face bbox is degenerate
# or has no torso room (face touching the frame edge). A 1x1 crop carries no
# body signal, so we skip Re-ID for the face and leave it NULL rather than
# poison the column with a meaningless embedding.
_DEGENERATE_BBOX = (0, 0, 1, 1)


def _run_async(coro):
    """Run an async coroutine from this sync RQ worker.

    Mirrors the helper in face_indexer_compreface so the backfill shares the
    indexer's event-loop handling exactly.
    """
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop.run_until_complete(coro)


def _embed_faces_for_image(db: Session, image: Image, img) -> dict:
    """Fill reid_embedding for every NULL face on one already-opened image.

    ``img`` is the EXIF-corrected PIL image. Commits are the caller's job so a
    crash mid-image doesn't leave a half-written set behind without a barrier.
    """
    counts = {"written": 0, "failed": 0, "degenerate": 0}

    null_faces = (
        db.query(Face)
        .filter(Face.image_id == image.id, Face.reid_embedding.is_(None))
        .all()
    )
    for face in null_faces:
        bbox = face.bbox  # [x_min, y_min, x_max, y_max] as stored by the indexer
        body_bbox = derive_upper_body_bbox(bbox, img.width, img.height)
        if tuple(body_bbox) == _DEGENERATE_BBOX:
            counts["degenerate"] += 1
            continue
        try:
            crop = img.crop(body_bbox)
            if crop.mode in ("RGBA", "LA", "P"):
                crop = crop.convert("RGB")
            buf = io.BytesIO()
            crop.save(buf, format="JPEG", quality=90)
            embedding = _run_async(compute_reid_embedding(buf.getvalue()))
        except Exception as exc:
            # Never let one bad crop abort the whole image. Leave NULL — a
            # later re-run retries it.
            logger.warning(
                "reid backfill: crop/embed failed for face %s (image %s): %s",
                face.id, image.id, exc,
            )
            embedding = None

        if embedding is None:
            # Sidecar down / model missing / fail-soft. Stays NULL; the next
            # run will retry once the sidecar is healthy.
            counts["failed"] += 1
            continue

        face.reid_embedding = embedding
        counts["written"] += 1

    return counts


def backfill_reid_embeddings(
    event_id: Optional[str] = None,
    max_images: Optional[int] = None,
    db: Optional[Session] = None,
) -> dict:
    """Backfill NULL Re-ID embeddings, optionally scoped to one event.

    Args:
        event_id: UUID string. When given, only that event's faces are
            backfilled; otherwise every event with NULL faces is processed.
        max_images: Optional cap on the number of images processed this run
            (useful for incremental / rate-limited backfills). NOTE: when set,
            images beyond the cap are silently left for a later run — the
            return dict's ``images_remaining_capped`` flag surfaces that.
        db: Optional session (tests inject one); otherwise a fresh
            SessionLocal is opened and closed here.

    Returns:
        Dict summary of work done — safe to log and to assert on in tests.
    """
    if not settings.reid_enabled_indexing and not settings.reid_enabled_scan:
        # compute_embedding short-circuits to None in this state, so every
        # face would be counted "failed" for no reason. Bail loudly instead.
        logger.warning(
            "reid backfill: both reid_enabled_indexing and reid_enabled_scan "
            "are False — nothing to do (the sidecar call would be skipped)."
        )
        return {"skipped": True, "reason": "reid disabled"}

    db_provided = db is not None
    if not db_provided:
        db = SessionLocal()

    event_uuid: Optional[uuid.UUID] = None
    if event_id:
        try:
            event_uuid = uuid.UUID(event_id)
        except (ValueError, TypeError):
            logger.error("reid backfill: invalid event_id=%s", event_id)
            if not db_provided:
                db.close()
            return {"error": "invalid event_id"}

    try:
        # Distinct images that still have at least one NULL-embedding face.
        # Filling embeddings shrinks this set, so the work is monotonic and
        # bounded — we materialise the candidate list up front (UUIDs are
        # cheap) to avoid an offset-paging loop that could spin forever on
        # images whose faces all fail (e.g. sidecar permanently down).
        q = (
            db.query(Image)
            .join(Face, Face.image_id == Image.id)
            .filter(Face.reid_embedding.is_(None))
        )
        if event_uuid is not None:
            q = q.filter(Image.event_id == event_uuid)
        q = q.distinct().order_by(Image.id)

        images = q.all()
        total_candidates = len(images)
        capped = False
        if max_images is not None and total_candidates > max_images:
            images = images[:max_images]
            capped = True

        totals = {
            "images_total": total_candidates,
            "images_processed": 0,
            "images_missing": 0,
            "faces_written": 0,
            "faces_failed": 0,
            "faces_degenerate": 0,
            "images_remaining_capped": capped,
        }

        for image in images:
            # Download + EXIF-correct exactly as the indexer did, so the stored
            # face bbox lines up with this image's pixel grid.
            try:
                photo_bytes = storage_service.get_photo(
                    event_id=image.event_id,
                    image_id=image.id,
                    photo_type="original",
                )
            except FileNotFoundError:
                logger.warning(
                    "reid backfill: original missing for image %s — skipping",
                    image.id,
                )
                totals["images_missing"] += 1
                continue
            except Exception as exc:
                logger.warning(
                    "reid backfill: download failed for image %s: %s",
                    image.id, exc,
                )
                totals["images_missing"] += 1
                continue

            try:
                pil_img = safe_open_image(photo_bytes)
                pil_img = ImageOps.exif_transpose(pil_img)
                if pil_img.mode in ("RGBA", "LA", "P"):
                    pil_img = pil_img.convert("RGB")
            except Exception as exc:
                logger.warning(
                    "reid backfill: decode failed for image %s: %s",
                    image.id, exc,
                )
                totals["images_missing"] += 1
                continue

            counts = _embed_faces_for_image(db, image, pil_img)
            totals["faces_written"] += counts["written"]
            totals["faces_failed"] += counts["failed"]
            totals["faces_degenerate"] += counts["degenerate"]
            totals["images_processed"] += 1

            # Commit per image so a long backfill is durable and restartable.
            db.commit()

        logger.info(
            "reid backfill done (event=%s): %s",
            event_id or "ALL", totals,
        )
        return totals
    except Exception:
        db.rollback()
        raise
    finally:
        if not db_provided:
            db.close()


def _main() -> None:
    """CLI entry point: ``python -m app.workers.reid_backfill [--event UUID]``."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Backfill NULL faces.reid_embedding via the reid-api sidecar."
    )
    parser.add_argument(
        "--event",
        default=None,
        help="Restrict to a single event UUID. Omit to backfill every event.",
    )
    parser.add_argument(
        "--max-images",
        type=int,
        default=None,
        help="Cap images processed this run (incremental backfill).",
    )
    args = parser.parse_args()

    result = backfill_reid_embeddings(event_id=args.event, max_images=args.max_images)
    print(json.dumps(result, default=str))


if __name__ == "__main__":
    _main()
