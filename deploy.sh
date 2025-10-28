#!/bin/bash
# Deployment script for MA Teachers Contracts application

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}=== MA Teachers Contracts Deployment ===${NC}\n"

# Check if we're in the right directory
if [ ! -f "deploy.sh" ]; then
    echo -e "${RED}Error: Please run this script from the project root directory${NC}"
    exit 1
fi

# Get Terraform outputs
echo -e "${YELLOW}Getting infrastructure configuration...${NC}"
cd infrastructure/terraform

if [ ! -f "terraform.tfstate" ]; then
    echo -e "${RED}Error: Terraform state not found. Please run 'terraform apply' first.${NC}"
    exit 1
fi

S3_BUCKET=$(terraform output -raw s3_bucket)
LAMBDA_FUNCTION_NAME=$(terraform output -raw lambda_function_name)
LAMBDA_ROLE_ARN=$(terraform output -raw lambda_role_arn)
AWS_REGION=$(terraform output -raw region)
DYNAMODB_TABLE=$(terraform output -raw dynamodb_districts_table_name)
CLOUDFRONT_ID=$(terraform output -raw cloudfront_distribution_id)
API_GATEWAY_ID=$(terraform output -raw api_gateway_id)

echo -e "${GREEN}✓ Configuration loaded${NC}"
echo "  S3 Bucket: $S3_BUCKET"
echo "  Lambda Function: $LAMBDA_FUNCTION_NAME"
echo "  Region: $AWS_REGION"
echo "  DynamoDB Table: $DYNAMODB_TABLE"
echo ""

cd ../..

# Deploy Backend
echo -e "${YELLOW}=== Deploying Backend ===${NC}"
cd backend

# Create deployment package
echo "Creating Lambda deployment package..."
rm -rf package lambda-deployment.zip 2>/dev/null || true

# Install dependencies
pip install -r requirements.txt -t package/ --quiet

# Copy application code
cp -r *.py package/
[ -d "services" ] && cp -r services package/

# Create zip
cd package
zip -r ../lambda-deployment.zip . -q
cd ..

echo -e "${GREEN}✓ Lambda package created${NC}"

# Upload to S3
echo "Uploading Lambda package to S3..."
aws s3 cp lambda-deployment.zip s3://$S3_BUCKET/backend/lambda-deployment.zip --region $AWS_REGION

echo -e "${GREEN}✓ Lambda package uploaded${NC}"

# Check if Lambda function exists
if aws lambda get-function --function-name $LAMBDA_FUNCTION_NAME --region $AWS_REGION > /dev/null 2>&1; then
    echo "Updating existing Lambda function..."
    aws lambda update-function-code \
        --function-name $LAMBDA_FUNCTION_NAME \
        --s3-bucket $S3_BUCKET \
        --s3-key backend/lambda-deployment.zip \
        --region $AWS_REGION \
        --output json > /dev/null

    # Update environment variables
    aws lambda update-function-configuration \
        --function-name $LAMBDA_FUNCTION_NAME \
        --environment "Variables={AWS_REGION=$AWS_REGION,DYNAMODB_DISTRICTS_TABLE=$DYNAMODB_TABLE}" \
        --region $AWS_REGION \
        --output json > /dev/null
else
    echo "Creating new Lambda function..."
    aws lambda create-function \
        --function-name $LAMBDA_FUNCTION_NAME \
        --runtime python3.12 \
        --role $LAMBDA_ROLE_ARN \
        --handler main.handler \
        --code S3Bucket=$S3_BUCKET,S3Key=backend/lambda-deployment.zip \
        --environment "Variables={AWS_REGION=$AWS_REGION,DYNAMODB_DISTRICTS_TABLE=$DYNAMODB_TABLE}" \
        --timeout 30 \
        --memory-size 512 \
        --region $AWS_REGION \
        --output json > /dev/null
fi

echo -e "${GREEN}✓ Lambda function deployed${NC}"

# Wait for Lambda to be ready
echo "Waiting for Lambda to be ready..."
aws lambda wait function-updated --function-name $LAMBDA_FUNCTION_NAME --region $AWS_REGION 2>/dev/null || true

cd ..

# Deploy Frontend
echo -e "\n${YELLOW}=== Deploying Frontend ===${NC}"
cd frontend

# Build production bundle
echo "Building frontend..."
npm run build

echo -e "${GREEN}✓ Frontend built${NC}"

# Upload to S3
echo "Uploading frontend to S3..."
aws s3 sync dist/ s3://$S3_BUCKET/frontend/ --delete --region $AWS_REGION

echo -e "${GREEN}✓ Frontend uploaded${NC}"

# Invalidate CloudFront cache
echo "Invalidating CloudFront cache..."
aws cloudfront create-invalidation \
    --distribution-id $CLOUDFRONT_ID \
    --paths "/*" \
    --region $AWS_REGION \
    --output json > /dev/null

echo -e "${GREEN}✓ CloudFront cache invalidated${NC}"

cd ..

# Configure API Gateway (if needed)
echo -e "\n${YELLOW}=== Configuring API Gateway ===${NC}"

# Check if API Gateway is configured
INTEGRATION_EXISTS=$(aws apigateway get-integrations \
    --api-id $API_GATEWAY_ID \
    --region $AWS_REGION \
    2>/dev/null | grep -c "integrationId" || echo "0")

if [ "$INTEGRATION_EXISTS" -eq "0" ]; then
    echo -e "${YELLOW}Note: API Gateway needs manual configuration. See docs/DEPLOYMENT_GUIDE.md${NC}"
else
    echo -e "${GREEN}✓ API Gateway already configured${NC}"
fi

# Summary
echo -e "\n${GREEN}=== Deployment Complete! ===${NC}\n"

CLOUDFRONT_DOMAIN=$(cd infrastructure/terraform && terraform output -raw cloudfront_domain)
echo "Frontend URL: https://$CLOUDFRONT_DOMAIN"
echo "Custom Domain: https://school.crackpow.com (if DNS configured)"
echo ""
echo "Next steps:"
echo "1. Update DNS CNAME for school.crackpow.com → $CLOUDFRONT_DOMAIN"
echo "2. Load sample data: cd backend && python init_dynamodb_sample_data.py"
echo "3. Test the application"
echo ""
