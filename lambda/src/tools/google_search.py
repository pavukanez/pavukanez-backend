"""DuckDuckGo Search tool for LangGraph agent (no API key required)."""
from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field, PrivateAttr
from typing import Optional, Type
import asyncio
import json
import hashlib
from datetime import datetime, timedelta

from ..config.settings import settings
from .rate_limiter import RateLimiter
from .cache import SearchCache


class DuckDuckGoSearchInput(BaseModel):
    """Input schema for DuckDuckGo Search tool."""
    query: str = Field(description="Search query string")
    num_results: int = Field(default=5, ge=1, le=10, description="Number of results to return")
    recency_days: Optional[int] = Field(default=None, description="Limit results to last N days")


class DuckDuckGoSearchTool(BaseTool):
    """LangChain-compatible tool for DuckDuckGo HTML scraping (no API key needed)."""

    name: str = "duckduckgo_search"
    description: str = (
        "Search the web for current information, news, facts, or answers to questions using DuckDuckGo. "
        "Use this when you need up-to-date information not in your training data. "
        "Returns structured results with title, URL, snippet, and source. No API key required."
    )
    args_schema: Type[BaseModel] = DuckDuckGoSearchInput

    # Private attributes for dependencies (not part of schema)
    _rate_limiter: RateLimiter = PrivateAttr()
    _cache: SearchCache = PrivateAttr()

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Initialize shared dependencies on first instantiation
        from upstash_redis import Redis
        redis = Redis(url=settings.upstash_url, token=settings.upstash_token)
        object.__setattr__(self, '_rate_limiter', RateLimiter(redis, limit=settings.search_rate_limit))
        object.__setattr__(self, '_cache', SearchCache(redis, default_ttl=settings.search_cache_ttl))

    @property
    def rate_limiter(self) -> RateLimiter:
        return self._rate_limiter

    @property
    def cache(self) -> SearchCache:
        return self._cache

    def _run(self, query: str, num_results: int = 5, recency_days: Optional[int] = None) -> str:
        """Synchronous wrapper for Lambda compatibility."""
        return asyncio.run(self._arun(query, num_results, recency_days))

    async def _arun(self, query: str, num_results: int = 5, recency_days: Optional[int] = None) -> str:
        # 1. Check rate limit
        if not await self.rate_limiter.check_limit("duckduckgo_search"):
            return json.dumps({"error": "Rate limit exceeded. Please try again later."})

        # 2. Check cache
        cache_key = self._cache_key(query, num_results, recency_days)
        cached = await self.cache.get(cache_key)
        if cached:
            return json.dumps(cached)

        # 3. Execute search
        try:
            results = await self._execute_search(query, num_results, recency_days)
        except Exception as e:
            return json.dumps({"error": f"Search failed: {str(e)}"})

        # 4. Format and cache
        formatted = self._format_results(results)
        await self.cache.set(cache_key, formatted, ttl=settings.search_cache_ttl)

        return json.dumps(formatted)

    def _cache_key(self, query: str, num_results: int, recency_days: Optional[int]) -> str:
        """Generate cache key from query parameters."""
        key = f"search:{hashlib.sha256(query.encode()).hexdigest()[:16]}:{num_results}:{recency_days or 0}"
        return key

    async def _execute_search(self, query: str, num_results: int, recency_days: Optional[int]) -> list:
        """Execute DuckDuckGo search using ddgs library."""
        from ddgs import DDGS
        
        # Build query with recency filter
        search_query = query
        if recency_days:
            # ddgs supports time filters: 'd' (day), 'w' (week), 'm' (month), 'y' (year)
            if recency_days <= 1:
                timelimit = 'd'
            elif recency_days <= 7:
                timelimit = 'w'
            elif recency_days <= 30:
                timelimit = 'm'
            else:
                timelimit = 'y'
        else:
            timelimit = None

        # Run search in thread pool since ddgs is synchronous
        loop = asyncio.get_event_loop()
        
        def _search():
            with DDGS() as ddgs:
                return list(ddgs.text(
                    query=search_query,
                    max_results=min(num_results, 10),
                    timelimit=timelimit,
                    region='wt-wt',  # Worldwide
                    safesearch='moderate'
                ))
        
        results = await loop.run_in_executor(None, _search)
        return results

    def _format_results(self, raw_results: list) -> list:
        """Format raw ddgs results into structured list."""
        return [
            {
                "title": item.get("title", ""),
                "url": item.get("href", ""),
                "snippet": item.get("body", ""),
                "source": "duckduckgo"
            }
            for item in raw_results
        ]