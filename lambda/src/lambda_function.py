import json
import os
from typing import Dict, Any, Optional

# Load settings early
from src.config.settings import settings
from src.agent.graph import graph
from src.agent.state import AgentState
from src.utils.streaming import stream_graph_response


# Deployment test marker - triggers GitHub Actions workflow
DEPLOY_TEST = True
DEPLOY_TEST_V2 = True
DEPLOY_TEST_V3 = True
DEPLOY_TEST_V4 = True
DEPLOY_TEST_V5 = True
DEPLOY_TEST_V6 = True
DEPLOY_TEST_V7_NO_AUD = True
DEPLOY_TEST_V8_FIXED_URL = True
DEPLOY_TEST_V9_WITH_AUD = True
DEPLOY_TEST_V10_DEBUG_TOKEN = True
DEPLOY_TEST_V11_FIXED_SUB_PATTERN = True
DEPLOY_TEST_V12_OIDC_CLIENT_ID = True
DEPLOY_TEST_V13_STATIC_CREDS = True


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """Main Lambda handler with LangGraph agent."""
    
    # Parse request body
    body = event.get("body", {})
    if isinstance(body, str):
        try:
            body = json.loads(body)
        except json.JSONDecodeError:
            return _error_response(400, "Invalid JSON in request body")
    
    query = body.get("query", "").strip()
    history = body.get("history", "").strip()
    stream = body.get("stream", False)
    request_id = event.get("requestContext", {}).get("requestId", "local")
    
    if not query:
        return _error_response(400, "Missing 'query' field")
    
    # Initial state
    initial_state: AgentState = {
        "messages": [{"role": "user", "content": query}],
        "query": query,
        "history": history,
        "stream": stream,
        "tool_call_count": 0,
        "max_tool_calls": settings.max_tool_calls,
        "request_id": request_id,
        "user_id": None,
    }
    
    try:
        if stream:
            return _streaming_response(initial_state, context)
        else:
            return _non_streaming_response(initial_state)
            
    except Exception as e:
        print(f"Error: {str(e)}")
        return _error_response(500, f"Internal server error: {str(e)}")


def _streaming_response(state: AgentState, context: Any) -> Dict[str, Any]:
    """Handle streaming response via Lambda response streaming."""
    # Check if response streaming is available
    response_stream = getattr(context, 'response_stream', None)
    
    if not response_stream:
        # Fallback: collect all and return
        return _non_streaming_response(state)
    
    # Write initial headers
    response_stream.write(json.dumps({
        "statusCode": 200,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "Content-Type",
            "Access-Control-Allow-Methods": "POST, OPTIONS"
        }
    }) + "\n")
    
    try:
        # Stream the graph
        import asyncio
        
        async def stream_and_write():
            async for chunk in stream_graph_response(state):
                response_stream.write(chunk)
        
        asyncio.run(stream_and_write())
        
    except Exception as e:
        print(f"Streaming error: {str(e)}")
        response_stream.write(json.dumps({"body": f"Error: {str(e)}", "isFinal": True}) + "\n")
    
    response_stream.end()
    return {}  # No return value for streaming


def _non_streaming_response(state: AgentState) -> Dict[str, Any]:
    """Execute graph and return final response."""
    result = graph.invoke(state)
    
    # Extract final AI message
    final_message = result["messages"][-1]
    response_text = final_message.content if hasattr(final_message, "content") else str(final_message)
    
    return {
        "statusCode": 200,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "Content-Type",
            "Access-Control-Allow-Methods": "POST, OPTIONS"
        },
        "body": json.dumps({
            "response": response_text,
            "model": settings.openrouter_model,
            "usage": {}
        })
    }


def _error_response(status: int, message: str) -> Dict[str, Any]:
    return {
        "statusCode": status,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps({"error": message})
    }
