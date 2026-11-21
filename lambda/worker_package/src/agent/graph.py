"""Simple agent without LangGraph - direct HTTP requests to OpenRouter API."""
import json
import httpx
import re
from typing import List, Dict, Any, AsyncGenerator, Optional
from ..config.settings import settings
from ..tools.github_repo import github_repo_fetch_tree, github_repo_fetch_files

# Tool definitions for OpenRouter function calling
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "github_repo_fetch_tree",
            "description": "Fetch a GitHub repository's file tree (metadata only). Use this FIRST to understand the codebase structure. Returns file paths, sizes, and types. Supports filtering by language extensions.",
            "parameters": {
                "type": "object",
                "properties": {
                    "repo_url": {"type": "string", "description": "GitHub repository URL (e.g., https://github.com/owner/repo)"},
                    "max_files": {"type": "integer", "default": 100, "description": "Maximum files to return"},
                    "include_extensions": {"type": "array", "items": {"type": "string"}, "description": "File extensions to include (e.g., ['.py', '.ts', '.java', '.go'])"},
                    "exclude_patterns": {"type": "array", "items": {"type": "string"}, "description": "Glob patterns to exclude"},
                    "focus_query": {"type": "string", "description": "User's review focus to help prioritize files"}
                },
                "required": ["repo_url"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "github_repo_fetch_files",
            "description": "Fetch contents of specific files from a GitHub repository. Use AFTER fetch_tree to get actual code for review.",
            "parameters": {
                "type": "object",
                "properties": {
                    "repo_url": {"type": "string", "description": "GitHub repository URL"},
                    "file_paths": {"type": "array", "items": {"type": "string"}, "description": "List of file paths to fetch"},
                    "max_files": {"type": "integer", "default": 20, "description": "Maximum files to fetch"},
                    "max_file_size": {"type": "integer", "default": 100000, "description": "Max characters per file"}
                },
                "required": ["repo_url", "file_paths"]
            }
        }
    }
]

GITHUB_URL_PATTERN = re.compile(
    r'https?://github\.com/([a-zA-Z0-9_.-]+)/([a-zA-Z0-9_.-]+)'
)

REPO_REVIEW_KEYWORDS = [
    "review", "analyze", "audit", "check", "look at", "inspect",
    "code review", "security review", "architecture review",
    "performance review", "code quality"
]

class QueryIntent:
    """Result of intent classification."""
    REPO_REVIEW = "repo_review"
    GENERIC_QUERY = "generic_query"
    AMBIGUOUS = "ambiguous"

class IntentResult:
    """Result of intent classification with extracted data."""
    def __init__(self, intent: str, repo_url: str = None, focus: str = None, clarification: str = None):
        self.intent = intent
        self.repo_url = repo_url
        self.focus = focus
        self.clarification = clarification

def classify_intent(query: str):
    """
    Classify the user's query intent.
    
    Returns:
        IntentResult with intent type and extracted data (repo_url, focus, etc.)
    """
    query_lower = query.lower().strip()
    
    # Check for GitHub URL
    github_match = GITHUB_URL_PATTERN.search(query)
    repo_url = None
    if github_match:
        owner = github_match.group(1)
        repo = github_match.group(2).replace('.git', '')
        repo_url = f"https://github.com/{owner}/{repo}"
    
    # Check for repo review keywords
    has_review_keyword = any(keyword in query_lower for keyword in REPO_REVIEW_KEYWORDS)
    
    # Determine intent
    if repo_url and has_review_keyword:
        # Explicit repo URL + review keyword = clear repo review intent
        focus = _extract_focus(query_lower)
        return IntentResult("repo_review", repo_url=repo_url, focus=focus)
    
    if repo_url and not has_review_keyword:
        # URL without explicit review keyword - could be ambiguous
        # Check if query is just the URL or has a question about it
        if len(query.strip()) > len(repo_url) + 10:
            # Has additional context beyond just the URL
            focus = _extract_focus(query_lower)
            return IntentResult("repo_review", repo_url=repo_url, focus=focus)
        else:
            # Just the URL - ask for clarification
            return IntentResult(
                "ambiguous",
                repo_url=repo_url,
                clarification="Please specify what you'd like me to do with this repository (e.g., 'review', 'analyze for security issues', 'check architecture')."
            )
    
    if has_review_keyword and not repo_url:
        # Review keywords but no URL - ambiguous
        return IntentResult(
            "ambiguous",
            clarification="Please provide a GitHub repository URL (e.g., https://github.com/owner/repo) for me to review."
        )
    
    # No repo URL, no review keywords = generic query
    return IntentResult("generic_query")


def _extract_focus(query: str) -> str:
    """Extract review focus from query."""
    focus_map = {
        "security": ["security", "vulnerability", "auth", "authentication", "authorization", "crypto", "encryption", "secret", "token", "permission", "access control"],
        "performance": ["performance", "speed", "optimization", "slow", "bottleneck", "latency", "throughput", "memory", "cpu", "query", "database", "cache"],
        "architecture": ["architecture", "design", "pattern", "structure", "modular", "coupling", "cohesion", "dependency", "layer", "service", "component"],
        "best-practices": ["best practice", "clean code", "style", "convention", "lint", "naming", "documentation", "testing", "maintainability"],
    }
    
    query_lower = query.lower()
    for focus, keywords in focus_map.items():
        if any(keyword in query_lower for keyword in keywords):
            return focus
    return "general"


