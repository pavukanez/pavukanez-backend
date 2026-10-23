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