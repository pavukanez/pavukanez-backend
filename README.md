# pavukanez-backend

A serverless backend that receives user queries via Lambda Function URL, calls OpenRouter LLM (free models), and returns generated responses. **Uses only AWS Free Tier services.**

## Architecture

```
Client → Lambda Function URL (POST /) → Lambda (Python) → OpenRouter API → Response
                                         ↓
                                   Env Var (API Key)
```

## Components

- **AWS Lambda** (Python 3.11) - Processes requests and calls OpenRouter
- **Lambda Function URL** - Free HTTPS endpoint (no API Gateway needed)
- **Lambda Environment Variables** - Stores OpenRouter API key (no Secrets Manager)
- **IAM Roles/Policies** - Least privilege permissions
- **CloudWatch Logs** - Logging for Lambda

## Free Tier Eligibility

| Service | Free Tier Limit |
|---------|----------------|
| Lambda | 1M requests/month, 400K GB-seconds |
| Lambda Function URLs | 1M requests/month |
| CloudWatch Logs | 5GB ingestion, 5GB archive |
| S3 | 5GB standard storage |

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

After deployment, you'll get a Lambda Function URL. Test it with:

```bash
curl -X POST "https://<function-url>.lambda-url.<region>.on.aws/" \
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
POST /
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
│   └── terraform.tfvars.example # Example variables file
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

## OpenRouter Models

The default model is `openrouter/free` which routes to free models. You can specify other models:

- `openrouter/free` - Free tier models
- `anthropic/claude-3-haiku` - Fast, affordable
- `openai/gpt-3.5-turbo` - Popular choice
- `meta-llama/llama-3-8b-instruct` - Open source
- And many more at https://openrouter.ai/models

## Security

- API key stored in Lambda environment variable (encrypted at rest)
- Lambda has minimal IAM permissions (only CloudWatch Logs write)
- Lambda Function URL with CORS configured
- No public S3 access
- No API Gateway, no Secrets Manager - reduced attack surface

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
export OPENROUTER_API_KEY="your-openrouter-api-key"
export OPENROUTER_MODEL="openrouter/free"
export OPENROUTER_BASE_URL="https://openrouter.ai/api/v1"

# Test with a mock event (Lambda Function URL format)
python3 -c "
import lambda_function
event = {
    'requestContext': {'http': {'method': 'POST'}},
    'body': '{\"query\": \"test\"}',
    'isBase64Encoded': False
}
print(lambda_function.lambda_handler(event, None))
"
```

## License

MIT License