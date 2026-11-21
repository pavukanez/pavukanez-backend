terraform {
  required_version = ">= 1.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    archive = {
      source  = "hashicorp/archive"
      version = "~> 2.0"
    }
  }
}

provider "aws" {
  region = var.aws_region
}

# Data source for current AWS account
data "aws_caller_identity" "current" {}

# S3 bucket for Lambda deployment package
resource "aws_s3_bucket" "lambda_deployment" {
  bucket = "${var.project_name}-lambda-deployment-${data.aws_caller_identity.current.account_id}-${var.aws_region}"

  server_side_encryption_configuration {
    rule {
      apply_server_side_encryption_by_default {
        sse_algorithm = "AES256"
      }
    }
  }

  versioning {
    enabled = true
  }

  lifecycle {
    prevent_destroy = false
  }
}

resource "aws_s3_bucket_public_access_block" "lambda_deployment" {
  bucket = aws_s3_bucket.lambda_deployment.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# Null resource to create the MAIN Lambda deployment package (for chat/streaming)
resource "null_resource" "lambda_package" {
  triggers = {
    requirements_hash = filemd5("${path.module}/../lambda/requirements.txt")
    source_hash       = filemd5("${path.module}/../lambda/lambda_function.py")
  }

  provisioner "local-exec" {
    command = <<-EOT
      set -e
      cd ${path.module}/../lambda
      rm -rf deploy_package
      mkdir -p deploy_package
      # Copy source code
      cp -r src deploy_package/
      cp lambda_function.py deploy_package/
      cp requirements.txt deploy_package/
      # Install dependencies
      cd deploy_package
      python3 -m pip install --target . -r requirements.txt --quiet --no-cache-dir 2>/dev/null
      # Remove unnecessary files
      find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
      find . -type d -name "*.dist-info" -exec rm -rf {} + 2>/dev/null || true
      find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
      find . -name "*.pyc" -delete 2>/dev/null || true
      find . -name "*.pyo" -delete 2>/dev/null || true
      find . -name "tests" -type d -exec rm -rf {} + 2>/dev/null || true
      find . -name "*.dist-info" -type d -exec rm -rf {} + 2>/dev/null || true
      find . -name "*.egg-info" -type d -exec rm -rf {} + 2>/dev/null || true
    EOT
  }
}

# Null resource to create the WORKER Lambda deployment package (for async repo reviews)
resource "null_resource" "worker_lambda_package" {
  triggers = {
    requirements_hash = filemd5("${path.module}/../lambda/requirements.txt")
    source_hash       = filemd5("${path.module}/../lambda/worker_lambda.py")
  }

  provisioner "local-exec" {
    command = <<-EOT
      set -e
      cd ${path.module}/../lambda
      rm -rf worker_deploy_package
      mkdir -p worker_deploy_package
      # Copy source code
      cp -r src worker_deploy_package/
      cp worker_lambda.py worker_deploy_package/
      cp requirements.txt worker_deploy_package/
      # Install dependencies
      cd worker_deploy_package
      python3 -m pip install --target . -r requirements.txt --quiet --no-cache-dir 2>/dev/null
      # Remove unnecessary files
      find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
      find . -type d -name "*.dist-info" -exec rm -rf {} + 2>/dev/null || true
      find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
      find . -name "*.pyc" -delete 2>/dev/null || true
      find . -name "*.pyo" -delete 2>/dev/null || true
      find . -name "tests" -type d -exec rm -rf {} + 2>/dev/null || true
      find . -name "*.dist-info" -type d -exec rm -rf {} + 2>/dev/null || true
      find . -name "*.egg-info" -type d -exec rm -rf {} + 2>/dev/null || true
    EOT
  }
}

# Main Lambda deployment package
data "archive_file" "lambda_zip" {
  type        = "zip"
  source_dir  = "${path.module}/../lambda/deploy_package"
  output_path = abspath("${path.module}/../lambda/lambda_function.zip")
  depends_on  = [null_resource.lambda_package]
}

# Worker Lambda deployment package
data "archive_file" "worker_lambda_zip" {
  type        = "zip"
  source_dir  = "${path.module}/../lambda/worker_deploy_package"
  output_path = abspath("${path.module}/../lambda/worker_lambda.zip")
  depends_on  = [null_resource.worker_lambda_package]
}

resource "aws_s3_object" "worker_lambda_zip" {
  bucket = aws_s3_bucket.lambda_deployment.id
  key    = "worker_lambda/${var.worker_lambda_function_name}.zip"
  source = data.archive_file.worker_lambda_zip.output_path
  etag   = filemd5(data.archive_file.worker_lambda_zip.output_path)
}

resource "aws_s3_object" "lambda_zip" {
  bucket = aws_s3_bucket.lambda_deployment.id
  key    = "lambda_function/${var.lambda_function_name}.zip"
  source = data.archive_file.lambda_zip.output_path
  etag   = filemd5(data.archive_file.lambda_zip.output_path)
}

# IAM Role for Main Lambda
resource "aws_iam_role" "lambda_role" {
  name = "${var.project_name}-lambda-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = "sts:AssumeRole"
      Effect = "Allow"
      Principal = {
        Service = "lambda.amazonaws.com"
      }
  }] })
}

