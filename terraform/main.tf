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

# Lambda deployment package
data "archive_file" "lambda_zip" {
  type        = "zip"
  source_dir  = "${path.module}/../lambda/src"
  output_path = "${path.module}/../lambda/lambda_function.zip"
}

resource "aws_s3_object" "lambda_zip" {
  bucket = aws_s3_bucket.lambda_deployment.id
  key    = "lambda_function/${var.lambda_function_name}.zip"
  source = data.archive_file.lambda_zip.output_path
  etag   = filemd5(data.archive_file.lambda_zip.output_path)
}

# IAM Role for Lambda
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
    }]
  })
}

resource "aws_iam_role_policy_attachment" "lambda_basic_execution" {
  role       = aws_iam_role.lambda_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_policy" "lambda_secrets_access" {
  name = "${var.project_name}-lambda-secrets-policy"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = [
        "secretsmanager:GetSecretValue"
      ]
      Resource = aws_secretsmanager_secret.openrouter_api_key.arn
    }]})
}

resource "aws_iam_role_policy_attachment" "lambda_secrets_access" {
  role       = aws_iam_role.lambda_role.name
  policy_arn = aws_iam_policy.lambda_secrets_access.arn
}

# Secrets Manager for OpenRouter API Key
resource "aws_secretsmanager_secret" "openrouter_api_key" {
  name = "${var.project_name}/openrouter-api-key"
}

resource "aws_secretsmanager_secret_version" "openrouter_api_key" {
  secret_id     = aws_secretsmanager_secret.openrouter_api_key.id
  secret_string = var.openrouter_api_key
}

# Lambda Function
resource "aws_lambda_function" "openrouter_lambda" {
  function_name = var.lambda_function_name
  role          = aws_iam_role.lambda_role.arn
  runtime       = "python3.11"
  handler       = "lambda_function.lambda_handler"
  s3_bucket     = aws_s3_bucket.lambda_deployment.id
  s3_key        = aws_s3_object.lambda_zip.key
  timeout       = 30
  memory_size   = 256

  environment {
    variables = {
      OPENROUTER_API_KEY_SECRET_ARN = aws_secretsmanager_secret.openrouter_api_key.arn
      OPENROUTER_MODEL              = var.openrouter_model
      OPENROUTER_BASE_URL           = "https://openrouter.ai/api/v1"
    }
  }

  # Ensure the Lambda is updated when the zip file changes
  source_code_hash = data.archive_file.lambda_zip.output_base64sha256
}
# API Gateway REST API
resource "aws_api_gateway_rest_api" "openrouter_api" {
  name        = "${var.project_name}-api"
  description = "API Gateway for OpenRouter Lambda function"

  endpoint_configuration {
    types = ["REGIONAL"]
  }
}

resource "aws_api_gateway_resource" "query_resource" {
  rest_api_id = aws_api_gateway_rest_api.openrouter_api.id
  parent_id   = aws_api_gateway_rest_api.openrouter_api.root_resource_id
  path_part   = "query"
}

resource "aws_api_gateway_method" "query_post" {
  rest_api_id   = aws_api_gateway_rest_api.openrouter_api.id
  resource_id   = aws_api_gateway_resource.query_resource.id
  http_method   = "POST"
  authorization = "NONE"
}

resource "aws_api_gateway_integration" "query_lambda" {
  rest_api_id             = aws_api_gateway_rest_api.openrouter_api.id
  resource_id             = aws_api_gateway_resource.query_resource.id
  http_method             = aws_api_gateway_method.query_post.http_method
  integration_http_method = "POST"
  type                    = "AWS_PROXY"
  uri                     = aws_lambda_function.openrouter_lambda.invoke_arn
}

resource "aws_api_gateway_method_response" "query_200" {
  rest_api_id = aws_api_gateway_rest_api.openrouter_api.id
  resource_id = aws_api_gateway_resource.query_resource.id
  http_method = aws_api_gateway_method.query_post.http_method
  status_code = "200"
}

resource "aws_api_gateway_method_response" "query_400" {
  rest_api_id = aws_api_gateway_rest_api.openrouter_api.id
  resource_id = aws_api_gateway_resource.query_resource.id
  http_method = aws_api_gateway_method.query_post.http_method
  status_code = "400"
}

resource "aws_api_gateway_method_response" "query_500" {
  rest_api_id = aws_api_gateway_rest_api.openrouter_api.id
  resource_id = aws_api_gateway_resource.query_resource.id
  http_method = aws_api_gateway_method.query_post.http_method
  status_code = "500"
}

# Lambda Permission for API Gateway
resource "aws_lambda_permission" "api_gateway_invoke" {
  statement_id  = "AllowAPIGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.openrouter_lambda.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_api_gateway_rest_api.openrouter_api.execution_arn}/*/*"
}

# API Gateway Deployment
resource "aws_api_gateway_deployment" "openrouter_deployment" {
  depends_on = [
    aws_api_gateway_integration.query_lambda
  ]

  rest_api_id = aws_api_gateway_rest_api.openrouter_api.id
  stage_name  = var.api_gateway_stage_name

  lifecycle {
    create_before_destroy = true
  }
}

# API Gateway Stage
resource "aws_api_gateway_stage" "openrouter_stage" {
  deployment_id = aws_api_gateway_deployment.openrouter_deployment.id
  rest_api_id   = aws_api_gateway_rest_api.openrouter_api.id
  stage_name    = var.api_gateway_stage_name

  access_log_settings {
    destination_arn = aws_cloudwatch_log_group.api_gateway_access_logs.arn
    format          = jsonencode({
      requestId      = "$context.requestId"
      ip             = "$context.identity.sourceIp"
      requestTime    = "$context.requestTime"
      httpMethod     = "$context.httpMethod"
      resourcePath   = "$context.resourcePath"
      status         = "$context.status"
      responseLength = "$context.responseLength"
    })
  }
}

resource "aws_cloudwatch_log_group" "api_gateway_access_logs" {
  name              = "/aws/apigateway/${var.project_name}-access-logs"
  retention_in_days = 7
}

# CloudWatch Log Group for Lambda
resource "aws_cloudwatch_log_group" "lambda_logs" {
  name              = "/aws/lambda/${var.lambda_function_name}"
  retention_in_days = 14
}

# Outputs
output "api_endpoint" {
  description = "API Gateway endpoint URL"
  value       = "https://${aws_api_gateway_rest_api.openrouter_api.id}.execute-api.${var.aws_region}.amazonaws.com/${var.api_gateway_stage_name}/query"
}

output "lambda_function_name" {
  description = "Lambda function name"
  value       = aws_lambda_function.openrouter_lambda.function_name
}

output "lambda_function_arn" {
  description = "Lambda function ARN"
  value       = aws_lambda_function.openrouter_lambda.arn
}

output "openrouter_api_key_secret_arn" {
  description = "OpenRouter API Key Secret ARN"
  value       = aws_secretsmanager_secret.openrouter_api_key.arn
}
