import json
import os
import urllib.request
import urllib.error
from typing import Dict, Any, Generator, Optional

# Environment variables
OPENROUTER_API_KEY = os.environ.get('OPENROUTER_API_KEY')
OPENROUTER_MODEL = os.environ.get('OPENROUTER_MODEL', 'openrouter/free')
OPENROUTER_BASE_URL = os.environ.get('OPENROUTER_BASE_URL', 'https://openrouter.ai/api/v1')

# Deployment test marker - triggers GitHub Actions workflow
DEPLOY_TEST = True
DEPLOY_TEST_V2 = True
DEPLOY_TEST_V3 = True
DEPLOY_TEST_V4 = True
DEPLOY_TEST_V5 = True
DEPLOY_TEST_V6 = True
DEPLOY_TEST_V7_NO_AUD = True

# System prompt with Daniel's context (LangGraph-style context injection)
SYSTEM_PROMPT = """You are Daniel's Agent — an AI assistant that represents Daniel Pham to visitors.

## About Daniel Pham
- **Role**: Backend & Cloud Infrastructure Engineer
- **Experience**: 3+ years
- **Specialization**: Backend development, cloud infrastructure
- **Previous Companies**: Cisco, AWS, Novozymes, TIAA
- **Tech Stack**: Python, TypeScript, Terraform, Kubernetes, AWS services
- **Focus**: Building robust, scalable systems

## Your Role
- You are an AI agent representing Daniel Pham to visitors/users
- The USER is a visitor asking about Daniel - NOT Daniel himself
- Answer questions about Daniel's background, skills, experience, and projects
- Be helpful, knowledgeable, and professional
- If asked about yourself, explain you are Daniel's AI agent
- If asked about Daniel, provide accurate information from the context above
- If the visitor shares their name/info, acknowledge it but remember you represent Daniel

Always respond naturally and conversationally as Daniel's representative."""

# Cache for API key
_cached_api_key = None


def get_openrouter_api_key() -> str:
    """Retrieve OpenRouter API key from AWS Secrets Manager or environment."""
    global _cached_api_key
    if _cached_api_key:
        return _cached_api_key
    
    # First try environment variable
    api_key = os.environ.get('OPENROUTER_API_KEY')
    if api_key:
        _cached_api_key = api_key
        return api_key
    
    # TODO: Add Secrets Manager fallback if needed
    raise ValueError("OPENROUTER_API_KEY not configured")


def call_openrouter_api(query: str, model: Optional[str] = None, history: str = '') -> Dict[str, Any]:
    """Call OpenRouter API (non-streaming)."""
    api_key = get_openrouter_api_key()
    url = f"{OPENROUTER_BASE_URL}/chat/completions"
    
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    if history:
        messages.append({"role": "user", "content": f"Previous context: {history}"})
    messages.append({"role": "user", "content": query})
    
    payload = {
        "model": model or OPENROUTER_MODEL,
        "messages": messages,
        "temperature": 0.7,
        "max_tokens": 1000,
        "stream": False
    }
    
    data = json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            'Authorization': f'Bearer {api_key}',
            'Content-Type': 'application/json',
            'HTTP-Referer': 'https://pavukanez.vercel.app',
            'X-Title': 'Daniel Pham AI Agent'
        },
        method='POST'
    )
    
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            return json.loads(response.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        error_body = e.read().decode('utf-8')
        raise Exception(f"OpenRouter API error ({e.code}): {error_body}")
    except urllib.error.URLError as e:
        raise Exception(f"Network error calling OpenRouter: {str(e)}")


def call_openrouter_api_stream(query: str, model: Optional[str] = None, history: str = '') -> Generator[str, None, None]:
    """Call OpenRouter API with streaming and yield content chunks."""
    api_key = get_openrouter_api_key()
    url = f"{OPENROUTER_BASE_URL}/chat/completions"
    
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    if history:
        messages.append({"role": "user", "content": f"Previous context: {history}"})
    messages.append({"role": "user", "content": query})
    
    payload = {
        "model": model or OPENROUTER_MODEL,
        "messages": messages,
        "temperature": 0.7,
        "max_tokens": 1000,
        "stream": True
    }
    
    data = json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            'Authorization': f'Bearer {api_key}',
            'Content-Type': 'application/json',
            'Accept': 'text/event-stream',
            'HTTP-Referer': 'https://pavukanez.vercel.app',
            'X-Title': 'Daniel Pham AI Agent'
        },
        method='POST'
    )
    
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            for line in response:
                line = line.decode('utf-8').strip()
                if not line or line == 'data: [DONE]':
                    continue
                if line.startswith('data: '):
                    try:
                        chunk_data = json.loads(line[6:])  # Remove 'data: ' prefix
                        choices = chunk_data.get('choices', [])
                        if choices:
                            delta = choices[0].get('delta', {})
                            content = delta.get('content', '')
                            if content:
                                    yield content
                    except json.JSONDecodeError:
                        continue
    except urllib.error.HTTPError as e:
        error_body = e.read().decode('utf-8')
        raise Exception(f"OpenRouter API error ({e.code}): {error_body}")
    except urllib.error.URLError as e:
        raise Exception(f"Network error calling OpenRouter: {str(e)}")


