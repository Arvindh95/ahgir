"""
Rate limiting service using Redis for distributed rate limiting.

Implements a sliding window algorithm to enforce scan rate limits per guest session.
"""

from datetime import datetime, timedelta
from typing import Optional
import redis
from fastapi import HTTPException, status
from app.config import settings

# Initialize Redis client
redis_client = redis.from_url(settings.redis_url, decode_responses=True)


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
        
        # Use Redis pipeline for atomic operations
        pipe = self.redis.pipeline()
        
        # Remove timestamps older than the window
        pipe.zremrangebyscore(key, 0, window_start.timestamp())
        
        # Count current timestamps in window
        pipe.zcard(key)
        
        # Execute pipeline
        results = pipe.execute()
        current_count = results[1]
        
        # Check if under limit
        if current_count < self.limit:
            # Add current timestamp
            self.redis.zadd(key, {now.isoformat(): now.timestamp()})
            
            # Set expiry on key (window + buffer)
            self.redis.expire(key, self.window_seconds + 3600)
            
            return True, None
        else:
            # Over limit - calculate retry-after
            # Get oldest timestamp in current window
            oldest_timestamps = self.redis.zrange(key, 0, 0, withscores=True)
            
            if oldest_timestamps:
                oldest_timestamp = oldest_timestamps[0][1]
                oldest_time = datetime.fromtimestamp(oldest_timestamp)
                retry_time = oldest_time + timedelta(hours=self.window_hours)
                retry_after_seconds = int((retry_time - now).total_seconds())
                
                # Ensure retry_after is at least 1 second
                retry_after_seconds = max(1, retry_after_seconds)
            else:
                # Fallback if no timestamps found
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
