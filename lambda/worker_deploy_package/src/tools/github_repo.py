"""GitHub Repository fetching tool for public repos only.
Iterative pattern: fetch tree -> LLM selects -> fetch files -> review.
No authentication required for public repos.
"""
import asyncio
import hashlib
import json
import re
from dataclasses import dataclass, asdict
from typing import List, Optional, Dict, Any

import httpx
from ..config.settings import settings
from .rate_limiter import RateLimiter
from .cache import SearchCache


# ──────────────────────────────────────────────
# Data Models
# ────────────────────────────────────────────__

@dataclass
class GitHubRepoInput:
    repo_url: str
    max_files: int = 50
    max_file_size: int = 100_000  # 100KB
    include_extensions: List[str] = None  # e.g., [".py", ".ts", ".java", ".go"]
    exclude_patterns: List[str] = None    # e.g., ["**/node_modules/**", "**/*.min.js"]
    focus_query: str = ""                 # User's review focus (security, performance, etc.)


@dataclass
class RepoInfo:
    owner: str
    name: str
    description: str
    default_branch: str
    size_kb: int
    language: Optional[str]
    stars: int
    forks: int


@dataclass
class TreeEntry:
    path: str
    type: str  # "blob" or "tree"
    size: int
    sha: str


@dataclass
class FileContent:
    path: str
    content: str
    language: str
    size: int
    truncated: bool = False


@dataclass
class FetchTreeResult:
    repo: RepoInfo
    tree: List[TreeEntry]
    total_files: int
    filtered_files: int
    truncated: bool


@dataclass
class FetchFilesResult:
    files: List[FileContent]
    total_size: int
    truncated: bool


# ────────────────────────────────────────────__
# Language Detection
# ────────────────────────────────────────────__

LANGUAGE_EXTENSIONS = {
    ".py": "python",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".js": "javascript",
    ".jsx": "javascript",
    ".java": "java",
    ".go": "go",
    ".rs": "rust",
    ".cpp": "cpp",
    ".c": "c",
    ".h": "c",
    ".hpp": "cpp",
    ".cs": "csharp",
    ".rb": "ruby",
    ".php": "php",
    ".swift": "swift",
    ".kt": "kotlin",
    ".scala": "scala",
    ".md": "markdown",
    ".json": "json",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".toml": "toml",
    ".sql": "sql",
    ".sh": "bash",
    ".dockerfile": "dockerfile",
    ".tf": "terraform",
    ".html": "html",
    ".css": "css",
    ".scss": "scss",
}

SUPPORTED_EXTENSIONS = {".py", ".ts", ".tsx", ".js", ".jsx", ".java", ".go"}


def detect_language(path: str) -> str:
    """Detect language from file extension."""
    for ext, lang in LANGUAGE_EXTENSIONS.items():
        if path.endswith(ext):
            return lang
    return "text"


def is_supported_file(path: str, include_extensions: List[str] = None) -> bool:
    """Check if file should be included based on extension."""
    if include_extensions:
        return any(path.endswith(ext) for ext in include_extensions)
    return any(path.endswith(ext) for ext in SUPPORTED_EXTENSIONS)


def matches_exclude_patterns(path: str, patterns: List[str]) -> bool:
    """Check if path matches any exclude pattern (glob-style)."""
    if not patterns:
        return False
    for pattern in patterns:
        # Convert glob to regex
        regex = pattern.replace("**", ".*").replace("*", "[^/]*")
        if re.match(f"^{regex}$", path):
            return True
    return False


# ────────────────────────────────────────────__
# GitHubRepoTool Class
# ────────────────────────────────────────────__