def lambda_handler(event: Dict[str, Any], context: Any, response_stream=None) -> Dict[str, Any]:
    """
    Lambda handler supporting both direct invoke and Lambda Function URL.
    
    For streaming: uses response_stream parameter (Lambda native streaming).
    For non-streaming: returns standard Lambda response dict.
    """
    # Detect invocation type
    request_context = event.get('requestContext')
    http_method = request_context.get('http', {}).get('method') if request_context else None
    is_direct_invoke = not request_context or not http_method
    
    # Handle OPTIONS preflight request (Function URL only)
    if not is_direct_invoke and http_method == 'OPTIONS':
        return {
            "statusCode": 200,
            "headers": {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Headers": "Content-Type",
                "Access-Control-Allow-Methods": "POST, OPTIONS"
            },
            "body": ""
        }
    
    if not is_direct_invoke and http_method != 'POST':
        return {
            "statusCode": 405,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({"error": "Method not allowed. Use POST."})
        }
    
    # Parse request body
    try:
        if is_direct_invoke:
            # Direct SDK invoke: body is the event itself
            body = event
        else:
            # Function URL: parse body from event
            body = event.get('body', '{}')
            # Lambda Function URL may send body as base64 encoded
            if event.get('isBase64Encoded', False):
                import base64
                body = base64.b64decode(body).decode('utf-8')
        if isinstance(body, str):
            body = json.loads(body)
    except json.JSONDecodeError:
        return {
            "statusCode": 400,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({"error": "Invalid JSON in request body"})
        }
    
    # Extract query from body
    query = body.get('query', '').strip()
    history = body.get('history', '').strip()
    stream = body.get('stream', False)  # Support streaming parameter
    
    if not query:
        return {
            "statusCode": 400,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({"error": "Missing 'query' field in request body"})
        }
    
    # Optional: allow model override from request
    model = body.get('model', None)
    
    try:
        if stream and response_stream:
            # Streaming response using Lambda native response streaming
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
                for chunk in call_openrouter_api_stream(query, model, history):
                    # Write NDJSON chunk format expected by Vercel API route
                    response_stream.write(json.dumps({"body": chunk}) + "\n")
                
                # Final chunk
                response_stream.write(json.dumps({"body": "", "isFinal": True}) + "\n")
            except Exception as e:
                print(f"Error in stream generation: {str(e)}")
                response_stream.write(json.dumps({"body": f"Error: {str(e)}", "isFinal": True}) + "\n")
            
            response_stream.end()
            return  # No return value needed for streaming
        
        # Non-streaming (original behavior)
        response_data = call_openrouter_api(query, model, history)
        
        # Extract the generated response
        choices = response_data.get('choices', [])
        if not choices:
            raise Exception("No choices returned from OpenRouter API")
        
        generated_content = choices[0].get('message', {}).get('content', '')
        
        used_model = response_data.get('model', OPENROUTER_MODEL)
        
        return {
            "statusCode": 200,
            "headers": {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Headers": "Content-Type",
                "Access-Control-Allow-Methods": "POST, OPTIONS"
            },
            "body": json.dumps({
                "response": generated_content,
                "model": used_model,
                "usage": response_data.get('usage', {})
            })
        }
    
    except Exception as e:
        print(f"Error processing request: {str(e)}")
        return {
            "statusCode": 500,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({"error": f"Internal server error: {str(e)}"})
        }
