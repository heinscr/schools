#!/bin/bash
# Deployment script for MA Teachers Contracts application

set -e  # Exit on error (will be temporarily disabled around tests to capture exit codes)

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

# Parse flags
RUN_TESTS=true
for arg in "$@"; do
    case "$arg" in
        --no-tests)
            RUN_TESTS=false
            shift
            ;;
        *)
            ;;
    esac
done

if [ "$RUN_TESTS" = false ]; then
    echo -e "${YELLOW}Skipping tests due to --no-tests flag${NC}"
else
    echo -e "${YELLOW}=== Running Test Suites (Backend & Frontend) ===${NC}"

    # Allow commands to fail so we can prompt
    set +e

    BACKEND_TEST_EXIT=0
    FRONTEND_TEST_EXIT=0

    # Backend tests
    if [ -d "backend" ]; then
        echo -e "${YELLOW}- Backend: setting up venv, installing dev requirements, and running tests...${NC}"
        pushd backend >/dev/null

        # Ensure we have Python
        PYTHON_BIN="python3"
        if ! command -v $PYTHON_BIN >/dev/null 2>&1; then
            PYTHON_BIN="python"
        fi

        # Create a virtual environment if it doesn't exist (avoids PEP 668 issues)
        if [ ! -d "venv" ] || [ ! -f "venv/bin/activate" ]; then
            $PYTHON_BIN -m venv venv
        fi

        # Activate venv
        # shellcheck disable=SC1091
        source venv/bin/activate

        # Upgrade pip tooling quietly and install dev requirements inside the venv
        python -m pip install --upgrade pip setuptools wheel -q
        if [ -f "requirements-dev.txt" ]; then
            python -m pip install -r requirements-dev.txt -q
        fi

        # Run tests
        pytest -q
        BACKEND_TEST_EXIT=$?

        # Deactivate venv
        deactivate

        popd >/dev/null
    fi

    # Frontend tests
    if [ -d "frontend" ]; then
        echo -e "${YELLOW}- Frontend: installing deps and running tests...${NC}"
        pushd frontend >/dev/null
        # Install deps quietly; do not fail build due to audit/funding noise
        if command -v npm >/dev/null 2>&1; then
            npm install --no-audit --no-fund -s >/dev/null 2>&1
            npm run test -s
            FRONTEND_TEST_EXIT=$?
        else
            echo -e "${RED}npm not found; skipping frontend tests${NC}"
            FRONTEND_TEST_EXIT=1
        fi
        popd >/dev/null
    fi

    # Summarize and prompt on failures
    if [ $BACKEND_TEST_EXIT -ne 0 ] || [ $FRONTEND_TEST_EXIT -ne 0 ]; then
        echo -e "${RED}One or more test suites failed.${NC}"
        echo "Backend tests exit code: $BACKEND_TEST_EXIT"
        echo "Frontend tests exit code: $FRONTEND_TEST_EXIT"
        echo ""
        read -r -p "Continue deployment anyway? [y/N]: " CONFIRM
        case "$CONFIRM" in
            y|Y|yes|YES)
                echo -e "${YELLOW}Proceeding with deployment despite failing tests...${NC}"
                ;;
            *)
                echo -e "${RED}Deployment cancelled due to failing tests.${NC}"
                exit 1
                ;;
        esac
    else
        echo -e "${GREEN}✓ All tests passed. Continuing with deployment.${NC}"
    fi

    # Re-enable exit-on-error for deployment steps
    set -e
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
CLOUDFRONT_DOMAIN=$(terraform output -raw cloudfront_domain)
API_GATEWAY_ID=$(terraform output -raw api_gateway_id)
API_ENDPOINT=$(terraform output -raw api_endpoint)
SALARY_API_ENDPOINT=$(terraform output -raw api_endpoint)
SALARY_LAMBDA_FUNCTION_NAME=$(terraform output -raw salaries_lambda_function_name)
SALARIES_TABLE_NAME=$(terraform output -raw salaries_table_name)
SCHEDULES_TABLE_NAME=$(terraform output -raw schedules_table_name)

echo -e "${GREEN}✓ Configuration loaded${NC}"
echo "  S3 Bucket: $S3_BUCKET"
echo "  Lambda Function: $LAMBDA_FUNCTION_NAME"
echo "  Salary Lambda Function: $SALARY_LAMBDA_FUNCTION_NAME"
echo "  Region: $AWS_REGION"
echo "  DynamoDB Table: $DYNAMODB_TABLE"
echo "  CloudFront Domain: $CLOUDFRONT_DOMAIN"
echo "  API Endpoint: $API_ENDPOINT"
echo "  Salary API Endpoint: $SALARY_API_ENDPOINT"
echo ""

cd ../..