resource "aws_iam_role_policy_attachment" "lambda_basic_execution" {
  role       = aws_iam_role.lambda_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

# SQS Queue for async repo reviews with Dead Letter Queue
resource "aws_sqs_queue" "repo_review_dlq" {
  name                       = "${var.project_name}-repo-review-dlq"
  message_retention_seconds  = 604800  # 7 days
}

resource "aws_sqs_queue" "repo_review_queue" {
  name                       = "${var.project_name}-repo-review-queue"
  message_retention_seconds  = 604800  # 7 days
  visibility_timeout_seconds = 300     # 5 minutes (matches Lambda timeout)
  receive_wait_time_seconds  = 20      # Long polling

  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.repo_review_dlq.arn
    maxReceiveCount     = 3
  })
}

# DynamoDB table for job status/results with TTL
resource "aws_dynamodb_table" "repo_review_jobs" {
  name           = "${var.project_name}-repo-review-jobs"
  billing_mode   = "PAY_PER_REQUEST"
  hash_key       = "jobId"
  ttl {
    attribute_name = "ttl"
    enabled        = true
  }

  attribute {
    name = "jobId"
    type = "S"
  }
}

# IAM Role for Worker Lambda (needs SQS, DynamoDB, and AWSLambdaBasicExecutionRole)
resource "aws_iam_role" "worker_lambda_role" {
  name = "${var.project_name}-worker-lambda-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = "sts:AssumeRole"
      Effect = "Allow"
      Principal = {
        Service = "lambda.amazonaws.com"
      }
  }] })
}

resource "aws_iam_role_policy_attachment" "worker_lambda_basic_execution" {
  role       = aws_iam_role.worker_lambda_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

# Worker Lambda needs permissions for SQS, DynamoDB
resource "aws_iam_role_policy" "worker_lambda_permissions" {
  name = "${var.project_name}-worker-lambda-permissions"
  role = aws_iam_role.worker_lambda_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = [
          "sqs:ReceiveMessage",
          "sqs:DeleteMessage",
          "sqs:GetQueueAttributes"
        ]
        Effect   = "Allow"
        Resource = aws_sqs_queue.repo_review_queue.arn
      },
      {
        Action = [
          "dynamodb:GetItem",
          "dynamodb:PutItem",
          "dynamodb:UpdateItem",
          "dynamodb:Query"
        ]
        Effect   = "Allow"
        Resource = aws_dynamodb_table.repo_review_jobs.arn
      }
    ]
  })
}

# Main Lambda Function (Entry Lambda) - 60s timeout for chat/streaming
# Only handles: chat queries, streaming, enqueueing repo review jobs to SQS
resource "aws_lambda_function" "openrouter_lambda" {
  function_name = var.lambda_function_name
  role          = aws_iam_role.lambda_role.arn
  runtime       = "python3.11"
  handler       = "lambda_function.lambda_handler"
  s3_bucket     = aws_s3_bucket.lambda_deployment.id
  s3_key        = aws_s3_object.lambda_zip.key
  timeout       = 60
  memory_size   = 512

  environment {
    variables = {
      OPENROUTER_API_KEY  = var.openrouter_api_key
      OPENROUTER_MODEL    = var.openrouter_model
      OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
      # Upstash Redis for rate limiting & caching
      UPSTASH_REDIS_REST_URL   = var.upstash_redis_rest_url
      UPSTASH_REDIS_REST_TOKEN = var.upstash_redis_rest_token
      # Search configuration
      SEARCH_RATE_LIMIT  = "30"
      SEARCH_CACHE_TTL   = "3600"
      SEARCH_MAX_RESULTS = "5"
      MAX_TOOL_CALLS     = "3"
      # GitHub configuration
      GITHUB_TOKEN       = var.github_token
      GITHUB_RATE_LIMIT  = var.github_rate_limit
      GITHUB_CACHE_TTL   = var.github_cache_ttl
      MAX_REPO_SIZE_MB   = var.max_repo_size_mb
      MAX_FILES_PER_REPO = var.max_files_per_repo
      # SQS Queue for async repo reviews
      REPO_REVIEW_QUEUE_URL = aws_sqs_queue.repo_review_queue.url
    }
  }

  # Ensure the Lambda is updated when the zip file changes
  source_code_hash = data.archive_file.lambda_zip.output_base64sha256
}

