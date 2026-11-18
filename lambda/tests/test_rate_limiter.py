"""Tests for rate limiter."""
import pytest
from unittest.mock import MagicMock
from src.tools.rate_limiter import RateLimiter


@pytest.fixture
def mock_redis():
    return MagicMock()


@pytest.fixture
def rate_limiter(mock_redis):
    return RateLimiter(mock_redis, limit=5, window_seconds=60)


@pytest.mark.asyncio
async def test_rate_limiter_allows_under_limit(rate_limiter, mock_redis):
    """Test that requests under limit are allowed."""
    mock_redis.zcard.return_value = 3
    mock_redis.zremrangebyscore.return_value = None
    mock_redis.zadd.return_value = None
    mock_redis.expire.return_value = None

    result = await rate_limiter.check_limit("test")
    assert result is True
    mock_redis.zadd.assert_called_once()


@pytest.mark.asyncio
async def test_rate_limiter_blocks_over_limit(rate_limiter, mock_redis):
    """Test that requests over limit are blocked."""
    mock_redis.zcard.return_value = 10
    mock_redis.zremrangebyscore.return_value = None

    result = await rate_limiter.check_limit("test")
    assert result is False
    mock_redis.zadd.assert_not_called()


@pytest.mark.asyncio
async def test_rate_limiter_custom_limit(rate_limiter, mock_redis):
    """Test rate limiter with custom limit."""
    mock_redis.zcard.return_value = 3
    mock_redis.zremrangebyscore.return_value = None
    mock_redis.zadd.return_value = None
    mock_redis.expire.return_value = None

    result = await rate_limiter.check_limit("test", custom_limit=10)
    assert result is True