class GitHubRepoTool:
    """Tool for fetching public GitHub repository data iteratively."""

    name: str = "github_repo"
    description: str = (
        "Fetch and analyze GitHub repositories (public only). "
        "Supports iterative review: first fetch file tree, then fetch selected files for review. "
        "Supports Python, TypeScript, Java, Go, and other languages. "
        "No authentication required for public repositories."
    )

    # GitHub API limits
    GITHUB_API_BASE = "https://api.github.com"
    MAX_TREE_ITEMS = 10000
    MAX_FILES_PER_REQUEST = 50
    MAX_FILE_SIZE = 100_000  # 100KB
    DEFAULT_INCLUDE_EXTS = list(SUPPORTED_EXTENSIONS)
    DEFAULT_EXCLUDE_PATTERNS = [
        "**/node_modules/**",
        "**/dist/**",
        "**/build/**",
        "**/.git/**",
        "**/__pycache__/**",
        "**/*.min.js",
        "**/*.min.css",
        "**/vendor/**",
        "**/target/**",
        "**/.venv/**",
        "**/venv/**",
        "**/env/**",
    ]

    def __init__(self):
        from upstash_redis import Redis
        from ..config.settings import settings
        redis = Redis(url=settings.upstash_url, token=settings.upstash_token)
        self._rate_limiter = RateLimiter(redis, limit=settings.github_rate_limit)
        self._cache = SearchCache(redis, default_ttl=settings.github_cache_ttl)
        self._http_client = httpx.AsyncClient(
            timeout=30.0,
            headers={
                "Accept": "application/vnd.github+json",
                "User-Agent": "DanielPhamAgent/1.0",
            }
        )

    @property
    def rate_limiter(self) -> RateLimiter:
        return self._rate_limiter

    @property
    def cache(self) -> SearchCache:
        return self._cache

    # ────────────────────────────────────────────__
    # Public Interface (sync for Lambda compatibility)
    # ────────────────────────────────────────────__

    def fetch_tree(self, input_data: GitHubRepoInput) -> str:
        """Synchronous wrapper for fetch_tree."""
        return asyncio.run(self._afetch_tree(input_data))

    def fetch_files(self, input_data: GitHubRepoInput, file_paths: List[str]) -> str:
        """Synchronous wrapper for fetch_files."""
        return asyncio.run(self._afetch_files(input_data, file_paths))

    # ────────────────────────────────────────────__
    # Core Async Methods
    # ────────────────────────────────────────────__

    async def _afetch_tree(self, input_data: GitHubRepoInput) -> str:
        """Fetch repository file tree (metadata only, no file contents)."""
        # 1. Rate limit check
        if not await self.rate_limiter.check_limit("github_repo_tree"):
            return json.dumps({"error": "Rate limit exceeded. Please try again later."})

        # 2. Parse and validate URL
        owner, repo = self._parse_repo_url(input_data.repo_url)
        if not owner or not repo:
            return json.dumps({"error": "Invalid GitHub URL. Use format: https://github.com/owner/repo"})

        # 3. Check cache
        cache_key = f"github:tree:{owner}:{repo}:{input_data.max_files}"
        cached = await self.cache.get(cache_key)
        if cached:
            return json.dumps(cached)

        # 4. Execute fetch
        try:
            result = await self._execute_fetch_tree(owner, repo, input_data)
        except Exception as e:
            return json.dumps({"error": f"Failed to fetch repository: {str(e)}"})

        # 5. Cache and return
        await self.cache.set(cache_key, result, ttl=settings.github_cache_ttl)
        return json.dumps(result)

    async def _afetch_files(self, input_data: GitHubRepoInput, file_paths: List[str]) -> str:
        """Fetch contents of specific files."""
        # 1. Rate limit check
        if not await self.rate_limiter.check_limit("github_repo_files"):
            return json.dumps({"error": "Rate limit exceeded. Please try again later."})

        # 2. Parse URL
        owner, repo = self._parse_repo_url(input_data.repo_url)
        if not owner or not repo:
            return json.dumps({"error": "Invalid GitHub URL"})

        # 3. Check cache for each file
        files_to_fetch = []
        cached_files = []
        for path in file_paths[:input_data.max_files]:
            cache_key = f"github:file:{owner}:{repo}:{hashlib.sha256(path.encode()).hexdigest()[:16]}"
            cached = await self.cache.get(cache_key)
            if cached:
                cached_files.append(cached)
            else:
                files_to_fetch.append(path)

        # 4. Fetch uncached files
        fetched_files = []
        if files_to_fetch:
            try:
                fetched_files = await self._execute_fetch_files(owner, repo, files_to_fetch, input_data)
                # Cache fetched files
                for f in fetched_files:
                    cache_key = f"github:file:{owner}:{repo}:{hashlib.sha256(f['path']).hexdigest()[:16]}"
                    await self.cache.set(cache_key, f, ttl=settings.github_cache_ttl)
            except Exception as e:
                return json.dumps({"error": f"Failed to fetch files: {str(e)}"})

        # 5. Combine and return
        all_files = cached_files + fetched_files
        result = {
            "files": all_files,
            "total_size": sum(f["size"] for f in all_files),
            "truncated": len(all_files) < len(file_paths)
        }
        return json.dumps(result)

    # ────────────────────────────────────────────__
    # GitHub API Execution
    # ────────────────────────────────────────────__

    def _parse_repo_url(self, url: str) -> tuple:
        """Parse GitHub URL to extract owner and repo."""
        # Handle various URL formats
        patterns = [
            r"github\.com/([^/]+)/([^/#?]+)",
            r"github\.com/([^/]+)/([^/#?]+)\.git",
        ]
        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                owner = match.group(1)
                repo = match.group(2).replace(".git", "")
                # Validate: only alphanumeric, dash, underscore
                if re.match(r"^[a-zA-Z0-9_.-]+$", owner) and re.match(r"^[a-zA-Z0-9_.-]+$", repo):
                    return owner, repo
        return None, None

    async def _execute_fetch_tree(self, owner: str, repo: str, input_data: GitHubRepoInput) -> dict:
        """Execute the tree fetch via GitHub API."""
        # Get repo info first
        repo_url = f"{self.GITHUB_API_BASE}/repos/{owner}/{repo}"
        repo_resp = await self._http_client.get(repo_url)
        if repo_resp.status_code == 404:
            raise Exception("Repository not found or private")
        if repo_resp.status_code != 200:
            raise Exception(f"GitHub API error: {repo_resp.status_code}")

        repo_data = repo_resp.json()
        default_branch = repo_data.get("default_branch", "main")
        repo_size_kb = repo_data.get("size", 0)

        # Check repo size limit
        if repo_size_kb > settings.max_repo_size_mb * 1024:
            raise Exception(f"Repository too large ({repo_size_kb/1024:.0f}MB > {settings.max_repo_size_mb}MB limit)")

        # Get recursive tree
        tree_url = f"{self.GITHUB_API_BASE}/repos/{owner}/{repo}/git/trees/{default_branch}?recursive=1"
        tree_resp = await self._http_client.get(tree_url)
        if tree_resp.status_code != 200:
            raise Exception(f"Failed to fetch tree: {tree_resp.status_code}")

        tree_data = tree_resp.json()
        if tree_data.get("truncated"):
            # Tree too large, we'll work with what we have
            pass

        # Filter tree entries
        include_exts = input_data.include_extensions or self.DEFAULT_INCLUDE_EXTS
        exclude_patterns = input_data.exclude_patterns or self.DEFAULT_EXCLUDE_PATTERNS

        filtered_entries = []
        for entry in tree_data.get("tree", []):
            if entry["type"] != "blob":
                continue
            if not is_supported_file(entry["path"], include_exts):
                continue
            if matches_exclude_patterns(entry["path"], exclude_patterns):
                continue
            if entry.get("size", 0) > input_data.max_file_size:
                continue
            filtered_entries.append(TreeEntry(
                path=entry["path"],
                type=entry["type"],
                size=entry.get("size", 0),
                sha=entry["sha"]
            ))

        # Sort by relevance: prioritize source files over config, smaller files first
        filtered_entries.sort(key=lambda e: (
            0 if any(e.path.endswith(ext) for ext in [".py", ".ts", ".tsx", ".java", ".go"]) else 1,
            e.size
        ))

        # Limit results
        truncated = len(filtered_entries) > input_data.max_files
        filtered_entries = filtered_entries[:input_data.max_files]

        result = FetchTreeResult(
            repo=RepoInfo(
                owner=owner,
                name=repo,
                description=repo_data.get("description") or "",
                default_branch=default_branch,
                size_kb=repo_size_kb,
                language=repo_data.get("language"),
                stars=repo_data.get("stargazers_count", 0),
                forks=repo_data.get("forks_count", 0),
            ),
            tree=[asdict(e) for e in filtered_entries],
            total_files=len(tree_data.get("tree", [])),
            filtered_files=len(filtered_entries),
            truncated=truncated,
        )
        return asdict(result)

    async def _execute_fetch_files(self, owner: str, repo: str, file_paths: List[str], input_data: GitHubRepoInput) -> List[dict]:
        """Fetch multiple file contents in parallel (batched)."""
        semaphore = asyncio.Semaphore(10)  # Max 10 concurrent requests

        async def fetch_one(path: str) -> Optional[dict]:
            async with semaphore:
                url = f"{self.GITHUB_API_BASE}/repos/{owner}/{repo}/contents/{path}"
                resp = await self._http_client.get(url)
                if resp.status_code != 200:
                    return None
                data = resp.json()
                if data.get("encoding") == "base64":
                    import base64
                    content = base64.b64decode(data["content"]).decode("utf-8", errors="replace")
                else:
                    content = data.get("content", "")

                # Truncate if too large
                truncated = False
                if len(content) > input_data.max_file_size:
                    content = content[:input_data.max_file_size] + f"\n... [truncated, {len(content)} total chars]"
                    truncated = True

                return FileContent(
                    path=path,
                    content=content,
                    language=detect_language(path),
                    size=len(content),
                    truncated=truncated,
                ).__dict__

        tasks = [fetch_one(path) for path in file_paths]
        results = await asyncio.gather(*tasks)
        return [r for r in results if r is not None]

    # ──────────────────────────────────────────────
    # Cleanup
    # ──────────────────────────────────────────────

    async def close(self):
        await self._http_client.aclose()


# ──────────────────────────────────────────────
# Tool Function Wrappers (for agent graph)
# ────────────────────────────────────────────__

# Global instance
_github_repo_tool = GitHubRepoTool()


def github_repo_fetch_tree(
    repo_url: str,
    max_files: int = 50,
    include_extensions: List[str] = None,
    exclude_patterns: List[str] = None,
    focus_query: str = ""
) -> str:
    """Fetch repository file tree for iterative review."""
    input_data = GitHubRepoInput(
        repo_url=repo_url,
        max_files=max_files,
        include_extensions=include_extensions,
        exclude_patterns=exclude_patterns,
        focus_query=focus_query,
    )
    return _github_repo_tool.fetch_tree(input_data)


def github_repo_fetch_files(
    repo_url: str,
    file_paths: List[str],
    max_files: int = 50,
    max_file_size: int = 100_000
) -> str:
    """Fetch contents of specific files from repository."""
    input_data = GitHubRepoInput(
        repo_url=repo_url,
        max_files=max_files,
        max_file_size=max_file_size,
    )
    return _github_repo_tool.fetch_files(input_data, file_paths)
# Force redeploy
