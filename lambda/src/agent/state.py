"""Agent state schema for LangGraph."""
from typing import TypedDict, List, Optional, Annotated
from langgraph.graph.message import add_messages
from langchain_core.messages import BaseMessage


class AgentState(TypedDict):
    """State schema for the LangGraph agent."""
    messages: Annotated[List[BaseMessage], add_messages]
    query: str
    history: str
    stream: bool
    # Tool-related
    tool_call_count: int
    max_tool_calls: int
    # Metadata
    request_id: str
    user_id: Optional[str]