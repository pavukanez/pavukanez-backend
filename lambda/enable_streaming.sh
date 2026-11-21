#!/bin/bash
# Enable Lambda Function URL response streaming mode
# Run this after deploying the Lambda function
# Requires: lambda:ListFunctionUrlConfigs, lambda:UpdateFunctionUrlConfig, lambda:CreateFunctionUrlConfig

set -e

FUNCTION_NAME="pavukanez-backend-openrouter"
REGION="us-east-2"

echo "Checking Function URL configuration for $FUNCTION_NAME..."

# Check if Function URL exists
FUNCTION_URL=$(aws lambda list-function-url-configs \
  --function-name "$FUNCTION_NAME" \
  --region "$REGION" \
  --query 'FunctionUrlConfigs[0].FunctionUrl' \
  --output text 2>/dev/null)
LIST_EXIT=$?

if [ $LIST_EXIT -ne 0 ]; then
  echo "Error: Failed to list Function URLs."
  echo "Ensure your AWS credentials have lambda:ListFunctionUrlConfigs permission."
  echo "See lambda/iam-policy-streaming.json for required policy."
  exit 1
fi

if [ "$FUNCTION_URL" = "None" ] || [ -z "$FUNCTION_URL" ]; then
  echo "No Function URL found. Creating one with RESPONSE_STREAM mode..."
  aws lambda create-function-url-config \
    --function-name "$FUNCTION_NAME" \
    --region "$REGION" \
    --auth-type AWS_IAM \
    --invoke-mode RESPONSE_STREAM \
    --cors '{"AllowOrigins":["*"],"AllowMethods":["POST"],"AllowHeaders":["Content-Type"]}'
  
  if [ $? -eq 0 ]; then
    echo "Function URL created with streaming enabled!"
    # Get the new URL
    NEW_URL=$(aws lambda list-function-url-configs \
      --function-name "$FUNCTION_NAME" \
      --region "$REGION" \
      --query 'FunctionUrlConfigs[0].FunctionUrl' \
      --output text)
    echo "Function URL: $NEW_URL"
  else
    echo "Error: Failed to create Function URL."
    echo "Ensure your AWS credentials have lambda:CreateFunctionUrlConfig permission."
    exit 1
  fi
else
  echo "Function URL found: $FUNCTION_URL"
  echo "Updating to RESPONSE_STREAM mode..."
  aws lambda update-function-url-config \
    --function-name "$FUNCTION_NAME" \
    --region "$REGION" \
    --invoke-mode RESPONSE_STREAM
  
  if [ $? -eq 0 ]; then
    echo "Function URL streaming mode enabled!"
  else
    echo "Error: Failed to update Function URL."
    echo "Ensure your AWS credentials have lambda:UpdateFunctionUrlConfig permission."
    exit 1
  fi
fi

echo "Done! Function URL is now configured for response streaming."