SYSTEM_PROMPT = """You are Daniel's Agent — an AI assistant representing Daniel Pham.

## About Daniel Pham
- **Role**: Backend & Cloud Infrastructure Engineer
- **Experience**: 3+ years
- **Specialization**: Backend development, cloud infrastructure, AI agents
- **Previous Companies**: Cisco, AWS, Novozymes, TIAA
- **Tech Stack**: Python, TypeScript, Terraform, Kubernetes, AWS, LangGraph

## Your Capabilities
- Answer questions about Daniel's background, skills, experience, and projects
- **Review GitHub repositories (public only) using iterative code review**
- Be helpful, knowledgeable, and professional

## Tool Usage Guidelines
- Use github_repo_fetch_tree FIRST for any repo review request
- Use github_repo_fetch_files AFTER tree fetch to get code
- Do NOT search for: personal info about Daniel (use your knowledge), basic coding questions
- Limit to 2-3 tool calls per conversation turn
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
                func_name = tool_call["function"]["name"]
                import json as json_lib
                args = json_lib.loads(tool_call["function"]["arguments"])
                
                if func_name == "github_repo_fetch_tree":
                    result = github_repo_fetch_tree(**args)
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call["id"],
                        "content": result
                    })
                elif func_name == "github_repo_fetch_files":
                    result = github_repo_fetch_files(**args)
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call["id"],
                        "content": result
                    })
            
            # Check max tool calls
            if len([m for m in messages if m.get("role") == "tool"]) >= max_tool_calls:
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

# Streaming function moved to end of file
# DEPLOY_TRIGGER: streaming v2
async def invoke_agent_streaming(
    query: str, 
    history: str = "", 
    max_tool_calls: int = 3
) -> AsyncGenerator[str, None]:
    """Invoke the agent with streaming response from OpenRouter."""
    
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT}
    ]
    
    if history:
        messages.append({"role": "user", "content": f"Previous context: {history}"})
    
    messages.append({"role": "user", "content": query})
    
    async with httpx.AsyncClient(timeout=60.0) as http_client:
        try:
            while True:
                payload = {
                    "model": OPENROUTER_MODEL,
                    "messages": messages,
                    "tools": TOOLS,
                    "tool_choice": "auto",
                    "temperature": 0.7,
                    "max_tokens": 4000,
                    "stream": True,
                }
                
                headers = {
                    "Authorization": f"Bearer {settings.openrouter_api_key}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "https://pavukanez.vercel.app",
                    "X-Title": "Daniel Pham AI Agent",
                    "Accept": "text/event-stream",
                }
                
                async with http_client.stream(
                    "POST",
                    OPENROUTER_API_URL,
                    json=payload,
                    headers=headers,
                ) as response:
                    if response.status_code != 200:
                        error_text = await response.aread()
                        raise Exception(f"OpenRouter API error: {response.status_code} - {error_text.decode()}")
                    
                    tool_calls_buffer = []
                    accumulated_content = ""
                    
                    async for line in response.aiter_lines():
                        if not line.startswith("data: "):
                            continue
                        data = line[6:]
                        if data == "[DONE]":
                            break
                        try:
                            parsed = json.loads(data)
                            delta = parsed.get("choices", [{}])[0].get("delta", {})
                            
                            if "tool_calls" in delta:
                                for tc in delta["tool_calls"]:
                                    index = tc.get("index", 0)
                                    if index >= len(tool_calls_buffer):
                                        tool_calls_buffer.append({"id": "", "function": {"name": "", "arguments": ""}})
                                    tc_buf = tool_calls_buffer[index]
                                    if "id" in tc:
                                        tc_buf["id"] = tc["id"]
                                    if "function" in tc:
                                        if "name" in tc["function"]:
                                            tc_buf["function"]["name"] = tc["function"]["name"]
                                        if "arguments" in tc["function"]:
                                            tc_buf["function"]["arguments"] += tc["function"]["arguments"]
                            
                            if "content" in delta and delta["content"]:
                                content = delta["content"]
                                accumulated_content += content
                                yield content
                        
                        except json.JSONDecodeError:
                            pass
                    
                    if tool_calls_buffer:
                        assistant_message = {
                            "role": "assistant",
                            "content": accumulated_content or None,
                            "tool_calls": tool_calls_buffer
                        }
                        messages.append(assistant_message)
                        
                        for tool_call in tool_calls_buffer:
                            func_name = tool_call["function"]["name"]
                            import json as json_lib
                            args = json_lib.loads(tool_call["function"]["arguments"])
                            
                            if func_name == "github_repo_fetch_tree":
                                result = github_repo_fetch_tree(**args)
                                messages.append({
                                    "role": "tool",
                                    "tool_call_id": tool_call["id"],
                                    "content": result
                                })
                            elif func_name == "github_repo_fetch_files":
                                result = github_repo_fetch_files(**args)
                                messages.append({
                                    "role": "tool",
                                    "tool_call_id": tool_call["id"],
                                    "content": result
                                })
                        
                        if len([m for m in messages if m.get("role") == "tool"]) >= max_tool_calls:
                            break
                        continue
                    
                    break
            
            payload = {
                "model": OPENROUTER_MODEL,
                "messages": messages,
                "temperature": 0.7,
                "max_tokens": 4000,
                "stream": True,
            }
            
            async with http_client.stream(
                "POST",
                OPENROUTER_API_URL,
                json=payload,
                headers=headers,
            ) as response:
                if response.status_code != 200:
                    error_text = await response.aread()
                    raise Exception(f"OpenRouter API error: {response.status_code} - {error_text.decode()}")
                
                async for line in response.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    data = line[6:]
                    if data == "[DONE]":
                        break
                    try:
                        parsed = json.loads(data)
                        content = parsed.get("choices", [{}])[0].get("delta", {}).get("content")
                        if content:
                            yield content
                    except json.JSONDecodeError:
                        pass
        
        except Exception as e:
            yield f"Error: {str(e)}"