# Deploy Backend
echo -e "${YELLOW}=== Deploying Backend ===${NC}"

# 1. Package Python Lambda (districts API)
echo "Creating Python Lambda deployment package..."
cd backend
rm -rf package lambda-deployment.zip 2>/dev/null || true

# Install dependencies (use python -m pip to avoid PEP 668 issues)
if command -v python3 >/dev/null 2>&1; then
    PIP_BUILD_CMD="python3 -m pip"
else
    PIP_BUILD_CMD="pip"
fi
$PIP_BUILD_CMD install -r requirements.txt -t package/ --quiet

# Copy application code
cp -r *.py package/
[ -d "services" ] && cp -r services package/
[ -d "utils" ] && cp -r utils package/

# Create zip
cd package
zip -r ../lambda-deployment.zip . -q
cd ..

echo -e "${GREEN}✓ Python Lambda package created${NC}"

cd ..

# 2. Package Python Lambda (salary API)
echo "Creating salary Lambda deployment package..."
cd backend

# Create a temporary directory for packaging
mkdir -p salary_package

# Copy the salary Lambda handler, config, and utils
cp salaries.py salary_package/
cp config.py salary_package/
[ -d "utils" ] && cp -r utils salary_package/

# Install dependencies (boto3 is included in Lambda runtime, but we might need others)
# For now, just package the handler since it only uses boto3
cd salary_package

# Remove old zip if exists
rm -f ../salaries.zip

# Create zip file
zip -r ../salaries.zip . -q

cd ..

# Clean up
rm -rf salary_package

echo -e "${GREEN}✓ Salary Lambda package created${NC}"

cd ..

# Upload to S3
echo "Uploading Lambda packages to S3..."
cd backend
aws s3 cp lambda-deployment.zip s3://$S3_BUCKET/backend/lambda-deployment.zip --region $AWS_REGION
aws s3 cp salaries.zip s3://$S3_BUCKET/backend/salaries.zip --region $AWS_REGION
cd ..

echo -e "${GREEN}✓ Lambda packages uploaded${NC}"

# Check if Lambda function exists
if aws lambda get-function --function-name $LAMBDA_FUNCTION_NAME --region $AWS_REGION > /dev/null 2>&1; then
    echo "Updating existing Lambda function code..."

    # Wait for any pending updates to complete first
    echo "Checking if Lambda is ready..."
    aws lambda wait function-updated --function-name $LAMBDA_FUNCTION_NAME --region $AWS_REGION 2>/dev/null || true

    # Update function code
    aws lambda update-function-code \
        --function-name $LAMBDA_FUNCTION_NAME \
        --s3-bucket $S3_BUCKET \
        --s3-key backend/lambda-deployment.zip \
        --region $AWS_REGION \
        --output json > /dev/null

    echo "Waiting for code update to complete..."
    aws lambda wait function-updated --function-name $LAMBDA_FUNCTION_NAME --region $AWS_REGION 2>/dev/null || true

    # Update environment variables
    echo "Updating Lambda configuration..."

    # Get API key from Terraform output (managed by Terraform)
    API_KEY=$(cd infrastructure/terraform && terraform output -raw api_key 2>/dev/null || echo "")

    # Get CUSTOM_DOMAIN from backend/.env if it exists
    CUSTOM_DOMAIN=""
    if [ -f "backend/.env" ]; then
        CUSTOM_DOMAIN=$(grep -E "^CUSTOM_DOMAIN=" backend/.env | cut -d '=' -f2- | tr -d '\r\n')
    fi

    if [ -z "$API_KEY" ]; then
        echo -e "${YELLOW}Warning: API_KEY not found in Terraform. Write operations will be disabled.${NC}"
        ENV_VARS="DYNAMODB_DISTRICTS_TABLE=$DYNAMODB_TABLE,CLOUDFRONT_DOMAIN=$CLOUDFRONT_DOMAIN"
    else
        ENV_VARS="DYNAMODB_DISTRICTS_TABLE=$DYNAMODB_TABLE,CLOUDFRONT_DOMAIN=$CLOUDFRONT_DOMAIN,API_KEY=$API_KEY"
    fi

    # Add CUSTOM_DOMAIN if it exists
    if [ -n "$CUSTOM_DOMAIN" ]; then
        ENV_VARS="$ENV_VARS,CUSTOM_DOMAIN=$CUSTOM_DOMAIN"
        echo "  Using custom domain: $CUSTOM_DOMAIN"
    fi

    aws lambda update-function-configuration \
        --function-name $LAMBDA_FUNCTION_NAME \
        --environment "Variables={$ENV_VARS}" \
        --region $AWS_REGION \
        --output json > /dev/null

    echo "Waiting for configuration update to complete..."
    aws lambda wait function-updated --function-name $LAMBDA_FUNCTION_NAME --region $AWS_REGION 2>/dev/null || true
