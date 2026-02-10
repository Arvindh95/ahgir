"""Simple Redis cache for API responses."""

import json
import logging
from typing import Optional
import redis
from app.config import settings

logger = logging.getLogger(__name__)

_redis: Optional[redis.Redis] = None


def get_redis() -> redis.Redis:
    global _redis
    if _redis is None:
        _redis = redis.from_url(settings.redis_url, decode_responses=True)
    return _redis


def cache_get(key: str) -> Optional[dict]:
    """Get a cached value. Returns None on miss or error."""
    try:
        data = get_redis().get(key)
        if data:
            return json.loads(data)
    except Exception:
        logger.debug("Cache miss/error for %s", key)
    return None


def cache_set(key: str, value: dict, ttl_seconds: int = 60):
    """Cache a value with TTL. Fails silently."""
    try:
        get_redis().setex(key, ttl_seconds, json.dumps(value, default=str))
    except Exception:
        logger.debug("Cache set error for %s", key)


def cache_delete_pattern(pattern: str):
    """Delete all keys matching a pattern. Fails silently."""
    try:
        r = get_redis()
        cursor = 0
        while True:
            cursor, keys = r.scan(cursor, match=pattern, count=100)
            if keys:
                r.delete(*keys)
            if cursor == 0:
                break
    except Exception:
        logger.debug("Cache delete error for pattern %s", pattern)
