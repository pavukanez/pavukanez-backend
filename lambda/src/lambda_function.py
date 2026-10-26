import json
import os
import urllib.request
import urllib.error
from typing import Dict, Any

# Environment variables
OPENROUTER_API_KEY = os.environ.get('OPENROUTER_API_KEY')
OPENROUTER_MODEL = os.environ.get('OPENROUTER_MODEL', 'openrouter/free')
OPENROUTER_BASE_URL = os.environ.get('OPENROUTER_BASE_URL', 'https://openrouter.ai/api/v1')

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
    """Retrieve OpenRouter API key from environment variable."""
    global _cached_api_key
    
    if _cached_api_key:
        return _cached_api_key
    
    if not OPENROUTER_API_KEY:
        raise ValueError("OPENROUTER_API_KEY environment variable not set")
    
    _cached_api_key = OPENROUTER_API_KEY
    return _cached_api_key


def call_openrouter_api(query: str, model: str = None, history: str = "") -> Dict[str, Any]:
    """Call OpenRouter API to get LLM response."""
    api_key = get_openrouter_api_key()
    model = model or OPENROUTER_MODEL
    
    url = f"{OPENROUTER_BASE_URL}/chat/completions"
    
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/pavukanez/pavukanez-backend",
        "X-Title": "pavukanez-backend"
    }
    
    # Build messages with conversation history
    messages = [
        {
            "role": "system",
            "content": SYSTEM_PROMPT
        }
    ]
    
    # Add conversation history if provided - parse into proper message format
    if history:
        # Parse history format: "User: ...\nAssistant: ...\nUser: ...\nAssistant: ..."
        lines = history.strip().split('\n')
        for line in lines:
            if line.startswith('User: '):
                messages.append({
                    "role": "user",
                    "content": line[6:]  # Remove "User: "
                })
            elif line.startswith('Assistant: '):
                messages.append({
                    "role": "assistant",
                    "content": line[11:]  # Remove "Assistant: "
                })
            # Skip empty lines or malformed lines
    
    # Add current query
    messages.append({
        "role": "user",
        "content": query
    })
    
    payload = {
        "model": model,
        "messages": messages,
        "temperature": 0.7,
        "max_tokens": 2000
    }
    
    data = json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(url, data=data, headers=headers, method='POST')
    
    try:
        with urllib.request.urlopen(req, timeout=25) as response:
            response_data = json.loads(response.read().decode('utf-8'))
            return response_data
    except urllib.error.HTTPError as e:
        error_body = e.read().decode('utf-8')
        raise Exception(f"OpenRouter API error ({e.code}): {error_body}")
    except urllib.error.URLError as e:
        raise Exception(f"Network error calling OpenRouter API: {str(e)}")


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lambda handler for processing user queries via OpenRouter.

    Supports two invocation modes:
    1. Lambda Function URL (HTTP) event:
       {
           "requestContext": {"http": {"method": "POST", ...}},
           "body": "{\"query\": \"user query\"}",
           "headers": {...},
           "isBase64Encoded": false
       }
    2. Direct SDK Invoke event (from AWS SDK):
       {
           "query": "user query string",
           "model": "optional-model-name"
       }

    Returns:
    {
        "statusCode": 200,
        "body": "{\"response\": \"LLM response\", \"model\": \"model-name\"}",
        "headers": {"Content-Type": "application/json"}
    }
    """
    # Detect invocation mode: Function URL vs direct SDK invoke
    request_context = event.get('requestContext', {})
    http_method = request_context.get('http', {}).get('method', '') if request_context else ''

    # If no requestContext or no http method -> direct SDK invoke
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

    if not query:
        return {
            "statusCode": 400,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({"error": "Missing 'query' field in request body"})
        }

    # Optional: allow model override from request
    model = body.get('model', None)

    try:
        # Call OpenRouter API
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
