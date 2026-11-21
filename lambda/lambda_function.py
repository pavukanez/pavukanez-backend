import json
import os
import sys
import uuid
import boto3
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
DEPLOY_TEST_V14_STREAMING_FIX = True
DEPLOY_TEST_V15_REPO_REVIEW_DETECTION = True


# SQS client for enqueueing repo review jobs
SQS_QUEUE_URL = os.environ.get('REPO_REVIEW_QUEUE_URL')
sqs_client = boto3.client('sqs', region_name=os.environ.get('AWS_REGION', 'us-east-2')) if SQS_QUEUE_URL else None

# Repo review keywords that trigger async processing
REPO_REVIEW_KEYWORDS = [
    "review", "analyze", "audit", "check", "look at", "inspect",
    "code review", "security review", "architecture review",
    "performance review", "code quality"
]

GITHUB_URL_PATTERN = r'https?://github\.com/([a-zA-Z0-9_.-]+)/([a-zA-Z0-9_.-]+)'

def is_repo_review_query(query: str) -> bool:
    """Check if query is a repo review request."""
    import re
    has_github_url = re.search(GITHUB_URL_PATTERN, query) is not None
    has_review_keyword = any(keyword in query.lower() for keyword in REPO_REVIEW_KEYWORDS)
    result = has_github_url and has_review_keyword
    print(f"DEBUG is_repo_review_query: query={query[:100]}, has_github_url={has_github_url}, has_review_keyword={has_review_keyword}, result={result}")
    return result


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """Main Lambda handler - Entry point for chat/streaming and repo review enqueue."""
    
    # Parse request body
    body = event.get("body", {})
    if isinstance(body, str):
        try:
            body = json.loads(body)
        except json.JSONDecodeError:
            return _error_response(400, "Invalid JSON in request body")
    
    # Handle both formats: direct {query, history, stream} or wrapped {payload: {query, history, stream}}
    if "payload" in body and isinstance(body["payload"], dict):
        payload = body["payload"]
        query = payload.get("query", "").strip()
        history = payload.get("history", "").strip()
        stream = payload.get("stream", False)
    else:
        query = body.get("query", "").strip()
        history = body.get("history", "").strip()
        stream = body.get("stream", False)
    
    request_id = event.get("requestContext", {}).get("requestId", "local")
    
    if not query:
        return _error_response(400, "Missing 'query' field")
    
    # Check if this is a repo review request - if so, enqueue to SQS for async processing
    is_repo = is_repo_review_query(query)
    print(f"DEBUG: is_repo_review={is_repo}")
    if is_repo:
        print("DEBUG: Calling _enqueue_repo_review")
        result = _enqueue_repo_review(query, request_id)
        print(f"DEBUG: _enqueue_repo_review returned: {result}")
        return result
    
    try:
        if stream:
            return _streaming_response(query, history, context)
        else:
            return _non_streaming_response(query, history)
            
    except Exception as e:
        print(f"Error: {str(e)}")
        return _error_response(500, f"Internal server error: {str(e)}")


def _enqueue_repo_review(query: str, request_id: str) -> Dict[str, Any]:
    """Enqueue a repo review job to SQS for async processing by worker."""
    if not sqs_client or not SQS_QUEUE_URL:
        return _error_response(500, "SQS queue not configured for repo reviews")
    
    # Extract GitHub URL and focus from query
    import re
    github_match = re.search(GITHUB_URL_PATTERN, query)
    if not github_match:
        return _error_response(400, "Invalid GitHub URL in query")
    
    owner = github_match.group(1)
    repo = github_match.group(2).replace('.git', '')
    repo_url = f"https://github.com/{owner}/{repo}"
    
    # Extract focus if specified
    focus = ""
    focus_keywords = {
        "security": ["security", "vulnerability", "auth", "authentication", "authorization", "crypto", "encryption", "secret", "token", "permission", "access control"],
        "performance": ["performance", "speed", "optimization", "slow", "bottleneck", "latency", "throughput", "memory", "cpu", "query", "database", "cache"],
        "architecture": ["architecture", "design", "pattern", "structure", "modular", "coupling", "cohesion", "dependency", "layer", "service", "component"],
        "best-practices": ["best practice", "clean code", "style", "convention", "lint", "naming", "documentation", "testing", "maintainability"],
    }
    query_lower = query.lower()
    for focus_name, keywords in focus_keywords.items():
        if any(keyword in query_lower for keyword in keywords):
            focus = focus_name
            break
    
    job_id = str(uuid.uuid4())
    
    try:
        sqs_client.send_message(
            QueueUrl=SQS_QUEUE_URL,
            MessageBody=json.dumps({
                "jobId": job_id,
                "url": repo_url,
                "focus": focus
            })
        )
        
        return {
            "statusCode": 200,
            "headers": {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Headers": "Content-Type",
                "Access-Control-Allow-Methods": "POST, OPTIONS"
            },
            "body": json.dumps({
                "success": True,
                "jobId": job_id,
                "status": "pending",
                "message": f"Repo review job queued. Poll GET /api/repo-reviews/{job_id} for status.",
                "requestId": request_id
            })
        }
    except Exception as e:
        print(f"Failed to enqueue repo review: {str(e)}")
        return _error_response(500, f"Failed to enqueue repo review: {str(e)}")


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