else
    echo "Creating new Lambda function..."

    # Get API key from Terraform output (managed by Terraform)
    API_KEY=$(cd infrastructure/terraform && terraform output -raw api_key 2>/dev/null || echo "")

    # Get CUSTOM_DOMAIN from backend/.env if it exists
    CUSTOM_DOMAIN=""
    if [ -f "backend/.env" ]; then
        CUSTOM_DOMAIN=$(grep -E "^CUSTOM_DOMAIN=" backend/.env | cut -d '=' -f2- | tr -d '\r\n')
    fi

    if [ -z "$API_KEY" ]; then
        echo -e "${YELLOW}Warning: API_KEY not found in Terraform. Write operations will be disabled.${NC}"
        ENV_VARS="DYNAMODB_DISTRICTS_TABLE=$DYNAMODB_TABLE,CLOUDFRONT_DOMAIN=$CLOUDFRONT_DOMAIN"
    else
        ENV_VARS="DYNAMODB_DISTRICTS_TABLE=$DYNAMODB_TABLE,CLOUDFRONT_DOMAIN=$CLOUDFRONT_DOMAIN,API_KEY=$API_KEY"
    fi

    # Add CUSTOM_DOMAIN if it exists
    if [ -n "$CUSTOM_DOMAIN" ]; then
        ENV_VARS="$ENV_VARS,CUSTOM_DOMAIN=$CUSTOM_DOMAIN"
        echo "  Using custom domain: $CUSTOM_DOMAIN"
    fi

    aws lambda create-function \
        --function-name $LAMBDA_FUNCTION_NAME \
        --runtime python3.12 \
        --role $LAMBDA_ROLE_ARN \
        --handler main.handler \
        --code S3Bucket=$S3_BUCKET,S3Key=backend/lambda-deployment.zip \
        --environment "Variables={$ENV_VARS}" \
        --timeout 30 \
        --memory-size 512 \
        --region $AWS_REGION \
        --output json > /dev/null

    echo "Waiting for Lambda to be ready..."
    aws lambda wait function-updated --function-name $LAMBDA_FUNCTION_NAME --region $AWS_REGION 2>/dev/null || true
fi

echo -e "${GREEN}✓ Lambda function deployed${NC}"

# Deploy Salary Lambda
echo -e "\n${YELLOW}=== Deploying Salary Lambda ===${NC}"

# Check if Salary Lambda function exists
if aws lambda get-function --function-name $SALARY_LAMBDA_FUNCTION_NAME --region $AWS_REGION > /dev/null 2>&1; then
    echo "Updating existing Salary Lambda function code..."

    # Wait for any pending updates to complete first
    echo "Checking if Salary Lambda is ready..."
    aws lambda wait function-updated --function-name $SALARY_LAMBDA_FUNCTION_NAME --region $AWS_REGION 2>/dev/null || true

    # Update function code
    aws lambda update-function-code \
        --function-name $SALARY_LAMBDA_FUNCTION_NAME \
        --s3-bucket $S3_BUCKET \
        --s3-key backend/salaries.zip \
        --region $AWS_REGION \
        --output json > /dev/null

    echo "Waiting for code update to complete..."
    aws lambda wait function-updated --function-name $SALARY_LAMBDA_FUNCTION_NAME --region $AWS_REGION 2>/dev/null || true

    # Update environment variables
    echo "Updating Salary Lambda configuration..."
    
    # Get CUSTOM_DOMAIN from backend/.env if it exists
    CUSTOM_DOMAIN=""
    if [ -f "backend/.env" ]; then
        CUSTOM_DOMAIN=$(grep -E "^CUSTOM_DOMAIN=" backend/.env | cut -d '=' -f2- | tr -d '\r\n')
    fi
    
    SALARY_ENV_VARS="SALARIES_TABLE_NAME=$SALARIES_TABLE_NAME,SCHEDULES_TABLE_NAME=$SCHEDULES_TABLE_NAME,DISTRICTS_TABLE_NAME=$DYNAMODB_TABLE"
    
    # Add CUSTOM_DOMAIN if it exists
    if [ -n "$CUSTOM_DOMAIN" ]; then
        SALARY_ENV_VARS="$SALARY_ENV_VARS,CUSTOM_DOMAIN=$CUSTOM_DOMAIN"
        echo "  Using custom domain: $CUSTOM_DOMAIN"
    fi
    
    aws lambda update-function-configuration \
        --function-name $SALARY_LAMBDA_FUNCTION_NAME \
        --environment "Variables={$SALARY_ENV_VARS}" \
        --region $AWS_REGION \
        --output json > /dev/null

    echo "Waiting for configuration update to complete..."
    aws lambda wait function-updated --function-name $SALARY_LAMBDA_FUNCTION_NAME --region $AWS_REGION 2>/dev/null || true
