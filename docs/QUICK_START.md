# Quick Start Guide

## TL;DR - Get Running Fast

### First Time Setup

```bash
# 1. Install prerequisites
sudo apt-get install jq  # JSON processor for scripts

# 2. Configure AWS credentials
aws configure

# 3. Configure Terraform variables
cd infrastructure/terraform
cp terraform.tfvars.example terraform.tfvars
# Edit terraform.tfvars with your AWS region, project name, etc.

# 4. Create infrastructure and deploy (one command!)
cd ../..
./recreate.sh
```

Done! Your site is live.

## Get Your URLs

```bash
# Get outputs from Terraform
cd infrastructure/terraform
terraform output
```

Or check the main README deployment section for URLs.

## Local Development

```bash
# Start both backend and frontend
./dev.sh start

# Stop both services
./dev.sh stop
```

Backend runs on http://localhost:8000
Frontend runs on http://localhost:5173

## Redeploy After Code Changes

### All changes (backend + frontend):
```bash
./deploy.sh
```

### Skip tests (faster):
```bash
./deploy.sh --no-tests
```

### Terraform-specific deployment:
```bash
cd infrastructure/scripts
./deploy-backend-tf.sh   # Backend only
./deploy-frontend-tf.sh  # Frontend only
```

## Common Issues

### "jq: command not found"
```bash
sudo apt-get install jq
```

### "AccessDenied on S3"
Your AWS user needs these permissions:
- AmazonS3FullAccess
- CloudFrontFullAccess
- AWSLambda_FullAccess
- AmazonAPIGatewayAdministrator
- AmazonDynamoDBFullAccess
- AmazonSQSFullAccess
- AWSCognitoAdminAccess
- IAMFullAccess (or at least role creation)

### "Terraform not initialized"
```bash
cd infrastructure/terraform
terraform init
```

### CloudFront shows old version
Wait 5-10 minutes for cache invalidation. The deploy.sh script automatically invalidates the cache.

### Tests failing
```bash
# Backend tests
cd backend
python -m pytest

# Frontend tests
cd frontend
npm test
```

## File Structure

```
schools/
├── deploy.sh                    # Main deployment script
├── deploy-simple.sh             # Simplified deployment wrapper
├── recreate.sh                  # Full infrastructure recreation
├── dev.sh                       # Local development startup
└── infrastructure/
    ├── terraform/               # Terraform IaC
    │   ├── main.tf
    │   ├── cognito.tf
    │   ├── salary_processing.tf
    │   └── terraform.tfvars     # Your config (gitignored)
    └── scripts/
        ├── deploy-backend-tf.sh
        └── deploy-frontend-tf.sh
```

## What Gets Created in AWS

- **1 S3 Bucket**: Frontend hosting + Backend packages + Contract PDFs
- **1 CloudFront Distribution**: CDN for frontend with OAC
- **1 API Gateway**: REST API with proxy integration
- **3 Lambda Functions**: Main API, PDF processor, normalizer
- **1 DynamoDB Table**: Single-table design with GSIs
- **1 SQS Queue**: Salary processing queue
- **1 Cognito User Pool**: Authentication with admin group
- **IAM Roles**: Lambda execution permissions
- **Origin Access Control**: CloudFront → S3 security

## Cost Estimate

With minimal traffic:
- **Free tier**: $0/month (first 12 months)
- **After free tier**: ~$5-20/month depending on traffic

## Development Workflow

```bash
# 1. Make changes to code locally

# 2. Test locally using dev.sh
./dev.sh start       # Starts both backend and frontend

# Or test individually:
cd backend && source venv/bin/activate && uvicorn main:app --reload  # Backend
cd frontend && npm run dev                                            # Frontend

# 3. Run tests
cd backend && pytest              # Backend tests
cd frontend && npm test           # Frontend tests

# 4. Deploy when ready
./deploy.sh                       # Deploy everything with tests
./deploy.sh --no-tests            # Deploy without running tests
```

## Data Import

After infrastructure is created:

```bash
cd backend
source venv/bin/activate

# Import districts
python scripts/import_districts.py

# Load salary data (if you have it)
python scripts/load_salary_data.py ../data/salary_data.example.json
```

## Terraform Commands

```bash
cd infrastructure/terraform

terraform init          # Initialize (first time only)
terraform plan          # Preview changes
terraform apply         # Apply changes
terraform destroy       # Tear down everything
terraform output        # View outputs (URLs, etc.)
```

## Help

- Full docs: [../README.md](../README.md)
- Deployment guide: [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md)
- Infrastructure docs: [INFRASTRUCTURE.md](INFRASTRUCTURE.md)
- Salary processing: [../SALARY_PROCESSING_IMPLEMENTATION.md](../SALARY_PROCESSING_IMPLEMENTATION.md)