# Worker Lambda Function - 300s timeout for async repo reviews
# Triggered by SQS, processes: fetch tree, fetch files, run LLM review
resource "aws_lambda_function" "worker_lambda" {
  function_name = var.worker_lambda_function_name
  role          = aws_iam_role.worker_lambda_role.arn
  runtime       = "python3.11"
  handler       = "worker_lambda.lambda_handler"
  s3_bucket     = aws_s3_bucket.lambda_deployment.id
  s3_key        = aws_s3_object.worker_lambda_zip.key
  timeout       = 300
  memory_size   = 1024

  environment {
    variables = {
      OPENROUTER_API_KEY  = var.openrouter_api_key
      OPENROUTER_MODEL    = var.openrouter_model
      OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
      # Upstash Redis for rate limiting & caching
      UPSTASH_REDIS_REST_URL   = var.upstash_redis_rest_url
      UPSTASH_REDIS_REST_TOKEN = var.upstash_redis_rest_token
      # Search configuration
      SEARCH_RATE_LIMIT  = "30"
      SEARCH_CACHE_TTL   = "3600"
      SEARCH_MAX_RESULTS = "5"
      MAX_TOOL_CALLS     = "3"
      # GitHub configuration
      GITHUB_TOKEN       = var.github_token
      GITHUB_RATE_LIMIT  = var.github_rate_limit
      GITHUB_CACHE_TTL   = var.github_cache_ttl
      MAX_REPO_SIZE_MB   = var.max_repo_size_mb
      MAX_FILES_PER_REPO = var.max_files_per_repo
      # SQS & DynamoDB
      REPO_REVIEW_QUEUE_URL = aws_sqs_queue.repo_review_queue.url
      REPO_REVIEW_TABLE_NAME = aws_dynamodb_table.repo_review_jobs.name
      AWS_REGION         = var.aws_region
    }
  }

  # Ensure the Lambda is updated when the zip file changes
  source_code_hash = data.archive_file.worker_lambda_zip.output_base64sha256
}

# SQS Event Source Mapping for Worker Lambda
resource "aws_lambda_event_source_mapping" "worker_sqs_trigger" {
  event_source_arn = aws_sqs_queue.repo_review_queue.arn
  function_name    = aws_lambda_function.worker_lambda.function_name
  batch_size       = 1
  maximum_batching_window_in_seconds = 0
}

# Lambda Function URL (free tier eligible, no API Gateway needed)
# Using AWS_IAM auth type because organization SCP blocks public (NONE) Function URLs
resource "aws_lambda_function_url" "openrouter_url" {
  function_name      = aws_lambda_function.openrouter_lambda.function_name
  authorization_type = "AWS_IAM"
  invoke_mode        = "RESPONSE_STREAM"
  cors {
    allow_credentials = false
    allow_headers     = ["Content-Type"]
    allow_methods     = ["*"]
    allow_origins     = ["*"]
    max_age           = 86400
  }
}

# CloudWatch Log Group for Main Lambda
resource "aws_cloudwatch_log_group" "lambda_logs" {
  name              = "/aws/lambda/${var.lambda_function_name}"
  retention_in_days = 14
}

# CloudWatch Log Group for Worker Lambda
resource "aws_cloudwatch_log_group" "worker_lambda_logs" {
  name              = "/aws/lambda/${var.worker_lambda_function_name}"
  retention_in_days = 14
}

# Outputs
output "function_url" {
  description = "Lambda Function URL endpoint"
  value       = aws_lambda_function_url.openrouter_url.function_url
}

output "lambda_function_name" {
  description = "Main Lambda function name (Entry Lambda)"
  value       = aws_lambda_function.openrouter_lambda.function_name
}

output "lambda_function_arn" {
  description = "Main Lambda function ARN"
  value       = aws_lambda_function.openrouter_lambda.arn
}

output "worker_lambda_function_name" {
  description = "Worker Lambda function name (Async Repo Review)"
  value       = aws_lambda_function.worker_lambda.function_name
}

output "worker_lambda_function_arn" {
  description = "Worker Lambda function ARN"
  value       = aws_lambda_function.worker_lambda.arn
}
