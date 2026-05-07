"""
Rate limiting service using Redis for distributed rate limiting.

Implements a sliding window algorithm to enforce scan rate limits per guest session.
The check + add is performed by a Redis-side Lua script so concurrent requests
cannot all observe count<limit and then all add themselves past the cap.
"""

from datetime import datetime, timedelta
from typing import Optional
import uuid
import redis
from fastapi import HTTPException, status
from app.config import settings

# Initialize Redis client
redis_client = redis.from_url(settings.redis_url, decode_responses=True)


# Atomic check-and-add Lua script.
# KEYS[1]: rate-limit zset key
# ARGV[1]: now (epoch seconds, float)
# ARGV[2]: window_start (epoch seconds, float) — anything older is pruned
# ARGV[3]: limit (int)
# ARGV[4]: member (unique string for this request)
# ARGV[5]: expire_seconds (int) — TTL on the key
# Returns: { allowed (1/0), oldest_timestamp_in_window (or 0 if allowed/empty) }
RATE_LIMIT_LUA = """
local key = KEYS[1]
local now = tonumber(ARGV[1])
local window_start = tonumber(ARGV[2])
local limit = tonumber(ARGV[3])
local member = ARGV[4]
local expire_seconds = tonumber(ARGV[5])

redis.call('ZREMRANGEBYSCORE', key, 0, window_start)
local count = redis.call('ZCARD', key)

if count >= limit then
    local oldest = redis.call('ZRANGE', key, 0, 0, 'WITHSCORES')
    if #oldest >= 2 then
        return {0, oldest[2]}
    end
    return {0, '0'}
end

redis.call('ZADD', key, now, member)
redis.call('EXPIRE', key, expire_seconds)
return {1, '0'}
"""

# Lazily-registered SHA so reconnects (e.g., redis restart) auto-recover.
_LUA_SHA: Optional[str] = None


def _run_rate_limit(client: redis.Redis, key: str, now: float, window_start: float,
                    limit: int, member: str, expire_seconds: int) -> tuple[int, float]:
    """Run the atomic rate-limit script. Falls back to register+retry on NOSCRIPT."""
    global _LUA_SHA
    args = [now, window_start, limit, member, expire_seconds]
    try:
        if _LUA_SHA is None:
            _LUA_SHA = client.script_load(RATE_LIMIT_LUA)
        result = client.evalsha(_LUA_SHA, 1, key, *args)
    except redis.exceptions.NoScriptError:
        # Redis was restarted or evicted the script. Reload and retry.
        _LUA_SHA = client.script_load(RATE_LIMIT_LUA)
        result = client.evalsha(_LUA_SHA, 1, key, *args)
    allowed = int(result[0])
    oldest = float(result[1])
    return allowed, oldest


class RateLimiter:
    """
    Rate limiter using Redis sliding window algorithm.
    
    Tracks scan counts per session and enforces configurable limits.
    """
    
    def __init__(
        self,
        redis_client: redis.Redis,
        limit: int = None,
        window_hours: int = None
    ):
        """
        Initialize rate limiter.
        
        Args:
            redis_client: Redis client instance
            limit: Maximum number of scans allowed per window (default from settings)
            window_hours: Time window in hours (default from settings)
        """
        self.redis = redis_client
        self.limit = limit or settings.scan_rate_limit
        self.window_hours = window_hours or settings.scan_rate_window_hours
        self.window_seconds = self.window_hours * 3600
    
    def _get_key(self, session_id: str, action: str = "scan") -> str:
        """Generate Redis key for session and action."""
        return f"rate_limit:{action}:{session_id}"
    
    def check_rate_limit(self, session_id: str, action: str = "scan") -> tuple[bool, Optional[int]]:
        """
        Check if the session has exceeded the rate limit.
        
        Uses sliding window algorithm:
        1. Remove timestamps older than the window
        2. Count remaining timestamps
        3. If under limit, allow and add new timestamp
        4. If over limit, deny and calculate retry-after
        
        Args:
            session_id: Guest session ID
            action: Action being rate limited (default: "scan")
        
        Returns:
            Tuple of (allowed: bool, retry_after_seconds: Optional[int])
            - If allowed=True, retry_after_seconds is None
            - If allowed=False, retry_after_seconds indicates when to retry
        """
        key = self._get_key(session_id, action)
        now = datetime.utcnow()
        window_start = now - timedelta(hours=self.window_hours)
        now_ts = now.timestamp()
        window_start_ts = window_start.timestamp()

        # Atomic check + add via Lua. Without this, concurrent requests can
        # all observe count < limit and then each add their own entry,
        # blowing past the cap. The script does prune + count + (conditional)
        # add + expire as a single Redis operation.
        member = f"{now_ts}-{uuid.uuid4().hex}"
        allowed, oldest_ts = _run_rate_limit(
            self.redis,
            key,
            now_ts,
            window_start_ts,
            self.limit,
            member,
            self.window_seconds + 3600,
        )

        if allowed == 1:
            return True, None

        # Over limit — compute retry-after from the oldest entry in the window.
        if oldest_ts > 0:
            retry_time = datetime.fromtimestamp(oldest_ts) + timedelta(hours=self.window_hours)
            retry_after_seconds = max(1, int((retry_time - now).total_seconds()))
        else:
            retry_after_seconds = self.window_seconds
        return False, retry_after_seconds
    
    def enforce_rate_limit(self, session_id: str, action: str = "scan") -> None:
        """
        Enforce rate limit and raise HTTPException if exceeded.
        
        Args:
            session_id: Guest session ID
            action: Action being rate limited (default: "scan")
        
        Raises:
            HTTPException: 429 Too Many Requests if rate limit exceeded
        """
        allowed, retry_after = self.check_rate_limit(session_id, action)
        
        if not allowed:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Rate limit exceeded. Maximum {self.limit} {action}s per {self.window_hours} hour(s).",
                headers={"Retry-After": str(retry_after)}
            )
    
    def get_current_count(self, session_id: str, action: str = "scan") -> int:
        """
        Get current count of actions in the window.
        
        Args:
            session_id: Guest session ID
            action: Action being counted
        
        Returns:
            Number of actions in current window
        """
        key = self._get_key(session_id, action)
        now = datetime.utcnow()
        window_start = now - timedelta(hours=self.window_hours)
        
        # Remove old timestamps
        self.redis.zremrangebyscore(key, 0, window_start.timestamp())
        
        # Return count
        return self.redis.zcard(key)
    
    def reset_limit(self, session_id: str, action: str = "scan") -> None:
        """
        Reset rate limit for a session (useful for testing).
        
        Args:
            session_id: Guest session ID
            action: Action to reset
        """
        key = self._get_key(session_id, action)
        self.redis.delete(key)


# Global rate limiter instances
rate_limiter = RateLimiter(redis_client)
auth_rate_limiter = RateLimiter(redis_client, limit=settings.auth_rate_limit, window_hours=settings.auth_rate_window_hours)
share_rate_limiter = RateLimiter(redis_client, limit=settings.share_rate_limit, window_hours=settings.share_rate_window_hours)
event_passcode_rate_limiter = RateLimiter(redis_client, limit=settings.event_passcode_rate_limit, window_hours=settings.event_passcode_rate_window_hours)
