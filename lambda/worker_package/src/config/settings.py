"""Application settings (no pydantic dependency)."""
import os
from functools import lru_cache
from dataclasses import dataclass
from typing import Optional


@dataclass
class Settings:
    """Application settings loaded from environment variables."""

    # Required fields (no defaults)
    openrouter_api_key: str
    upstash_url: str
    upstash_token: str

    # Optional fields with defaults
    openrouter_model: str = "openrouter/auto"
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    search_rate_limit: int = 30
    search_cache_ttl: int = 3600
    search_max_results: int = 5
    max_tool_calls: int = 3

    # GitHub settings
    github_token: Optional[str] = None
    github_rate_limit: int = 100
    github_cache_ttl: int = 3600
    max_repo_size_mb: int = 100
    max_files_per_repo: int = 200

    @classmethod
    def from_env(cls) -> "Settings":
        """Create settings from environment variables."""
        return cls(
            openrouter_api_key=os.environ["OPENROUTER_API_KEY"],
            upstash_url=os.environ["UPSTASH_REDIS_REST_URL"],
            upstash_token=os.environ["UPSTASH_REDIS_REST_TOKEN"],
            openrouter_model=os.environ.get("OPENROUTER_MODEL", "openrouter/auto"),
            openrouter_base_url=os.environ.get("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"),
            search_rate_limit=int(os.environ.get("SEARCH_RATE_LIMIT", "30")),
            search_cache_ttl=int(os.environ.get("SEARCH_CACHE_TTL", "3600")),
            search_max_results=int(os.environ.get("SEARCH_MAX_RESULTS", "5")),
            max_tool_calls=int(os.environ.get("MAX_TOOL_CALLS", "3")),
            github_token=os.environ.get("GITHUB_TOKEN"),
            github_rate_limit=int(os.environ.get("GITHUB_RATE_LIMIT", "100")),
            github_cache_ttl=int(os.environ.get("GITHUB_CACHE_TTL", "3600")),
            max_repo_size_mb=int(os.environ.get("MAX_REPO_SIZE_MB", "100")),
            max_files_per_repo=int(os.environ.get("MAX_FILES_PER_REPO", "200")),
        )


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings.from_env()


settings = get_settings()