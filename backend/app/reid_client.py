"""Re-ID sidecar HTTP client.

Tiny wrapper around the reid-api Flask service. Designed to fail soft:
any error condition (service down, timeout, missing model, bad image)
returns None rather than raising. Callers in the indexer and the scan
endpoint treat None as "no Re-ID signal available" and continue with
face-only matching.
"""
from __future__ import annotations

import logging
from typing import Optional

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


# Conservative request budget. The model is small (~80 ms CPU per inference)
# so any wait beyond a few seconds is the service being down, not slow.
# Indexing is throughput-bound — short timeout keeps the worker moving.
_TIMEOUT_SECONDS = 4.0


async def compute_embedding(image_bytes: bytes) -> Optional[list[float]]:
    """Return a 512-d L2-normalised Re-ID embedding for the given image bytes.

    Returns None on any failure. Callers MUST treat None as a fail-soft
    signal (write NULL into faces.reid_embedding at index time; skip the
    Re-ID gate for this probe at scan time).
    """
    if not image_bytes:
        return None
    if not settings.reid_enabled_indexing and not settings.reid_enabled_scan:
        # Neither pipeline wants Re-ID. Avoid the network call entirely.
        return None
    url = f"{settings.reid_api_url.rstrip('/')}/embed"
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT_SECONDS) as client:
            response = await client.post(
                url,
                files={"file": ("body.jpg", image_bytes, "image/jpeg")},
            )
    except httpx.TimeoutException:
        logger.warning("reid-api timeout after %.1fs (url=%s)", _TIMEOUT_SECONDS, url)
        return None
    except httpx.HTTPError as exc:
        logger.warning("reid-api request failed: %s (url=%s)", exc, url)
        return None
    except Exception as exc:
        # Defensive: never let an unexpected error bubble up to the worker.
        logger.warning("reid-api unexpected error: %s (url=%s)", exc, url)
        return None

    if response.status_code != 200:
        logger.warning(
            "reid-api %d response (url=%s, body=%s)",
            response.status_code,
            url,
            response.text[:200],
        )
        return None

    try:
        payload = response.json()
    except ValueError:
        logger.warning("reid-api non-JSON response (url=%s)", url)
        return None

    embedding = payload.get("embedding")
    if not isinstance(embedding, list) or not embedding:
        logger.warning("reid-api missing embedding key (url=%s)", url)
        return None
    if len(embedding) != 512:
        logger.warning(
            "reid-api returned unexpected embedding dim=%d (url=%s)",
            len(embedding),
            url,
        )
        return None

    return [float(v) for v in embedding]


async def healthcheck() -> bool:
    """Quick liveness probe — returns True only when the sidecar reports healthy.

    Used by the backend startup / health endpoints. Same fail-soft policy as
    compute_embedding: any error returns False.
    """
    url = f"{settings.reid_api_url.rstrip('/')}/healthcheck"
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            response = await client.get(url)
    except httpx.HTTPError:
        return False
    return response.status_code == 200
