"""Response cache using Upstash Redis."""
from upstash_redis import Redis
from typing import Any, Optional
import json
import asyncio


class SearchCache:
    """Simple Redis-based cache for search results."""

    def __init__(self, redis: Redis, default_ttl: int = 3600):
        self.redis = redis
        self.default_ttl = default_ttl

    def _get_sync(self, key: str) -> Optional[Any]:
        """Synchronous implementation."""
        data = self.redis.get(f"cache:{key}")
        if data:
            return json.loads(data)
        return None

    def _set_sync(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        """Synchronous implementation."""
        self.redis.set(
            f"cache:{key}",
            json.dumps(value),
            ex=ttl or self.default_ttl
        )

    def _delete_sync(self, key: str) -> None:
        """Synchronous implementation."""
        self.redis.delete(f"cache:{key}")

    async def get(self, key: str) -> Optional[Any]:
        """Get cached value by key."""
        return await asyncio.to_thread(self._get_sync, key)

    async def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        """Set cached value with TTL."""
        await asyncio.to_thread(self._set_sync, key, value, ttl)

    async def delete(self, key: str) -> None:
        """Delete cached value."""
        await asyncio.to_thread(self._delete_sync, key)