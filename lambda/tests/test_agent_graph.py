"""Tests for LangGraph agent."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from src.agent.state import AgentState
from src.agent.nodes import agent_node, should_continue
from src.agent.prompts import SYSTEM_PROMPT
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage


@pytest.fixture
def mock_llm_with_tools():
    """Mock LLM with tools."""
    mock_llm = MagicMock()
    mock_response = AIMessage(content="Test response")
    mock_response.tool_calls = []
    mock_llm.invoke.return_value = mock_response
    return mock_llm


@pytest.fixture
def sample_state():
    """Create a sample agent state."""
    return AgentState(
        messages=[HumanMessage(content="Hello")],
        query="Hello",
        history="",
        stream=False,
        tool_call_count=0,
        max_tool_calls=3,
        request_id="test-123",
        user_id=None,
    )


def test_agent_node_adds_system_prompt(sample_state, mock_llm_with_tools):
    """Test that agent node adds system prompt if missing."""
    with patch('src.agent.graph.llm_with_tools', mock_llm_with_tools):
        result = agent_node(sample_state)

        # Check system prompt was added
        call_args = mock_llm_with_tools.invoke.call_args[0][0]
        assert any(isinstance(m, SystemMessage) and "Daniel" in m.content for m in call_args)
        assert len(result["messages"]) == 1


def test_agent_node_uses_existing_system_prompt(mock_llm_with_tools):
    """Test that agent node doesn't duplicate system prompt."""
    state = AgentState(
        messages=[
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(content="Hello")
        ],
        query="Hello",
        history="",
        stream=False,
        tool_call_count=0,
        max_tool_calls=3,
        request_id="test-123",
        user_id=None,
    )

    with patch('src.agent.graph.llm_with_tools', mock_llm_with_tools):
        result = agent_node(state)

        call_args = mock_llm_with_tools.invoke.call_args[0][0]
        # Should have only one system message
        system_count = sum(1 for m in call_args if isinstance(m, SystemMessage) and "Daniel" in m.content)
        assert system_count == 1


def test_should_continue_no_tool_calls(sample_state):
    """Test should_continue returns 'end' when no tool calls."""
    mock_msg = AIMessage(content="Hi there!")
    mock_msg.tool_calls = []

    sample_state["messages"] = [
        HumanMessage(content="Hello"),
        mock_msg
    ]

    result = should_continue(sample_state)
    assert result == "end"


def test_should_continue_with_tool_calls(sample_state):
    """Test should_continue returns 'continue' when tool calls present."""
    mock_msg = AIMessage(content="")
    mock_msg.tool_calls = [{"name": "google_search", "args": {"query": "test"}}]

    sample_state["messages"] = [
        HumanMessage(content="Hello"),
        mock_msg
    ]

    result = should_continue(sample_state)
    assert result == "continue"


def test_should_continue_max_tool_calls_reached(sample_state):
    """Test should_continue returns 'end' when max tool calls reached."""
    mock_msg = AIMessage(content="")
    mock_msg.tool_calls = [{"name": "google_search", "args": {"query": "test"}}]

    sample_state["messages"] = [
        HumanMessage(content="Hello"),
        mock_msg
    ]
    sample_state["tool_call_count"] = 3
    sample_state["max_tool_calls"] = 3

    result = should_continue(sample_state)
    assert result == "end"