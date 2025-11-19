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
DYNAMODB_TABLE=$(terraform output -raw dynamodb_table_name)
CLOUDFRONT_ID=$(terraform output -raw cloudfront_distribution_id)
CLOUDFRONT_DOMAIN=$(terraform output -raw cloudfront_domain)
API_GATEWAY_ID=$(terraform output -raw api_gateway_id)
API_ENDPOINT=$(terraform output -raw api_endpoint)
SALARY_API_ENDPOINT=$(terraform output -raw api_endpoint)

# Salary processing Lambda functions (optional - may not exist in older deployments)
SALARY_PROCESSOR_LAMBDA=$(terraform output -raw salary_processor_lambda_name 2>/dev/null || echo "")
SALARY_NORMALIZER_LAMBDA=$(terraform output -raw salary_normalizer_lambda_name 2>/dev/null || echo "")
BACKUP_REAPPLY_WORKER_LAMBDA=$(terraform output -raw backup_reapply_worker_lambda_name 2>/dev/null || echo "")

echo -e "${GREEN}✓ Configuration loaded${NC}"
echo "  S3 Bucket: $S3_BUCKET"
echo "  Lambda Function: $LAMBDA_FUNCTION_NAME"
echo "  Region: $AWS_REGION"
echo "  DynamoDB Table: $DYNAMODB_TABLE"
echo "  CloudFront Domain: $CLOUDFRONT_DOMAIN"
echo "  API Endpoint: $API_ENDPOINT"
echo "  Salary API Endpoint: $SALARY_API_ENDPOINT"
if [ -n "$SALARY_PROCESSOR_LAMBDA" ]; then
    echo "  Salary Processor Lambda: $SALARY_PROCESSOR_LAMBDA"
fi
if [ -n "$SALARY_NORMALIZER_LAMBDA" ]; then
    echo "  Salary Normalizer Lambda: $SALARY_NORMALIZER_LAMBDA"
fi
if [ -n "$BACKUP_REAPPLY_WORKER_LAMBDA" ]; then
    echo "  Backup Reapply Worker Lambda: $BACKUP_REAPPLY_WORKER_LAMBDA"
fi
echo ""

cd ../..

# Deploy Backend
echo -e "${YELLOW}=== Deploying Backend ===${NC}"

# 1. Package Python Lambda (districts API)
echo "Creating Python Lambda deployment package..."

# Save current directory (project root)
PROJECT_ROOT="$(pwd)"

# Create build directory structure
BUILD_DIR="build/backend/api"
rm -rf "$BUILD_DIR" 2>/dev/null || true
mkdir -p "$BUILD_DIR/package"

# Install dependencies (use python -m pip to avoid PEP 668 issues)
if command -v python3 >/dev/null 2>&1; then
    PIP_BUILD_CMD="python3 -m pip"
else
    PIP_BUILD_CMD="pip"
fi
$PIP_BUILD_CMD install -r backend/requirements.txt -t "$BUILD_DIR/package/" --quiet

