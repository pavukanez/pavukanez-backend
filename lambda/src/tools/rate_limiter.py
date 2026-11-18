"""Rate limiter using Upstash Redis sorted sets (sliding window)."""
from upstash_redis import Redis
from typing import Optional
import time
import asyncio


class RateLimiter:
    """Sliding window rate limiter using Redis sorted sets."""

    def __init__(self, redis: Redis, limit: int = 30, window_seconds: int = 60):
        self.redis = redis
        self.limit = limit
        self.window = window_seconds

    def _check_limit_sync(self, key: str, custom_limit: Optional[int] = None) -> bool:
        """Synchronous implementation."""
        limit = custom_limit or self.limit
        now = time.time()
        window_start = now - self.window

        redis_key = f"ratelimit:{key}"

        # Remove expired entries
        self.redis.zremrangebyscore(redis_key, 0, window_start)

        # Count current requests in window
        current = self.redis.zcard(redis_key)

        if current >= limit:
            return False

        # Add current request with timestamp as score
        self.redis.zadd(redis_key, {str(now): now})
        self.redis.expire(redis_key, self.window + 1)

        return True

    async def check_limit(self, key: str, custom_limit: Optional[int] = None) -> bool:
        """
        Check if request is within rate limit.

        Args:
            key: Rate limit key (e.g., "google_search", "user:123")
            custom_limit: Override default limit for this check

        Returns:
            True if within limit, False if rate limited
        """
        return await asyncio.to_thread(self._check_limit_sync, key, custom_limit)