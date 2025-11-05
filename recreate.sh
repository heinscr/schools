#!/bin/bash
# Consolidated recreation script for MA Teachers Contracts application
# This script will recreate the entire infrastructure from scratch

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${GREEN}=== MA Teachers Contracts - Complete Recreation ===${NC}\n"

# Check if we're in the right directory
if [ ! -f "recreate.sh" ]; then
    echo -e "${RED}Error: Please run this script from the project root directory${NC}"
    exit 1
fi

# Step 1: Terraform Init
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${YELLOW}Step 1: Initializing Terraform${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}\n"

cd infrastructure/terraform
terraform init
echo -e "\n${GREEN}✓ Terraform initialized${NC}\n"

# Step 2: Terraform Apply
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${YELLOW}Step 2: Applying Terraform Configuration${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}\n"

terraform apply
echo -e "\n${GREEN}✓ Infrastructure created${NC}\n"

# Get the User Pool ID from Terraform outputs
USER_POOL_ID=$(terraform output -raw cognito_user_pool_id 2>/dev/null || echo "")

cd ../..

# Step 3: Create Admin User (Optional)
if [ -n "$USER_POOL_ID" ]; then
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${YELLOW}Step 3: Admin User Setup${NC}"
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}\n"

    echo -e "Cognito User Pool ID: ${GREEN}$USER_POOL_ID${NC}\n"

    read -r -p "Would you like to create an admin user? [y/N]: " CREATE_ADMIN

    if [[ "$CREATE_ADMIN" =~ ^[Yy]$ ]]; then
        # Prompt for email
        read -r -p "Enter admin email address: " ADMIN_EMAIL

        # Validate email is not empty
        if [ -z "$ADMIN_EMAIL" ]; then
            echo -e "${RED}Error: Email cannot be empty${NC}"
            exit 1
        fi

        # Prompt for password
        read -r -s -p "Enter admin password: " ADMIN_PASSWORD
        echo "" # New line after password input

        # Validate password is not empty
        if [ -z "$ADMIN_PASSWORD" ]; then
            echo -e "${RED}Error: Password cannot be empty${NC}"
            exit 1
        fi

        echo -e "\n${YELLOW}Creating admin user...${NC}"

        # Create the user
        aws cognito-idp admin-create-user \
            --user-pool-id "$USER_POOL_ID" \
            --username "$ADMIN_EMAIL" \
            --user-attributes Name=email,Value="$ADMIN_EMAIL" Name=email_verified,Value=true \
            --temporary-password "TempPassword123!" \
            --message-action SUPPRESS \
            --output json > /dev/null

        echo -e "${GREEN}✓ User created${NC}"

        # Set permanent password
        echo -e "${YELLOW}Setting permanent password...${NC}"
        aws cognito-idp admin-set-user-password \
            --user-pool-id "$USER_POOL_ID" \
            --username "$ADMIN_EMAIL" \
            --password "$ADMIN_PASSWORD" \
            --permanent \
            --output json > /dev/null

        echo -e "${GREEN}✓ Password set${NC}"

        # Add user to admins group
        echo -e "${YELLOW}Adding user to admins group...${NC}"
        aws cognito-idp admin-add-user-to-group \
            --user-pool-id "$USER_POOL_ID" \
            --username "$ADMIN_EMAIL" \
            --group-name admins \
            --output json > /dev/null 2>&1 || {
            echo -e "${YELLOW}⚠ Note: Could not add user to admins group (group may not exist yet)${NC}"
        }

        echo -e "${GREEN}✓ Admin user created successfully${NC}"
        echo -e "  Email: ${GREEN}$ADMIN_EMAIL${NC}\n"
    else
        echo -e "${YELLOW}Skipping admin user creation${NC}\n"
    fi
else
    echo -e "${YELLOW}⚠ Cognito User Pool ID not found, skipping user creation${NC}\n"
fi

# Step 4: Deploy Application
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${YELLOW}Step 4: Deploying Application${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}\n"

./deploy.sh
echo -e "\n${GREEN}✓ Application deployed${NC}\n"

# Step 5: Import Districts
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${YELLOW}Step 5: Importing Districts and Salary Data${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}\n"

cd backend

# Setup Python virtual environment if needed
PYTHON_BIN="python3"
if ! command -v $PYTHON_BIN >/dev/null 2>&1; then
    PYTHON_BIN="python"
fi

# Create/activate virtual environment
if [ ! -d "venv" ] || [ ! -f "venv/bin/activate" ]; then
    echo -e "${YELLOW}Creating Python virtual environment...${NC}"
    $PYTHON_BIN -m venv venv
fi

# Activate venv
# shellcheck disable=SC1091
source venv/bin/activate

# Install requirements
echo -e "${YELLOW}Installing Python dependencies...${NC}"
python -m pip install --upgrade pip setuptools wheel -q
python -m pip install -r requirements.txt -q

# Run import script with auto-yes to salary import
echo -e "${YELLOW}Importing districts...${NC}\n"
echo "y" | python scripts/import_districts.py

echo -e "\n${GREEN}✓ Districts and salary data imported${NC}\n"

# Deactivate venv
deactivate

cd ..

# Final Summary
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}=== Recreation Complete! ===${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}\n"

# Get final outputs
cd infrastructure/terraform
CLOUDFRONT_DOMAIN=$(terraform output -raw cloudfront_domain 2>/dev/null || echo "")
API_ENDPOINT=$(terraform output -raw api_endpoint 2>/dev/null || echo "")

if [ -n "$CLOUDFRONT_DOMAIN" ]; then
    echo -e "Frontend URL: ${GREEN}https://$CLOUDFRONT_DOMAIN${NC}"
fi

if [ -n "$API_ENDPOINT" ]; then
    echo -e "API Endpoint: ${GREEN}$API_ENDPOINT${NC}"
fi

cd ../..

echo -e "\n${GREEN}Your application is now fully deployed and ready to use!${NC}\n"
