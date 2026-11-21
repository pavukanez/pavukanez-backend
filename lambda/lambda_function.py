import json
import os
import sys
from typing import Dict, Any, Optional

# Add the current directory to Python path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Load settings early
from src.config.settings import settings
from src.agent.graph import invoke_agent, invoke_agent_streaming


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
    """Main Lambda handler with simple agent."""
    
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
    
    try:
        if stream:
            return _streaming_response(query, history, context)
        else:
            return _non_streaming_response(query, history)
            
    except Exception as e:
        print(f"Error: {str(e)}")
        return _error_response(500, f"Internal server error: {str(e)}")


def _streaming_response(query: str, history: str, context: Any) -> Dict[str, Any]:
    """Handle streaming response via Lambda response streaming."""
    # Check if response streaming is available
    response_stream = getattr(context, 'response_stream', None)
    
    if not response_stream:
        # Fallback: collect all and return
        print("WARNING: response_stream not available, falling back to non-streaming")
        return _non_streaming_response(query, history)
    
    print(f"=== STREAMING START: {query[:100]}... ===")
    
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
    print("Initial headers written")
    
    try:
        # Use true streaming from OpenRouter
        import asyncio
        
        async def stream_tokens():
            token_count = 0
            print("Starting invoke_agent_streaming...")
            async for token in invoke_agent_streaming(query, history):
                token_count += 1
                if token_count % 10 == 1:
                    print(f"Streamed {token_count} tokens...")
                response_stream.write(json.dumps({"body": token}) + "\n")
                if token_count == 1:
                    print("First token written to stream")
            
            print(f"Streaming complete: {token_count} tokens total")
        
        print("Running asyncio.run...")
        asyncio.run(stream_tokens())
        print("asyncio.run completed")
        
        response_stream.write(json.dumps({"body": "", "isFinal": True}) + "\n")
        print("Final chunk sent")
        
    except Exception as e:
        import traceback
        print(f"Streaming error: {str(e)}")
        print(traceback.format_exc())
        response_stream.write(json.dumps({"body": f"Error: {str(e)}", "isFinal": True}) + "\n")
    
    response_stream.end()
    print("=== STREAMING END ===")
    return {}  # No return value for streaming


def _non_streaming_response(query: str, history: str) -> Dict[str, Any]:
    """Execute agent and return final response."""
    try:
        response_text = invoke_agent(query, history)
    except Exception as e:
        error_msg = str(e)
        print(f"Agent execution error: {error_msg}")
        # Check for OpenRouter specific errors
        if "403" in error_msg or "PermissionDenied" in error_msg or "limit exceeded" in error_msg.lower():
            return _error_response(502, "LLM service unavailable: API key limit exceeded. Please check OpenRouter key limits.")
        if "401" in error_msg or "AuthenticationError" in error_msg:
            return _error_response(502, "LLM service unavailable: Invalid API key.")
        return _error_response(500, f"Agent execution failed: {error_msg}")
    
    # Check for empty response
    if not response_text or response_text.strip() == "":
        print("Warning: Empty response from LLM")
        return _error_response(502, "LLM returned empty response. Please try again.")
    
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
# force rebuild
