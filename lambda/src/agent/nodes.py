"""LangGraph agent nodes."""
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage
from typing import Literal
from .state import AgentState
from .prompts import SYSTEM_PROMPT
from ..config.settings import settings


def agent_node(state: AgentState) -> AgentState:
    """Main agent node - calls LLM with tools."""
    messages = state["messages"]

    # Add system prompt if not present
    if not any(isinstance(m, SystemMessage) for m in messages):
        messages = [SystemMessage(content=SYSTEM_PROMPT)] + messages

    # Add history context if provided
    if state.get("history") and not any("Previous context" in str(m.content) for m in messages):
        messages = [HumanMessage(content=f"Previous context: {state['history']}")] + messages

    # Call LLM (will be set via graph.py)
    from .graph import llm_with_tools
    response = llm_with_tools.invoke(messages)

    return {"messages": [response]}


def should_continue(state: AgentState) -> Literal["continue", "end"]:
    """Determine if agent should call tools or finish."""
    messages = state["messages"]
    last_message = messages[-1]

    # Check tool call count to prevent infinite loops
    tool_calls = state.get("tool_call_count", 0)
    if tool_calls >= state.get("max_tool_calls", 3):
        return "end"

    # Check if last message has tool calls
    if hasattr(last_message, "tool_calls") and last_message.tool_calls:
        return "continue"

    return "end"