"""LangGraph StateGraph definition."""
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode
from langchain_openai import ChatOpenAI
from typing import Literal

from .state import AgentState
from .nodes import agent_node, should_continue
from ..tools.google_search import DuckDuckGoSearchTool
from ..config.settings import settings


# Initialize LLM (OpenRouter compatible via OpenAI client)
llm = ChatOpenAI(
    model=settings.openrouter_model,
    api_key=settings.openrouter_api_key,
    base_url=settings.openrouter_base_url,
    temperature=0.7,
    streaming=True,
)

# Initialize DuckDuckGo Search tool
duckduckgo_search_tool = DuckDuckGoSearchTool()

tools = [duckduckgo_search_tool]
llm_with_tools = llm.bind_tools(tools)

# ToolNode for LangGraph
tool_node = ToolNode(tools)


# Build graph
workflow = StateGraph(AgentState)

# Nodes
workflow.add_node("agent", agent_node)
workflow.add_node("tools", tool_node)

# Edges
workflow.set_entry_point("agent")
workflow.add_conditional_edges(
    "agent",
    should_continue,
    {"continue": "tools", "end": END}
)
workflow.add_edge("tools", "agent")

# Compile
graph = workflow.compile()