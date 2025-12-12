# Infrastructure

AWS infrastructure and deployment automation for the MA Teachers Contracts application.

## Quick Start

```bash
# 1. Install Terraform
brew install terraform  # macOS
# or
sudo apt install terraform  # Ubuntu/Debian

# 2. Configure AWS
aws configure

# 3. Create infrastructure
cd terraform
terraform init
terraform apply

# 4. Deploy application
cd ../scripts
./deploy-backend-tf.sh
./deploy-frontend-tf.sh
```

## Architecture

- **S3**: Single bucket (`${project_name}-${account_id}`)
  - Frontend: `s3://bucket/frontend/`
  - Backend: `s3://bucket/backend/`
- **CloudFront**: CDN with Origin Access Control
- **Lambda**: Python FastAPI backend
- **API Gateway**: REST API endpoint
- **IAM**: Lambda execution role

## Directory Structure

```
infrastructure/
├── terraform/              # Terraform configuration
│   ├── main.tf            # Infrastructure definitions
│   ├── variables.tf       # Input variables
│   ├── outputs.tf         # Output values
│   └── terraform.tfvars   # Your settings (git-ignored)
└── scripts/
    ├── deploy-backend-tf.sh   # Deploy backend code
    └── deploy-frontend-tf.sh  # Deploy frontend code
```

## Workflows

### Create Infrastructure (One Time)

```bash
cd terraform
terraform init
terraform apply
```

### Deploy Code (Daily)

```bash
cd scripts
./deploy-backend-tf.sh   # If backend changed
./deploy-frontend-tf.sh  # If frontend changed
```

### Update Infrastructure

```bash
cd terraform
# Edit .tf files or terraform.tfvars
terraform plan
terraform apply
```

### Destroy Everything

```bash
cd terraform

# Delete Lambda function first
FUNCTION_NAME=$(terraform output -raw lambda_function_name)
aws lambda delete-function --function-name $FUNCTION_NAME

# Empty S3 bucket
BUCKET=$(terraform output -raw s3_bucket)
aws s3 rm s3://$BUCKET --recursive

# Destroy infrastructure
terraform destroy
```

## Documentation

- **[Quick Start](QUICK_START.md)** - Fast development setup
- **[Deployment Guide](DEPLOYMENT_GUIDE.md)** - Step-by-step deployment instructions
- **[Custom Domain Setup](CUSTOM_DOMAIN_SETUP.md)** - CloudFront SSL configuration

## Configuration

Edit `terraform/terraform.tfvars`:

```hcl
project_name = "ma-teachers-contracts"
aws_region   = "us-east-1"
environment  = "prod"

lambda_timeout = 30
lambda_memory  = 512
```

## Get URLs

```bash
cd terraform
terraform output website_url
terraform output api_endpoint
```

## Support

- Terraform issues: See [Terraform Guide](/docs/terraform-guide.md)
- AWS issues: `aws logs tail /aws/lambda/<function-name> --follow`
- General help: Check [project documentation](/docs)
