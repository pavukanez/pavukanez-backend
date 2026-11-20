"""Simple agent without LangGraph - direct HTTP requests to OpenRouter API."""
import json
import httpx
from typing import List, Dict, Any
from ..config.settings import settings
from ..tools.google_search import DuckDuckGoSearchTool

# Initialize DuckDuckGo Search tool
duckduckgo_search_tool = DuckDuckGoSearchTool()

# Tool definitions for OpenRouter function calling
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "duckduckgo_search",
            "description": "Search the web for current information, news, facts, or answers to questions. Use this when you need up-to-date information not in your training data. Returns structured results with title, URL, snippet, and source.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query string"},
                    "num_results": {"type": "integer", "minimum": 1, "maximum": 10, "default": 5, "description": "Number of results to return"},
                    "recency_days": {"type": "integer", "description": "Limit results to last N days"}
                },
                "required": ["query"]
            }
        }
    }
]

SYSTEM_PROMPT = """You are Daniel's Agent — an AI assistant representing Daniel Pham.

## About Daniel Pham
- **Role**: Backend & Cloud Infrastructure Engineer
- **Experience**: 3+ years
- **Specialization**: Backend development, cloud infrastructure, AI agents
- **Previous Companies**: Cisco, AWS, Novozymes, TIAA
- **Tech Stack**: Python, TypeScript, Terraform, Kubernetes, AWS, LangGraph

## Your Capabilities
- Answer questions about Daniel's background, skills, experience, and projects
- Search the web for current information using the duckduckgo_search tool
- Be helpful, knowledgeable, and professional

## Tool Usage Guidelines
- Use duckduckgo_search for: current events, recent tech updates, fact verification, unknown topics
- Do NOT search for: personal info about Daniel (use your knowledge), basic coding questions
- Always cite sources when using search results
- Limit to 2-3 searches per conversation turn
"""

# OpenRouter API configuration
OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"
# Use model from settings (configured via OPENROUTER_MODEL env var, defaults to openrouter/auto)
OPENROUTER_MODEL = settings.openrouter_model


def invoke_agent(query: str, history: str = "", max_tool_calls: int = 3) -> str:
    """Invoke the agent with the given query and optional history using direct HTTP requests."""
    
    # Get API key from settings
    api_key = settings.openrouter_api_key
    
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT}
    ]
    
    if history:
        messages.append({"role": "user", "content": f"Previous context: {history}"})
    
    messages.append({"role": "user", "content": query})
    
    tool_call_count = 0
    
    # HTTP client for OpenRouter API
    http_client = httpx.Client(timeout=60.0)
    
    try:
        while True:
            payload = {
                "model": OPENROUTER_MODEL,
                "messages": messages,
                "tools": TOOLS,
                "tool_choice": "auto",
                "temperature": 0.7,
                "max_tokens": 4000,
            }
            
            headers = {
                "Authorization": f"Bearer {settings.openrouter_api_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://pavukanez.vercel.app",
                "X-Title": "Daniel Pham AI Agent",
            }
            
            response = http_client.post(
                OPENROUTER_API_URL,
                json=payload,
                headers=headers,
            )
            
            if response.status_code != 200:
                error_text = response.text
                raise Exception(f"OpenRouter API error: {response.status_code} - {error_text}")
            
            response_data = response.json()
            message = response_data["choices"][0]["message"]
            messages.append(message)
            
            # Check for tool calls
            tool_calls = message.get("tool_calls", [])
            if not tool_calls:
                # No tool calls, return the response
                return message.get("content", "") or ""
            
            # Execute tool calls
            for tool_call in tool_calls:
                if tool_call["function"]["name"] == "duckduckgo_search":
                    import json as json_lib
                    args = json_lib.loads(tool_call["function"]["arguments"])
                    result = duckduckgo_search_tool._run(**args)
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call["id"],
                        "content": result
                    })
            
            # Check max tool calls
            if len([m for m in messages if m.get("role") == "tool"]) >= 3:
                break
        
        # Max tool calls reached, get final response
        payload = {
            "model": OPENROUTER_MODEL,
            "messages": messages,
            "temperature": 0.7,
            "max_tokens": 4000,
        }
        
        response = http_client.post(
            OPENROUTER_API_URL,
            json=payload,
            headers=headers,
        )
        
        if response.status_code != 200:
            error_text = response.text
            raise Exception(f"OpenRouter API error: {response.status_code} - {error_text}")
        
        response_data = response.json()
        return response_data["choices"][0]["message"].get("content", "") or ""
    
    finally:
        http_client.close()