else
    echo -e "${YELLOW}Salary Lambda function not found. It should be created by Terraform.${NC}"
fi

echo -e "${GREEN}✓ Salary Lambda function deployed${NC}"

# Deploy Frontend

echo -e "\n${YELLOW}=== Deploying Frontend ===${NC}"
cd frontend

# Copy filtered GeoJSON to public for deployment
echo "Copying geojson.json to frontend/public/geojson.json..."
cp ../data/geojson.json public/geojson.json

# Build production bundle with API endpoints from Terraform
echo "Building frontend with API endpoints:"
echo "  District API: $API_ENDPOINT"
echo "  Salary API: $SALARY_API_ENDPOINT"
# Vite only exposes variables starting with VITE_. Set both for compatibility
VITE_API_URL=$API_ENDPOINT \
VITE_DISTRICT_API_URL=$API_ENDPOINT \
VITE_SALARY_API_URL=$SALARY_API_ENDPOINT \
npm run build

echo -e "${GREEN}✓ Frontend built${NC}"

# Generate config.json from Terraform outputs
echo "Generating config.json with Cognito configuration..."
cd ../infrastructure/terraform

COGNITO_USER_POOL_ID=$(terraform output -raw cognito_user_pool_id 2>/dev/null || echo "")
COGNITO_CLIENT_ID=$(terraform output -raw cognito_client_id 2>/dev/null || echo "")
COGNITO_REGION=$(terraform output -raw region 2>/dev/null || echo "us-east-1")
COGNITO_DOMAIN=$(terraform output -raw cognito_domain 2>/dev/null || echo "")

cd ../../frontend

if [ -n "$COGNITO_USER_POOL_ID" ] && [ -n "$COGNITO_CLIENT_ID" ]; then
    cat > dist/config.json <<EOF
{
  "apiUrl": "$API_ENDPOINT",
  "cognitoUserPoolId": "$COGNITO_USER_POOL_ID",
  "cognitoClientId": "$COGNITO_CLIENT_ID",
  "cognitoRegion": "$COGNITO_REGION",
  "cognitoDomain": "$COGNITO_DOMAIN.auth.$COGNITO_REGION.amazoncognito.com"
}
EOF
    echo -e "${GREEN}✓ config.json generated with Cognito configuration${NC}"
else
    # Fallback for environments without Cognito
    cat > dist/config.json <<EOF
{
  "apiUrl": "$API_ENDPOINT"
}
EOF
    echo -e "${YELLOW}⚠ config.json generated without Cognito (not configured)${NC}"
fi

# Upload to S3 (excluding config.json from sync, will upload separately)
echo "Uploading frontend to S3..."
aws s3 sync dist/ s3://$S3_BUCKET/frontend/ --delete --region $AWS_REGION --exclude "config.json"

# Upload config.json separately with no-cache headers
echo "Uploading config.json with no-cache headers..."
aws s3 cp dist/config.json s3://$S3_BUCKET/frontend/config.json \
    --region $AWS_REGION \
    --cache-control "no-cache, no-store, must-revalidate" \
    --content-type "application/json"

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
INTEGRATION_COUNT=$(aws apigateway get-integrations \
    --api-id $API_GATEWAY_ID \
    --region $AWS_REGION \
    2>/dev/null | grep -c "integrationId" || echo "0")

# Remove any whitespace/newlines and ensure it's a valid integer
INTEGRATION_EXISTS=$(echo "$INTEGRATION_COUNT" | tr -d '\n\r' | grep -o '[0-9]*' | head -1)
INTEGRATION_EXISTS=${INTEGRATION_EXISTS:-0}

if [ "$INTEGRATION_EXISTS" -eq "0" ]; then
    echo -e "${YELLOW}Note: API Gateway needs manual configuration. See docs/DEPLOYMENT_GUIDE.md${NC}"
else
    echo -e "${GREEN}✓ API Gateway already configured${NC}"
fi

# Summary
echo -e "\n${GREEN}=== Deployment Complete! ===${NC}\n"

CLOUDFRONT_DOMAIN=$(cd infrastructure/terraform && terraform output -raw cloudfront_domain)
echo "Frontend URL: https://$CLOUDFRONT_DOMAIN"
echo "Custom Domain: https://$CUSTOM_DOMAIN (if DNS configured)"
echo ""
echo "Next steps:"
echo "1. Update DNS CNAME for $CUSTOM_DOMAIN → $CLOUDFRONT_DOMAIN"
echo "2. Load sample data: cd backend && python init_dynamodb_sample_data.py"
echo "3. Test the application"
echo ""
