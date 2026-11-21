"""Tests for agent graph."""
import pytest
from unittest.mock import MagicMock, patch
import json
import httpx
from src.agent.graph import invoke_agent, SYSTEM_PROMPT


@pytest.fixture
def mock_httpx_client():
    """Mock httpx client for OpenRouter API."""
    with patch('httpx.Client') as mock_client_class:
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        yield mock_client


def test_system_prompt_contains_daniel():
    """Test that system prompt contains Daniel's info."""
    assert "Daniel Pham" in SYSTEM_PROMPT
    assert "Backend & Cloud Infrastructure Engineer" in SYSTEM_PROMPT
    assert "GitHub repositories" in SYSTEM_PROMPT


def test_system_prompt_contains_github_tools():
    """Test that system prompt mentions GitHub repo tools."""
    assert "github_repo_fetch_tree" in SYSTEM_PROMPT
    assert "github_repo_fetch_files" in SYSTEM_PROMPT


def test_invoke_agent_with_simple_query(mock_httpx_client):
    """Test invoke_agent handles simple query without tools."""
    # Mock the HTTP response
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "choices": [{
            "message": {
                "content": "Hello! I'm Daniel's agent.",
                "role": "assistant"
            }
        }]
    }
    mock_httpx_client.post.return_value = mock_response
    
    result = invoke_agent("Hello", "", max_tool_calls=3)
    
    assert "Hello" in result or "Daniel" in result


def test_invoke_agent_handles_error():
    """Test invoke_agent raises exception on API errors."""
    with patch('src.agent.graph.httpx.Client') as mock_client_class:
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal server error"
        mock_client.post.return_value = mock_response
        
        with pytest.raises(Exception) as exc_info:
            invoke_agent("Hello", "", max_tool_calls=3)
        
    assert "OpenRouter API error: 500" in str(exc_info.value)