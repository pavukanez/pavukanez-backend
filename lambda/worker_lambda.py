"""SQS-triggered Worker Lambda for async repo reviews."""
import json
import os
import sys
import time
from typing import Dict, Any

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.config.settings import settings
from src.agent.graph import invoke_agent
from src.tools.github_repo import github_repo_fetch_tree, github_repo_fetch_files

import boto3

# Use environment variables (set by Terraform)
AWS_REGION = os.environ.get('AWS_REGION', 'us-east-2')
REPO_REVIEW_TABLE_NAME = os.environ.get('REPO_REVIEW_TABLE_NAME', 'repo-review-jobs')

sqs = boto3.client('sqs', region_name=AWS_REGION)
dynamodb = boto3.resource('dynamodb', region_name=AWS_REGION)

table = dynamodb.Table(REPO_REVIEW_TABLE_NAME)


def update_job_status(job_id: str, status: str, progress: str, partial_result: str = "", result: str = "", error: str = "") -> None:
    """Update job status in DynamoDB."""
    ttl = int(time.time()) + 7 * 24 * 60 * 60  # 7 days TTL
    
    update_expr = "SET #status = :status, progress = :progress, partialResult = :partial, updatedAt = :now, #ttl = :ttl"
    expr_names = {"#status": "status", "#ttl": "ttl"}
    expr_values = {
        ":status": status,
        ":progress": progress,
        ":partial": partial_result,
        ":now": int(time.time() * 1000),
        ":ttl": ttl,
    }
    
    if result:
        update_expr += ", #result = :result"
        expr_names["#result"] = "result"
        expr_values[":result"] = result
    
    if error:
        update_expr += ", #error = :error"
        expr_names["#error"] = "error"
        expr_values[":error"] = error
    
    table.update_item(
        Key={"jobId": job_id},
        UpdateExpression=update_expr,
        ExpressionAttributeNames=expr_names,
        ExpressionAttributeValues=expr_values,
    )


def get_repo_size_kb(owner: str, repo: str) -> int:
    """Get repository size from GitHub API."""
    import requests
    try:
        resp = requests.get(
            f"https://api.github.com/repos/{owner}/{repo}",
            headers={"Accept": "application/vnd.github.v3+json"},
            timeout=10,
        )
        if resp.ok:
            return resp.json().get("size", 0)
    except Exception:
        pass
    return 0


def process_repo_review(job_id: str, url: str, focus: str) -> str:
    """Process a repo review job and return the final review."""
    update_job_status(job_id, "running", "Fetching repository file tree...")
    
    import re
    match = re.match(r"https?://github\.com/([^/]+)/([^/]+)", url)
    if not match:
        raise ValueError(f"Invalid GitHub URL: {url}")
    owner, repo = match.groups()
    repo = repo.replace(".git", "")
    
    tree_result = github_repo_fetch_tree(url)
    tree_data = json.loads(tree_result)
    
    if "error" in tree_data:
        raise Exception(tree_data["error"])
    
    update_job_status(job_id, "running", "Analyzing codebase structure...")
    
    files = tree_data.get("tree", [])
    file_paths = [f["path"] for f in files[:50]]
    
    update_job_status(job_id, "running", f"Fetching {len(file_paths)} files...")
    
    batch_size = 10
    all_files = []
    for i in range(0, len(file_paths), batch_size):
        batch = file_paths[i:i+batch_size]
        files_result = github_repo_fetch_files(url, batch)
        files_data = json.loads(files_result)
        if "files" in files_data:
            all_files.extend(files_data["files"])
        
        update_job_status(job_id, "running", f"Fetched {min(i+batch_size, len(file_paths))}/{len(file_paths)} files...")
    
    file_contents = ""
    for f in all_files:
        file_contents += f"\n--- {f['path']} ---\n{f['content']}\n"
    
    update_job_status(job_id, "running", "Generating review with LLM...")
    
    focus_text = f" Focus: {focus}." if focus else ""
    review_query = f"""Please review this GitHub repository: {url}.{focus_text}

Repository files:
{file_contents}

Provide a comprehensive code review covering security, performance, architecture, and best practices. Format as markdown with sections: ## Code Review, ### Security Findings, ### Performance Findings, ### Architecture Findings, ### Best Practices."""
    
    review = invoke_agent(review_query, "")
    return review


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """Main SQS-triggered Lambda handler."""
    print(f"Received event: {json.dumps(event)}")
    
    for record in event.get("Records", []):
        try:
            body = json.loads(record["body"])
            job_id = body.get("jobId")
            url = body.get("url")
            focus = body.get("focus", "")
            
            print(f"Processing job {job_id}: {url}")
            
            if not job_id or not url:
                print(f"Invalid message: missing jobId or url")
                continue
            
            update_job_status(job_id, "running", "Starting repo review...")
            
            review = process_repo_review(job_id, url, focus)
            
            update_job_status(job_id, "completed", "Done", result=review)
            print(f"Job {job_id} completed successfully")
            
        except Exception as e:
            import traceback
            error_msg = f"Error processing job: {str(e)}"
            print(f"{error_msg}\n{traceback.format_exc()}")
            
            if "job_id" in locals():
                update_job_status(job_id, "failed", "Error", error=error_msg)
    
    return {"statusCode": 200, "body": "OK"}
