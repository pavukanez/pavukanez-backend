"""Tests for DuckDuckGo Search tool."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import json
from src.tools.google_search import DuckDuckGoSearchTool
from src.tools.rate_limiter import RateLimiter
from src.tools.cache import SearchCache


@pytest.fixture
def mock_redis():
    return AsyncMock()


@pytest.fixture
def mock_rate_limiter(mock_redis):
    limiter = RateLimiter(mock_redis, limit=5, window_seconds=60)
    limiter.check_limit = AsyncMock(return_value=True)
    return limiter


@pytest.fixture
def mock_cache(mock_redis):
    cache = SearchCache(mock_redis, default_ttl=3600)
    cache.get = AsyncMock(return_value=None)
    cache.set = AsyncMock()
    return cache


@pytest.fixture
def duckduckgo_search_tool(mock_rate_limiter, mock_cache):
    """Create DuckDuckGoSearchTool with mocked dependencies."""
    # Patch the __init__ to inject mocks
    original_init = DuckDuckGoSearchTool.__init__
    
    def mock_init(self, **kwargs):
        original_init(self, **kwargs)
        # Override private attributes
        object.__setattr__(self, '_rate_limiter', mock_rate_limiter)
        object.__setattr__(self, '_cache', mock_cache)
    
    with patch.object(DuckDuckGoSearchTool, '__init__', mock_init):
        tool = DuckDuckGoSearchTool()
        return tool


@pytest.mark.asyncio
async def test_duckduckgo_search_rate_limited(duckduckgo_search_tool, mock_rate_limiter):
    """Test that rate limited requests return error."""
    mock_rate_limiter.check_limit.return_value = False

    result = await duckduckgo_search_tool._arun("test query")
    data = json.loads(result)
    assert "error" in data
    assert "Rate limit exceeded" in data["error"]


@pytest.mark.asyncio
async def test_duckduckgo_search_cache_hit(duckduckgo_search_tool, mock_cache):
    """Test that cached results are returned."""
    mock_cache.get.return_value = [{"title": "Cached", "url": "http://cached.com", "snippet": "cached", "source": "duckduckgo"}]

    result = await duckduckgo_search_tool._arun("test query")
    data = json.loads(result)
    assert len(data) == 1
    assert data[0]["title"] == "Cached"
    mock_cache.get.assert_called_once()


@pytest.mark.asyncio
async def test_duckduckgo_search_execute_search(duckduckgo_search_tool):
    """Test search execution with mocked ddgs."""
    mock_results = [
        {"title": "Result 1", "href": "http://r1.com", "body": "Snippet 1"},
        {"title": "Result 2", "href": "http://r2.com", "body": "Snippet 2"},
    ]

    with patch('ddgs.DDGS') as mock_ddgs_class:
        mock_ddgs = MagicMock()
        mock_ddgs.text.return_value = mock_results
        mock_ddgs_class.return_value.__enter__.return_value = mock_ddgs

        result = await duckduckgo_search_tool._execute_search("test query", 2, None)

        assert result == mock_results
        mock_ddgs.text.assert_called_once_with(
            query="test query",
            max_results=2,
            timelimit=None,
            region='wt-wt',
            safesearch='moderate'
        )


@pytest.mark.asyncio
async def test_duckduckgo_search_execute_search_with_recency(duckduckgo_search_tool):
    """Test search execution with recency filter."""
    mock_results = [
        {"title": "Result 1", "href": "http://r1.com", "body": "Snippet 1"},
    ]

    with patch('ddgs.DDGS') as mock_ddgs_class:
        mock_ddgs = MagicMock()
        mock_ddgs.text.return_value = mock_results
        mock_ddgs_class.return_value.__enter__.return_value = mock_ddgs

        result = await duckduckgo_search_tool._execute_search("test query", 1, 3)  # 3 days

        assert result == mock_results
        mock_ddgs.text.assert_called_once_with(
            query="test query",
            max_results=1,
            timelimit='w',  # 3 days -> week
            region='wt-wt',
            safesearch='moderate'
        )


@pytest.mark.asyncio
async def test_duckduckgo_search_format_results(duckduckgo_search_tool):
    """Test result formatting."""
    raw_results = [
        {"title": "Title 1", "href": "http://link1.com", "body": "Snippet 1"},
        {"title": "Title 2", "href": "http://link2.com", "body": "Snippet 2"},
    ]

    formatted = duckduckgo_search_tool._format_results(raw_results)

    assert len(formatted) == 2
    assert formatted[0]["title"] == "Title 1"
    assert formatted[0]["url"] == "http://link1.com"
    assert formatted[0]["snippet"] == "Snippet 1"
    assert formatted[0]["source"] == "duckduckgo"