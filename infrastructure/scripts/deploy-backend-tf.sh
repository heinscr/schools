#!/bin/bash

# Backend Deployment Script (Terraform version)
# Packages and deploys the Python FastAPI backend to AWS Lambda

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Paths
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
BACKEND_DIR="$PROJECT_ROOT/backend"
TERRAFORM_DIR="$SCRIPT_DIR/../terraform"
DEPLOY_TEMP="$SCRIPT_DIR/.deploy-temp"

echo -e "${GREEN}=== Backend Deployment (Terraform) ===${NC}"
echo ""

# Check if terraform directory exists
if [ ! -d "$TERRAFORM_DIR" ]; then
    echo -e "${RED}Error: Terraform directory not found: $TERRAFORM_DIR${NC}"
    echo "Please run 'terraform apply' first"
    exit 1
fi

# Load configuration from Terraform outputs
echo "Loading Terraform outputs..."
cd "$TERRAFORM_DIR"

S3_BUCKET=$(terraform output -raw s3_bucket 2>/dev/null)
S3_PREFIX=$(terraform output -raw backend_s3_prefix 2>/dev/null)
FUNCTION_NAME=$(terraform output -raw lambda_function_name 2>/dev/null)
API_GATEWAY_ID=$(terraform output -raw api_gateway_id 2>/dev/null)
ROOT_RESOURCE_ID=$(terraform output -raw api_gateway_root_resource_id 2>/dev/null)
LAMBDA_ROLE_ARN=$(terraform output -raw lambda_role_arn 2>/dev/null)
REGION=$(terraform output -raw region 2>/dev/null)
API_ENDPOINT=$(terraform output -raw api_endpoint 2>/dev/null)

if [ -z "$S3_BUCKET" ]; then
    echo -e "${RED}Error: Could not read Terraform outputs${NC}"
    echo "Make sure you have run 'terraform apply' successfully"
    exit 1
fi

echo -e "${GREEN}✓ Configuration loaded${NC}"
echo "S3 Bucket: $S3_BUCKET"
echo "S3 Prefix: $S3_PREFIX"
echo "Lambda Function: $FUNCTION_NAME"
echo "API Gateway: $API_GATEWAY_ID"
echo "Region: $REGION"
echo ""

# Create temporary deployment directory
echo -e "${YELLOW}Step 1: Preparing deployment package${NC}"
rm -rf "$DEPLOY_TEMP"
mkdir -p "$DEPLOY_TEMP"

