"""Streaming utilities for Lambda response streaming."""
import json
from typing import AsyncGenerator, Dict, Any
from ..agent.graph import graph
from ..agent.state import AgentState


async def stream_graph_response(state: AgentState) -> AsyncGenerator[str, None]:
    """Stream LangGraph response as NDJSON chunks."""
    # Stream the graph execution
    async for chunk in graph.astream(state, stream_mode="messages"):
        if chunk:
            # chunk is (message, metadata)
            message = chunk[0]
            if hasattr(message, 'content') and message.content:
                yield json.dumps({"body": message.content}) + "\n"

    # Final chunk
    yield json.dumps({"body": "", "isFinal": True}) + "\n"


def format_sse_chunk(data: dict) -> str:
    """Format data as Server-Sent Events chunk."""
    return f"data: {json.dumps(data)}\n\n"