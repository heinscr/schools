#!/bin/bash

# Frontend Deployment Script (Terraform version)
# Builds and deploys the React frontend to S3 and CloudFront

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Paths
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
FRONTEND_DIR="$PROJECT_ROOT/frontend"
TERRAFORM_DIR="$SCRIPT_DIR/../terraform"

echo -e "${GREEN}=== Frontend Deployment (Terraform) ===${NC}"
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
S3_PREFIX=$(terraform output -raw frontend_s3_prefix 2>/dev/null)
CF_DISTRIBUTION_ID=$(terraform output -raw cloudfront_distribution_id 2>/dev/null)
REGION=$(terraform output -raw region 2>/dev/null)
API_ENDPOINT=$(terraform output -raw api_endpoint 2>/dev/null)
CLOUDFRONT_DOMAIN=$(terraform output -raw cloudfront_domain 2>/dev/null)

if [ -z "$S3_BUCKET" ]; then
    echo -e "${RED}Error: Could not read Terraform outputs${NC}"
    echo "Make sure you have run 'terraform apply' successfully"
    exit 1
fi

echo -e "${GREEN}✓ Configuration loaded${NC}"
echo "S3 Bucket: $S3_BUCKET"
echo "S3 Prefix: $S3_PREFIX"
echo "CloudFront distribution: $CF_DISTRIBUTION_ID"
echo "Region: $REGION"
echo ""

# Check if frontend directory exists
if [ ! -d "$FRONTEND_DIR" ]; then
    echo -e "${RED}Error: Frontend directory not found: $FRONTEND_DIR${NC}"
    exit 1
fi

cd "$FRONTEND_DIR"

# Create .env.production with API endpoint
echo -e "${YELLOW}Step 1: Configuring environment${NC}"
cat > .env.production <<EOF
VITE_API_URL=$API_ENDPOINT
EOF
echo -e "${GREEN}✓ Environment configured${NC}"
echo "API URL: $API_ENDPOINT"
echo ""

# Install dependencies if needed
if [ ! -d "node_modules" ]; then
    echo -e "${YELLOW}Step 2: Installing dependencies${NC}"
    npm install
    echo -e "${GREEN}✓ Dependencies installed${NC}"
    echo ""
else
    echo -e "${GREEN}✓ Dependencies already installed${NC}"
    echo ""
fi

# Build the frontend
echo -e "${YELLOW}Step 3: Building frontend${NC}"
npm run build

if [ ! -d "dist" ]; then
    echo -e "${RED}Error: Build failed - dist directory not found${NC}"
    exit 1
fi

echo -e "${GREEN}✓ Frontend built successfully${NC}"
echo ""

# Sync to S3
echo -e "${YELLOW}Step 4: Uploading to S3${NC}"
S3_PATH="s3://$S3_BUCKET/${S3_PREFIX}"

aws s3 sync dist/ "$S3_PATH" \
    --region "$REGION" \
    --delete \
    --cache-control "public, max-age=31536000" \
    --exclude "*.html" \
    --exclude "index.html"

# Upload HTML files with no-cache
aws s3 sync dist/ "$S3_PATH" \
    --region "$REGION" \
    --delete \
    --cache-control "no-cache" \
    --exclude "*" \
    --include "*.html"

echo -e "${GREEN}✓ Files uploaded to S3 at $S3_PATH${NC}"
echo ""

# Invalidate CloudFront cache
if [ -n "$CF_DISTRIBUTION_ID" ]; then
    echo -e "${YELLOW}Step 5: Invalidating CloudFront cache${NC}"

    INVALIDATION_ID=$(aws cloudfront create-invalidation \
        --distribution-id "$CF_DISTRIBUTION_ID" \
        --paths "/*" \
        --query 'Invalidation.Id' \
        --output text)

    echo -e "${GREEN}✓ CloudFront invalidation created${NC}"
    echo "Invalidation ID: $INVALIDATION_ID"
    echo ""
    echo "Note: CloudFront invalidation may take a few minutes to complete"
else
    echo -e "${YELLOW}Note: CloudFront distribution not configured${NC}"
    echo ""
fi

# Clean up
rm -f .env.production

echo -e "${GREEN}=== Frontend Deployment Complete ===${NC}"
echo ""
echo "Website URL: https://$CLOUDFRONT_DOMAIN"
echo ""
echo "Test the deployment:"
echo "  curl https://$CLOUDFRONT_DOMAIN"
