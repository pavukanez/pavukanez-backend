#!/bin/bash
# Enable Lambda Function URL response streaming mode
# Run this after deploying the Lambda function

set -e

FUNCTION_NAME="pavukanez-backend-openrouter"
REGION="us-east-2"

echo "Checking Function URL configuration for $FUNCTION_NAME..."

FUNCTION_URL=$(aws lambda list-function-url-configs \
  --function-name "$FUNCTION_NAME" \
  --region "$REGION" \
  --query 'FunctionUrlConfigs[0].FunctionUrl' \
  --output text)

if [ "$FUNCTION_URL" = "None" ] || [ -z "$FUNCTION_URL" ]; then
  echo "No Function URL found. Creating one with RESPONSE_STREAM mode..."
  aws lambda create-function-url-config \
    --function-name "$FUNCTION_NAME" \
    --region "$REGION" \
    --auth-type AWS_IAM \
    --invoke-mode RESPONSE_STREAM \
    --cors '{"AllowOrigins":["*"],"AllowMethods":["POST"],"AllowHeaders":["Content-Type"]}'
else
  echo "Function URL found: $FUNCTION_URL"
  echo "Updating to RESPONSE_STREAM mode..."
  aws lambda update-function-url-config \
    --function-name "$FUNCTION_NAME" \
    --region "$REGION" \
    --invoke-mode RESPONSE_STREAM
fi

echo "Done! Function URL is now configured for response streaming."