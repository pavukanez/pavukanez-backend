"""Application settings using Pydantic."""
import os
from pydantic import BaseModel
from functools import lru_cache


class Settings(BaseModel):
    """Application settings loaded from environment variables."""

    # OpenRouter
    openrouter_api_key: str
    openrouter_model: str = "openrouter/auto"
    openrouter_base_url: str = "https://openrouter.ai/api/v1"

    # Upstash Redis
    upstash_url: str
    upstash_token: str

    # Search settings
    search_rate_limit: int = 30
    search_cache_ttl: int = 3600
    search_max_results: int = 5

    # Agent settings
    max_tool_calls: int = 3

    @classmethod
    def from_env(cls) -> "Settings":
        """Create settings from environment variables."""
        return cls(
            openrouter_api_key=os.environ["OPENROUTER_API_KEY"],
            openrouter_model=os.environ.get("OPENROUTER_MODEL", "openrouter/auto"),
            openrouter_base_url=os.environ.get("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"),
            upstash_url=os.environ["UPSTASH_REDIS_REST_URL"],
            upstash_token=os.environ["UPSTASH_REDIS_REST_TOKEN"],
            search_rate_limit=int(os.environ.get("SEARCH_RATE_LIMIT", "30")),
            search_cache_ttl=int(os.environ.get("SEARCH_CACHE_TTL", "3600")),
            search_max_results=int(os.environ.get("SEARCH_MAX_RESULTS", "5")),
            max_tool_calls=int(os.environ.get("MAX_TOOL_CALLS", "3")),
        )


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings.from_env()


settings = get_settings()