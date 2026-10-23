# pavukanez-backend

A serverless backend that receives user queries via API Gateway, calls OpenRouter LLM (free models), and returns generated responses.

## Architecture

```
Client → API Gateway (POST /query) → Lambda (Python) → OpenRouter API → Response
                                    ↓
                              Secrets Manager (API Key)
```

## Components

- **AWS Lambda** (Python 3.11) - Processes requests and calls OpenRouter
- **API Gateway** (REST API) - HTTP endpoint for receiving queries
- **AWS Secrets Manager** - Securely stores OpenRouter API key
- **IAM Roles/Policies** - Least privilege permissions
- **CloudWatch Logs** - Logging for Lambda and API Gateway

## Prerequisites

- AWS CLI configured with appropriate permissions
- Terraform >= 1.0 installed
- OpenRouter API key (get one at https://openrouter.ai)

## Quick Start

### 1. Configure Variables

```bash
cd terraform
cp terraform.tfvars.example terraform.tfvars
# Edit terraform.tfvars with your OpenRouter API key
```

### 2. Deploy Infrastructure

```bash
# Initialize Terraform
terraform init

# Plan deployment
terraform plan

# Apply deployment
terraform apply
```

### 3. Test the API

After deployment, you'll get an API endpoint URL. Test it with:

```bash
curl -X POST "https://<api-id>.execute-api.<region>.amazonaws.com/prod/query" \
  -H "Content-Type: application/json" \
  -d '{"query": "Hello, how are you?"}'
```

Expected response:
```json
{
  "response": "Hello! I'm doing well, thank you for asking...",
  "model": "openrouter/free",
  "usage": {
    "prompt_tokens": 10,
    "completion_tokens": 25,
    "total_tokens": 35
  }
}
```

## API Specification

### Endpoint
```
POST /query
```

### Request Body
```json
{
  "query": "Your question or prompt here",
  "model": "optional-model-override"  // Optional, defaults to openrouter/free
}
```

### Response (200 OK)
```json
{
  "response": "Generated response from LLM",
  "model": "model-name-used",
  "usage": {
    "prompt_tokens": 10,
    "completion_tokens": 50,
    "total_tokens": 60
  }
}
```

### Error Responses

**400 Bad Request**
```json
{"error": "Missing 'query' field in request body"}
```

**405 Method Not Allowed**
```json
{"error": "Method not allowed. Use POST."}
```

**500 Internal Server Error**
```json
{"error": "Internal server error: <details>"}
```

## Project Structure

```
pavukanez-backend/
├── terraform/
│   ├── main.tf                 # Main Terraform configuration
│   ├── variables.tf            # Input variables
│   ├── terraform.tfvars.example # Example variables file
│   └── outputs.tf              # Output values
├── lambda/
│   ├── src/
│   │   └── lambda_function.py  # Lambda handler code
│   └── requirements.txt        # Python dependencies (none needed)
└── README.md                   # This file
```

## Configuration Options

| Variable | Description | Default |
|----------|-------------|---------|
| `aws_region` | AWS region for deployment | `us-east-1` |
| `project_name` | Prefix for all resources | `pavukanez-backend` |
| `lambda_function_name` | Lambda function name | `pavukanez-backend-openrouter` |
| `openrouter_api_key` | **Required** - Your OpenRouter API key | - |
| `openrouter_model` | OpenRouter model to use | `openrouter/free` |
| `api_gateway_stage_name` | API Gateway stage name | `prod` |

## OpenRouter Models

The default model is `openrouter/free` which routes to free models. You can specify other models:

- `openrouter/free` - Free tier models
- `anthropic/claude-3-haiku` - Fast, affordable
- `openai/gpt-3.5-turbo` - Popular choice
- `meta-llama/llama-3-8b-instruct` - Open source
- And many more at https://openrouter.ai/models

## Security

- API key stored in AWS Secrets Manager (encrypted at rest)
- Lambda has least-privilege IAM policy (only Secrets Manager read)
- API Gateway logs access to CloudWatch
- No public S3 access

## Cleanup

To destroy all resources:

```bash
cd terraform
terraform destroy
```

## Local Development

To test the Lambda locally:

```bash
cd lambda/src
# Set environment variables
export OPENROUTER_API_KEY_SECRET_ARN="arn:aws:secretsmanager:..."
export OPENROUTER_MODEL="openrouter/free"
export OPENROUTER_BASE_URL="https://openrouter.ai/api/v1"

# Test with a mock event
python3 -c "
import lambda_function
event = {'httpMethod': 'POST', 'body': '{\"query\": \"test\"}'}
print(lambda_function.lambda_handler(event, None))
"
```

## License

MIT License