# Copy application code
cp backend/*.py "$BUILD_DIR/package/"
[ -d "backend/services" ] && cp -r backend/services "$BUILD_DIR/package/"
[ -d "backend/utils" ] && cp -r backend/utils "$BUILD_DIR/package/"
[ -d "backend/routers" ] && cp -r backend/routers "$BUILD_DIR/package/"

# Create zip
cd "$BUILD_DIR/package"
zip -r ../lambda-deployment.zip . -q
cd "$PROJECT_ROOT"

echo -e "${GREEN}✓ Python Lambda package created at $BUILD_DIR/lambda-deployment.zip${NC}"

# Note: Salary endpoints are now served by the main API Lambda. The separate
# `salaries.zip` package is no longer built or uploaded. Terraform has been
# updated to integrate the salary API routes with the main API Lambda.
# If you need to keep a separate salaries Lambda, re-enable packaging here.

# Upload backend lambda-deployment.zip to S3
echo "Uploading backend Lambda package to S3..."
aws s3 cp "$PROJECT_ROOT/$BUILD_DIR/lambda-deployment.zip" s3://$S3_BUCKET/backend/lambda-deployment.zip --region $AWS_REGION

echo -e "${GREEN}✓ Lambda package uploaded${NC}"

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

    # Note: Lambda environment variables are managed by Terraform in main.tf
    # and should not be updated here. Run 'terraform apply' to update configuration.
else
    echo -e "${RED}Lambda function does not exist!${NC}"
    echo -e "${YELLOW}Lambda should be created by Terraform. Please run:${NC}"
    echo -e "  cd infrastructure/terraform && terraform apply"
    exit 1
fi

echo -e "${GREEN}✓ Lambda function deployed${NC}"

# Deploy Salary Processing Lambdas (if configured)
if [ -n "$SALARY_PROCESSOR_LAMBDA" ]; then
    echo -e "\n${YELLOW}=== Deploying Salary Processor Lambda ===${NC}"

    echo "Creating Salary Processor Lambda deployment package..."

    # Create build directory
    PROCESSOR_BUILD_DIR="build/backend/processor"
    rm -rf "$PROCESSOR_BUILD_DIR" 2>/dev/null || true
    mkdir -p "$PROCESSOR_BUILD_DIR/package"

    # Install dependencies
    $PIP_BUILD_CMD install boto3 pdfplumber pymupdf pypdfium2 -t "$PROCESSOR_BUILD_DIR/package/" --quiet

    # Copy Lambda handler
    cp backend/lambdas/processor.py "$PROCESSOR_BUILD_DIR/package/"

    # Copy required services (HybridContractExtractor and dependencies)
    mkdir -p "$PROCESSOR_BUILD_DIR/package/services"
    cp backend/services/hybrid_extractor.py "$PROCESSOR_BUILD_DIR/package/services/"
    cp backend/services/contract_processor.py "$PROCESSOR_BUILD_DIR/package/services/"
    cp backend/services/table_extractor.py "$PROCESSOR_BUILD_DIR/package/services/"
    [ -f "backend/services/__init__.py" ] && cp backend/services/__init__.py "$PROCESSOR_BUILD_DIR/package/services/"

    # Create zip
    cd "$PROCESSOR_BUILD_DIR/package"
    zip -r ../salary-processor.zip . -q
    cd "$PROJECT_ROOT"

    echo -e "${GREEN}✓ Salary Processor Lambda package created at $PROCESSOR_BUILD_DIR/salary-processor.zip${NC}"

    # Upload to S3
    echo "Uploading Salary Processor Lambda package to S3..."
    aws s3 cp "$PROJECT_ROOT/$PROCESSOR_BUILD_DIR/salary-processor.zip" s3://$S3_BUCKET/backend/salary-processor.zip --region $AWS_REGION
    echo -e "${GREEN}✓ Salary Processor Lambda package uploaded${NC}"

    # Update Lambda function
    if aws lambda get-function --function-name $SALARY_PROCESSOR_LAMBDA --region $AWS_REGION > /dev/null 2>&1; then
        echo "Updating Salary Processor Lambda function code..."

        # Wait for any pending updates
        aws lambda wait function-updated --function-name $SALARY_PROCESSOR_LAMBDA --region $AWS_REGION 2>/dev/null || true

        # Update function code
        aws lambda update-function-code \
            --function-name $SALARY_PROCESSOR_LAMBDA \
            --s3-bucket $S3_BUCKET \
            --s3-key backend/salary-processor.zip \
            --region $AWS_REGION \
            --output json > /dev/null

        echo "Waiting for code update to complete..."
        aws lambda wait function-updated --function-name $SALARY_PROCESSOR_LAMBDA --region $AWS_REGION 2>/dev/null || true

        echo -e "${GREEN}✓ Salary Processor Lambda function deployed${NC}"
    else
        echo -e "${YELLOW}⚠ Salary Processor Lambda function does not exist (should be created by Terraform)${NC}"
    fi
fi

if [ -n "$SALARY_NORMALIZER_LAMBDA" ]; then
    echo -e "\n${YELLOW}=== Deploying Salary Normalizer Lambda ===${NC}"

    echo "Creating Salary Normalizer Lambda deployment package..."

    # Create build directory
    NORMALIZER_BUILD_DIR="build/backend/normalizer"
    rm -rf "$NORMALIZER_BUILD_DIR" 2>/dev/null || true
    mkdir -p "$NORMALIZER_BUILD_DIR/package"

    # Install dependencies (boto3 is included by AWS Lambda runtime, but include for completeness)
    $PIP_BUILD_CMD install boto3 -t "$NORMALIZER_BUILD_DIR/package/" --quiet

    # Copy Lambda handler and shared utilities
    cp backend/lambdas/normalizer.py "$NORMALIZER_BUILD_DIR/package/"
    cp -r backend/utils "$NORMALIZER_BUILD_DIR/package/"

    # Create zip
    cd "$NORMALIZER_BUILD_DIR/package"
    zip -r ../salary-normalizer.zip . -q
    cd "$PROJECT_ROOT"

    echo -e "${GREEN}✓ Salary Normalizer Lambda package created at $NORMALIZER_BUILD_DIR/salary-normalizer.zip${NC}"

    # Upload to S3
    echo "Uploading Salary Normalizer Lambda package to S3..."
    aws s3 cp "$PROJECT_ROOT/$NORMALIZER_BUILD_DIR/salary-normalizer.zip" s3://$S3_BUCKET/backend/salary-normalizer.zip --region $AWS_REGION
    echo -e "${GREEN}✓ Salary Normalizer Lambda package uploaded${NC}"

    # Update Lambda function
    if aws lambda get-function --function-name $SALARY_NORMALIZER_LAMBDA --region $AWS_REGION > /dev/null 2>&1; then
        echo "Updating Salary Normalizer Lambda function code..."

        # Wait for any pending updates
        aws lambda wait function-updated --function-name $SALARY_NORMALIZER_LAMBDA --region $AWS_REGION 2>/dev/null || true

        # Update function code
        aws lambda update-function-code \
            --function-name $SALARY_NORMALIZER_LAMBDA \
            --s3-bucket $S3_BUCKET \
            --s3-key backend/salary-normalizer.zip \
            --region $AWS_REGION \
            --output json > /dev/null

        echo "Waiting for code update to complete..."
        aws lambda wait function-updated --function-name $SALARY_NORMALIZER_LAMBDA --region $AWS_REGION 2>/dev/null || true

        echo -e "${GREEN}✓ Salary Normalizer Lambda function deployed${NC}"
    else
        echo -e "${YELLOW}⚠ Salary Normalizer Lambda function does not exist (should be created by Terraform)${NC}"
    fi
fi

if [ -n "$BACKUP_REAPPLY_WORKER_LAMBDA" ]; then
    echo -e "\n${YELLOW}=== Deploying Backup Reapply Worker Lambda ===${NC}"

    echo "Creating Backup Reapply Worker Lambda deployment package..."

    # Create build directory
    BACKUP_WORKER_BUILD_DIR="build/backend/backup-worker"
    rm -rf "$BACKUP_WORKER_BUILD_DIR" 2>/dev/null || true
    mkdir -p "$BACKUP_WORKER_BUILD_DIR/package"

    # Install dependencies (boto3 is included by AWS Lambda runtime, but include for completeness)
    $PIP_BUILD_CMD install boto3 -t "$BACKUP_WORKER_BUILD_DIR/package/" --quiet

    # Copy Lambda handler and shared services/utilities
    cp backend/lambdas/backup_reapply_worker.py "$BACKUP_WORKER_BUILD_DIR/package/"
    mkdir -p "$BACKUP_WORKER_BUILD_DIR/package/services"
    cp backend/services/salary_jobs.py "$BACKUP_WORKER_BUILD_DIR/package/services/"
    [ -f "backend/services/__init__.py" ] && cp backend/services/__init__.py "$BACKUP_WORKER_BUILD_DIR/package/services/"

    # Copy utils directory (needed by salary_jobs.py)
    [ -d "backend/utils" ] && cp -r backend/utils "$BACKUP_WORKER_BUILD_DIR/package/"

    # Create zip
    cd "$BACKUP_WORKER_BUILD_DIR/package"
    zip -r ../backup-reapply-worker.zip . -q
    cd "$PROJECT_ROOT"

    echo -e "${GREEN}✓ Backup Reapply Worker Lambda package created at $BACKUP_WORKER_BUILD_DIR/backup-reapply-worker.zip${NC}"

    # Upload to S3
    echo "Uploading Backup Reapply Worker Lambda package to S3..."
    aws s3 cp "$PROJECT_ROOT/$BACKUP_WORKER_BUILD_DIR/backup-reapply-worker.zip" s3://$S3_BUCKET/backend/backup-reapply-worker.zip --region $AWS_REGION
    echo -e "${GREEN}✓ Backup Reapply Worker Lambda package uploaded${NC}"

    # Update Lambda function
    if aws lambda get-function --function-name $BACKUP_REAPPLY_WORKER_LAMBDA --region $AWS_REGION > /dev/null 2>&1; then
        echo "Updating Backup Reapply Worker Lambda function code..."

        # Wait for any pending updates
        aws lambda wait function-updated --function-name $BACKUP_REAPPLY_WORKER_LAMBDA --region $AWS_REGION 2>/dev/null || true

        # Update function code
        aws lambda update-function-code \
            --function-name $BACKUP_REAPPLY_WORKER_LAMBDA \
            --s3-bucket $S3_BUCKET \
            --s3-key backend/backup-reapply-worker.zip \
            --region $AWS_REGION \
            --output json > /dev/null

        echo "Waiting for code update to complete..."
        aws lambda wait function-updated --function-name $BACKUP_REAPPLY_WORKER_LAMBDA --region $AWS_REGION 2>/dev/null || true

        echo -e "${GREEN}✓ Backup Reapply Worker Lambda function deployed${NC}"
    else
        echo -e "${YELLOW}⚠ Backup Reapply Worker Lambda function does not exist (should be created by Terraform)${NC}"
    fi
fi

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