"""Tests for search cache."""
import pytest
from unittest.mock import AsyncMock
from src.tools.cache import SearchCache


@pytest.fixture
def mock_redis():
    return AsyncMock()


@pytest.fixture
def cache(mock_redis):
    return SearchCache(mock_redis, default_ttl=3600)


@pytest.mark.asyncio
async def test_cache_get_hit(cache, mock_redis):
    """Test cache get returns value on hit."""
    mock_redis.get.return_value = '{"title": "Test", "url": "http://example.com"}'

    result = await cache.get("test_key")
    assert result == {"title": "Test", "url": "http://example.com"}
    mock_redis.get.assert_called_once_with("cache:test_key")


@pytest.mark.asyncio
async def test_cache_get_miss(cache, mock_redis):
    """Test cache get returns None on miss."""
    mock_redis.get.return_value = None

    result = await cache.get("test_key")
    assert result is None


@pytest.mark.asyncio
async def test_cache_set(cache, mock_redis):
    """Test cache set stores value with TTL."""
    mock_redis.set.return_value = None

    await cache.set("test_key", {"title": "Test"}, ttl=1800)

    mock_redis.set.assert_called_once()
    args, kwargs = mock_redis.set.call_args
    assert args[0] == "cache:test_key"
    assert args[1] == '{"title": "Test"}'
    assert kwargs.get("ex") == 1800


@pytest.mark.asyncio
async def test_cache_delete(cache, mock_redis):
    """Test cache delete removes key."""
    mock_redis.delete.return_value = None

    await cache.delete("test_key")

    mock_redis.delete.assert_called_once_with("cache:test_key")