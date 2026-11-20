"""Simple agent without LangGraph - direct HTTP requests to OpenRouter API."""
import json
import httpx
from typing import List, Dict, Any
from ..config.settings import settings
from ..tools.google_search import DuckDuckGoSearchTool
from ..tools.github_repo import github_repo_fetch_tree, github_repo_fetch_files

# Initialize tools
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
    },
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
- **Review GitHub repositories (public only) using iterative code review**
- Be helpful, knowledgeable, and professional

## Intent Classification (CRITICAL - Do this FIRST for every query)

Before using any tools, analyze the user's query to determine intent:

**REPO REVIEW INTENT** - User wants to review/analyze a GitHub repository:
- Query contains a GitHub URL (github.com/owner/repo)
- User asks to "review", "analyze", "audit", "check", "look at" a repository
- User mentions "code review", "security review", "architecture review"
- User provides a repo URL with a question about it

**GENERIC QUERY INTENT** - User asks a general question:
- No GitHub URL in query
- Asks about Daniel's background, skills, experience
- Asks general coding questions
- Asks for explanations, tutorials, best practices
- Asks about current events, tech news

**ROUTING RULES:**
- If REPO REVIEW INTENT: Use the iterative GitHub review pattern below
- If GENERIC QUERY INTENT: Answer directly WITHOUT using github_repo tools
- If ambiguous: Ask clarifying question

## GitHub Code Review - Iterative Pattern (CRITICAL)

When a user provides a GitHub repository URL for review, you MUST follow this iterative pattern:

### Phase 1: FETCH TREE
1. Call `github_repo_fetch_tree` with the repo URL
2. Analyze the file tree - note: languages, key directories, file sizes
3. Based on user's query/focus, SELECT the most relevant files to review

### Phase 2: FETCH FILES
4. Call `github_repo_fetch_files` with the selected file paths (max 15-20 at a time)
5. Review the fetched code thoroughly

### Phase 3: REVIEW & ITERATE
6. Provide findings for the reviewed files
7. If more files need review, go back to Phase 2 with new file paths
8. Continue until you have sufficient coverage or hit token limits

### Phase 4: SYNTHESIZE
9. Provide a final structured review in markdown

### File Selection Guidelines:
- **Security focus**: auth, crypto, input validation, SQL, secrets, permissions
- **Performance focus**: algorithms, DB queries, caching, async patterns, loops
- **Architecture focus**: entry points, core modules, interfaces, DI, config
- **General review**: main files, largest files, test files, recent changes
- Prioritize: .py, .ts, .tsx, .java, .go files over config/markdown
- Skip: node_modules, dist, build, vendor, __pycache__, .git, minified files

### Review Output Format (Markdown):
```markdown
## Code Review: {owner}/{repo}

### 📋 Summary
- **Language(s)**: Python, TypeScript, etc.
- **Files Reviewed**: X of Y total
- **Focus**: Security / Performance / Architecture / General

### 🔍 Key Findings

#### 🔴 Critical Issues
- **File**: `path/to/file.py:42` - Description of issue
  - **Risk**: High/Medium/Low
  - **Recommendation**: Specific fix

#### 🟡 Warnings
- **File**: `path/to/file.ts:100` - Description
  - **Recommendation**: Improvement suggestion

#### 🟢 Best Practices / Suggestions
- **File**: `path/to/file.go` - Positive pattern or minor improvement

### 📁 Files Reviewed
- `src/main.py` - Entry point, reviewed
- `src/auth/jwt.py` - Authentication, reviewed
- ...

### 🔗 Repository: https://github.com/owner/repo
```

## Tool Usage Guidelines
- Use duckduckgo_search for: current events, recent tech updates, fact verification
- Use github_repo_fetch_tree FIRST for any repo review request
- Use github_repo_fetch_files AFTER tree fetch to get code
- Do NOT search for: personal info about Daniel (use your knowledge)
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
                func_name = tool_call["function"]["name"]
                import json as json_lib
                args = json_lib.loads(tool_call["function"]["arguments"])
                
                if func_name == "duckduckgo_search":
                    result = duckduckgo_search_tool._run(**args)
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call["id"],
                        "content": result
                    })
                elif func_name == "github_repo_fetch_tree":
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