# Copy backend code
cp -r "$BACKEND_DIR"/* "$DEPLOY_TEMP/"
cd "$DEPLOY_TEMP"

# Create requirements if not exists (for minimal Lambda)
if [ ! -f "requirements.txt" ]; then
    echo "mangum==0.17.0" > requirements.txt
fi

# Install dependencies in deployment directory
echo "Installing Python dependencies..."
pip install -r requirements.txt -t . --upgrade > /dev/null 2>&1

# Add Lambda handler wrapper for FastAPI
cat > lambda_handler.py <<'EOF'
from mangum import Mangum
from main import app

# Mangum adapter for AWS Lambda
handler = Mangum(app, lifespan="off")
EOF

echo -e "${GREEN}✓ Deployment package prepared${NC}"
echo ""

echo -e "${YELLOW}Step 2: Creating deployment ZIP${NC}"
ZIP_FILE="backend-$(date +%Y%m%d-%H%M%S).zip"
zip -r "$ZIP_FILE" . -x "*.pyc" -x "*__pycache__*" -x "*.git*" -x "venv/*" > /dev/null

if [ ! -f "$ZIP_FILE" ]; then
    echo -e "${RED}Error: Failed to create ZIP file${NC}"
    exit 1
fi

ZIP_SIZE=$(du -h "$ZIP_FILE" | cut -f1)
echo -e "${GREEN}✓ ZIP created: $ZIP_FILE ($ZIP_SIZE)${NC}"
echo ""

echo -e "${YELLOW}Step 3: Uploading to S3${NC}"
S3_KEY="${S3_PREFIX}${ZIP_FILE}"
aws s3 cp "$ZIP_FILE" "s3://$S3_BUCKET/$S3_KEY" --region "$REGION"
echo -e "${GREEN}✓ Uploaded to s3://$S3_BUCKET/$S3_KEY${NC}"
echo ""

echo -e "${YELLOW}Step 4: Deploying Lambda function${NC}"

# Check if Lambda function exists
if aws lambda get-function --function-name "$FUNCTION_NAME" --region "$REGION" > /dev/null 2>&1; then
    echo "Updating existing Lambda function..."
    aws lambda update-function-code \
        --function-name "$FUNCTION_NAME" \
        --s3-bucket "$S3_BUCKET" \
        --s3-key "$S3_KEY" \
        --region "$REGION" > /dev/null

    echo "Waiting for update to complete..."
    aws lambda wait function-updated \
        --function-name "$FUNCTION_NAME" \
        --region "$REGION"
else
    echo "Creating new Lambda function..."

    # Wait a moment for IAM role to propagate
    sleep 5

    aws lambda create-function \
        --function-name "$FUNCTION_NAME" \
        --runtime python3.12 \
        --role "$LAMBDA_ROLE_ARN" \
        --handler lambda_handler.handler \
        --code S3Bucket="$S3_BUCKET",S3Key="$S3_KEY" \
        --timeout 30 \
        --memory-size 512 \
        --region "$REGION" \
        --environment "Variables={ENVIRONMENT=production}" > /dev/null

    echo "Waiting for function to be active..."
    aws lambda wait function-active \
        --function-name "$FUNCTION_NAME" \
        --region "$REGION"
fi

LAMBDA_ARN=$(aws lambda get-function \
    --function-name "$FUNCTION_NAME" \
    --region "$REGION" \
    --query 'Configuration.FunctionArn' \
    --output text)

echo -e "${GREEN}✓ Lambda function deployed${NC}"
echo "Function ARN: $LAMBDA_ARN"
echo ""

echo -e "${YELLOW}Step 5: Configuring API Gateway${NC}"

# Create {proxy+} resource if it doesn't exist
PROXY_RESOURCE_ID=$(aws apigateway get-resources \
    --rest-api-id "$API_GATEWAY_ID" \
    --region "$REGION" \
    --query 'items[?pathPart==`{proxy+}`].id' \
    --output text)

if [ -z "$PROXY_RESOURCE_ID" ]; then
    echo "Creating proxy resource..."
    PROXY_RESOURCE_ID=$(aws apigateway create-resource \
        --rest-api-id "$API_GATEWAY_ID" \
        --parent-id "$ROOT_RESOURCE_ID" \
        --path-part "{proxy+}" \
        --region "$REGION" \
        --query 'id' \
        --output text)
fi

# Create ANY method if it doesn't exist
aws apigateway put-method \
    --rest-api-id "$API_GATEWAY_ID" \
    --resource-id "$PROXY_RESOURCE_ID" \
    --http-method ANY \
    --authorization-type NONE \
    --region "$REGION" > /dev/null 2>&1 || echo "Method may already exist"

# Set Lambda integration
LAMBDA_URI="arn:aws:apigateway:${REGION}:lambda:path/2015-03-31/functions/${LAMBDA_ARN}/invocations"

aws apigateway put-integration \
    --rest-api-id "$API_GATEWAY_ID" \
    --resource-id "$PROXY_RESOURCE_ID" \
    --http-method ANY \
    --type AWS_PROXY \
    --integration-http-method POST \
    --uri "$LAMBDA_URI" \
    --region "$REGION" > /dev/null

# Add Lambda permission for API Gateway
aws lambda add-permission \
    --function-name "$FUNCTION_NAME" \
    --statement-id "apigateway-invoke-$(date +%s)" \
    --action lambda:InvokeFunction \
    --principal apigateway.amazonaws.com \
    --source-arn "arn:aws:execute-api:${REGION}:*:${API_GATEWAY_ID}/*/*" \
    --region "$REGION" > /dev/null 2>&1 || echo "Permission may already exist"

# Deploy API
DEPLOYMENT_ID=$(aws apigateway create-deployment \
    --rest-api-id "$API_GATEWAY_ID" \
    --stage-name prod \
    --region "$REGION" \
    --query 'id' \
    --output text)

echo -e "${GREEN}✓ API Gateway configured and deployed${NC}"
echo "Deployment ID: $DEPLOYMENT_ID"
echo ""

# Clean up
cd "$SCRIPT_DIR"
rm -rf "$DEPLOY_TEMP"

echo -e "${GREEN}=== Backend Deployment Complete ===${NC}"
echo ""
echo "API Endpoint: $API_ENDPOINT"
echo "Test the API:"
echo "  curl $API_ENDPOINT/"
echo ""
echo "View logs:"
echo "  aws logs tail /aws/lambda/$FUNCTION_NAME --follow"
