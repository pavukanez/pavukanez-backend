variable "aws_region" {
  description = "AWS region for deployment"
  type        = string
  default     = "us-east-1"
}

variable "project_name" {
  description = "Project name prefix for resources"
  type        = string
  default     = "pavukanez-backend"
}

variable "lambda_function_name" {
  description = "Name of the Lambda function"
  type        = string
  default     = "pavukanez-backend-openrouter"
}

variable "openrouter_api_key" {
  description = "OpenRouter API key (stored as Lambda environment variable)"
  type        = string
  sensitive   = true
}

variable "openrouter_model" {
  description = "OpenRouter model to use (e.g., openrouter/free)"
  type        = string
  default     = "openrouter/free"
}

variable "upstash_redis_rest_url" {
  description = "Upstash Redis REST URL for rate limiting and caching"
  type        = string
  sensitive   = true
}

variable "upstash_redis_rest_token" {
  description = "Upstash Redis REST token for rate limiting and caching"
  type        = string
  sensitive   = true
}

# GitHub settings
variable "github_token" {
  description = "GitHub token for private repos (optional, for future use)"
  type        = string
  sensitive   = true
  default     = ""
}

variable "github_rate_limit" {
  description = "GitHub API requests per hour per user"
  type        = number
  default     = 100
}

variable "github_cache_ttl" {
  description = "Cache TTL for GitHub data in seconds"
  type        = number
  default     = 3600
}

variable "max_repo_size_mb" {
  description = "Maximum repository size in MB to process"
  type        = number
  default     = 100
}

variable "max_files_per_repo" {
  description = "Maximum files to fetch from a repository"
  type        = number
  default     = 200
}