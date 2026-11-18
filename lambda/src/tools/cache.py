"""Response cache using Upstash Redis."""
from upstash_redis import Redis
from typing import Any, Optional
import json


class SearchCache:
    """Simple Redis-based cache for search results."""

    def __init__(self, redis: Redis, default_ttl: int = 3600):
        self.redis = redis
        self.default_ttl = default_ttl

    async def get(self, key: str) -> Optional[Any]:
        """Get cached value by key."""
        data = await self.redis.get(f"cache:{key}")
        if data:
            return json.loads(data)
        return None

    async def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        """Set cached value with TTL."""
        await self.redis.set(
            f"cache:{key}",
            json.dumps(value),
            ex=ttl or self.default_ttl
        )

    async def delete(self, key: str) -> None:
        """Delete cached value."""
        await self.redis.delete(f"cache:{key}")