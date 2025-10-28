#!/bin/bash
# Simplified deployment script - Terraform now manages Lambda and API Gateway

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${GREEN}=== MA Teachers Contracts Deployment ===${NC}\n"

# Get Terraform outputs
echo -e "${YELLOW}Getting infrastructure configuration...${NC}"
cd infrastructure/terraform

S3_BUCKET=$(terraform output -raw s3_bucket)
AWS_REGION=$(terraform output -raw region)
CLOUDFRONT_ID=$(terraform output -raw cloudfront_distribution_id)

echo -e "${GREEN}✓ Configuration loaded${NC}"
echo "  S3 Bucket: $S3_BUCKET"
echo "  Region: $AWS_REGION"
echo ""

cd ../..

# Deploy Backend
echo -e "${YELLOW}=== Deploying Backend ===${NC}"
cd backend

echo "Creating Lambda deployment package..."
rm -rf package lambda-deployment.zip 2>/dev/null || true
pip install -r requirements.txt -t package/ --quiet
cp -r *.py package/
[ -d "services" ] && cp -r services package/
cd package && zip -r ../lambda-deployment.zip . -q && cd ..

echo -e "${GREEN}✓ Lambda package created${NC}"

echo "Uploading to S3..."
aws s3 cp lambda-deployment.zip s3://$S3_BUCKET/backend/lambda-deployment.zip --region $AWS_REGION

echo -e "${GREEN}✓ Backend uploaded${NC}"

cd ..

# Deploy Frontend
echo -e "\n${YELLOW}=== Deploying Frontend ===${NC}"
cd frontend

echo "Building frontend..."
npm run build

echo -e "${GREEN}✓ Frontend built${NC}"

echo "Uploading to S3..."
aws s3 sync dist/ s3://$S3_BUCKET/frontend/ --delete --region $AWS_REGION

echo -e "${GREEN}✓ Frontend uploaded${NC}"

echo "Invalidating CloudFront cache..."
aws cloudfront create-invalidation \
    --distribution-id $CLOUDFRONT_ID \
    --paths "/*" \
    --region $AWS_REGION \
    --output json > /dev/null

echo -e "${GREEN}✓ CloudFront cache invalidated${NC}"

cd ..

# Update Lambda
echo -e "\n${YELLOW}=== Updating Lambda Function ===${NC}"
cd infrastructure/terraform

terraform apply -auto-approve -target=aws_lambda_function.api

echo -e "${GREEN}✓ Lambda function updated${NC}"

# Summary
echo -e "\n${GREEN}=== Deployment Complete! ===${NC}\n"

CLOUDFRONT_DOMAIN=$(terraform output -raw cloudfront_domain)
API_ENDPOINT=$(terraform output -raw api_endpoint)

echo "Frontend URL: https://$CLOUDFRONT_DOMAIN"
echo "API Endpoint: $API_ENDPOINT"
echo ""
echo "Your application is live!"
echo ""
