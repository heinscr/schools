# Deployment Guide

Complete guide for deploying the Massachusetts Teachers Contracts application to AWS.

## Prerequisites Checklist

- [ ] AWS CLI installed (`aws --version`)
- [ ] AWS credentials configured (`aws configure`)
- [ ] Terraform installed (`terraform --version`) - Version 1.0+
- [ ] Node.js 18+ installed (`node --version`)
- [ ] Python 3.12 installed (`python3 --version`)
- [ ] jq installed (`jq --version`) - JSON processor

### Installing Prerequisites

```bash
# Ubuntu/Debian
sudo apt-get update
sudo apt-get install jq awscli

# Install Terraform
wget https://releases.hashicorp.com/terraform/1.6.0/terraform_1.6.0_linux_amd64.zip
unzip terraform_1.6.0_linux_amd64.zip
sudo mv terraform /usr/local/bin/

# macOS
brew install jq awscli terraform
```

## Deployment Methods

### Method 1: One-Command Deployment (Recommended for First Time)

The `recreate.sh` script handles everything:

```bash
./recreate.sh
```

This script will:
1. Initialize and apply Terraform configuration
2. Prompt for admin user creation (email/password)
3. Deploy backend and frontend code
4. Import district data (optional)

### Method 2: Manual Step-by-Step Deployment

For more control over the deployment process:

#### Step 1: Configure Terraform Variables

```bash
cd infrastructure/terraform
cp terraform.tfvars.example terraform.tfvars
```

Edit `terraform.tfvars` with your values:

```hcl
aws_region = "us-east-1"
project_name = "ma-teachers-contracts"

# Optional: Custom domain
custom_domain = "contracts.example.com"
use_custom_domain = true

# Lambda settings
lambda_memory_size = 512
lambda_timeout = 30
```

#### Step 2: Initialize Terraform

```bash
terraform init
```

This downloads required providers (AWS) and initializes the backend.

#### Step 3: Review Infrastructure Plan

```bash
terraform plan
```

Review the resources that will be created:
- S3 bucket
- CloudFront distribution
- API Gateway
- 3 Lambda functions
- DynamoDB table
- SQS queue
- Cognito user pool
- IAM roles and policies

#### Step 4: Create Infrastructure

```bash
terraform apply
```

Type `yes` when prompted. This takes 5-10 minutes due to CloudFront distribution creation.

#### Step 5: Create Admin User (Optional)

```bash
cd ../..
aws cognito-idp admin-create-user \
  --user-pool-id $(cd infrastructure/terraform && terraform output -raw cognito_user_pool_id) \
  --username admin@example.com \
  --user-attributes Name=email,Value=admin@example.com Name=email_verified,Value=true \
  --message-action SUPPRESS

# Set permanent password
aws cognito-idp admin-set-user-password \
  --user-pool-id $(cd infrastructure/terraform && terraform output -raw cognito_user_pool_id) \
  --username admin@example.com \
  --password YourSecurePassword123! \
  --permanent

# Add to admin group
aws cognito-idp admin-add-user-to-group \
  --user-pool-id $(cd infrastructure/terraform && terraform output -raw cognito_user_pool_id) \
  --username admin@example.com \
  --group-name admins
```

#### Step 6: Deploy Application Code

```bash
./deploy.sh
```

This script:
- Runs backend and frontend tests
- Packages Lambda code
- Uploads to S3
- Updates Lambda functions
- Builds frontend with correct API endpoint
- Uploads frontend to S3
- Invalidates CloudFront cache

Skip tests for faster deployment:
```bash
./deploy.sh --no-tests
```

#### Step 7: Import District Data (Optional)

```bash
cd backend
source venv/bin/activate
python scripts/import_districts.py
```

## Regular Deployments (After Initial Setup)

### Deploy All Changes

```bash
./deploy.sh
```

### Deploy Backend Only

```bash
cd infrastructure/scripts
./deploy-backend-tf.sh
```

### Deploy Frontend Only

```bash
cd infrastructure/scripts
./deploy-frontend-tf.sh
```

## Accessing Your Application

### Get Application URLs

```bash
cd infrastructure/terraform

# Get CloudFront URL
terraform output cloudfront_domain

# Get API Gateway URL
terraform output api_gateway_url

# Get Cognito details
terraform output cognito_user_pool_id
terraform output cognito_client_id
```

### Test Deployment

```bash
# Test backend
API_URL=$(cd infrastructure/terraform && terraform output -raw api_gateway_url)
curl $API_URL/health

# Test frontend - open in browser
FRONTEND_URL=$(cd infrastructure/terraform && terraform output -raw cloudfront_domain)
echo "https://$FRONTEND_URL"
```

## Monitoring & Debugging

### View Lambda Logs

```bash
# Main API Lambda
aws logs tail /aws/lambda/ma-teachers-contracts-api --follow

# PDF Processor Lambda
aws logs tail /aws/lambda/ma-teachers-contracts-salary-processor --follow

# Normalizer Lambda
aws logs tail /aws/lambda/ma-teachers-contracts-salary-normalizer --follow
```

### Check SQS Queue

```bash
aws sqs get-queue-attributes \
  --queue-url $(cd infrastructure/terraform && terraform output -raw sqs_queue_url) \
  --attribute-names All
```

### DynamoDB Table Stats

```bash
aws dynamodb describe-table \
  --table-name $(cd infrastructure/terraform && terraform output -raw dynamodb_table_name)
```

### Force CloudFront Cache Invalidation

```bash
CF_DIST=$(cd infrastructure/terraform && terraform output -raw cloudfront_distribution_id)
aws cloudfront create-invalidation --distribution-id $CF_DIST --paths "/*"
```

## Updating Infrastructure

When you modify Terraform files:

```bash
cd infrastructure/terraform

# Preview changes
terraform plan

# Apply changes
terraform apply
```

After infrastructure changes, redeploy application code:
```bash
cd ../..
./deploy.sh
```

## Troubleshooting

### Terraform State Issues

If Terraform state is corrupted:

```bash
cd infrastructure/terraform
terraform refresh
terraform plan  # Verify state
```

### Lambda Function Not Updating

Manually update Lambda code:

```bash
cd infrastructure/scripts
./deploy-backend-tf.sh
```

### CloudFront Shows Old Frontend

Invalidate cache:
```bash
CF_DIST=$(cd infrastructure/terraform && terraform output -raw cloudfront_distribution_id)
aws cloudfront create-invalidation --distribution-id $CF_DIST --paths "/*"
```

Wait 5-10 minutes for invalidation to complete.

### Backend Tests Failing

```bash
cd backend
source venv/bin/activate
pytest -v  # Run tests with verbose output
```

Check for:
- Missing dependencies
- Environment variable issues
- DynamoDB local connection issues

### Frontend Tests Failing

```bash
cd frontend
npm test -- --run  # Run tests once
npm run test:coverage  # Generate coverage report
```

### Permission Denied on Scripts

```bash
chmod +x deploy.sh recreate.sh dev.sh
chmod +x infrastructure/scripts/*.sh
```

### AWS Permissions Issues

Your AWS user/role needs these permissions:
- `AmazonS3FullAccess`
- `CloudFrontFullAccess`
- `AWSLambda_FullAccess`
- `AmazonAPIGatewayAdministrator`
- `AmazonDynamoDBFullAccess`
- `AmazonSQSFullAccess`
- `AWSCognitoAdminAccess`
- `IAMFullAccess` (or specific permissions for role creation)

## Cleanup & Teardown

### Remove All Resources

**WARNING**: This deletes all data permanently.

```bash
cd infrastructure/terraform

# Preview what will be deleted
terraform plan -destroy

# Delete all resources
terraform destroy
```

Type `yes` when prompted.

### Manual Cleanup (if Terraform fails)

If `terraform destroy` fails:

1. Empty S3 bucket manually:
```bash
BUCKET=$(terraform output -raw s3_bucket_name)
aws s3 rm s3://$BUCKET --recursive
```

2. Try destroy again:
```bash
terraform destroy
```

3. Manually delete stuck resources via AWS Console if needed.

## CI/CD Integration

### GitHub Actions Example

```yaml
name: Deploy

on:
  push:
    branches: [main]

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3

      - name: Configure AWS credentials
        uses: aws-actions/configure-aws-credentials@v2
        with:
          aws-access-key-id: ${{ secrets.AWS_ACCESS_KEY_ID }}
          aws-secret-access-key: ${{ secrets.AWS_SECRET_ACCESS_KEY }}
          aws-region: us-east-1

      - name: Setup Terraform
        uses: hashicorp/setup-terraform@v2

      - name: Deploy
        run: ./deploy.sh --no-tests
```

## Production Best Practices

### Security

1. **Enable CloudFront logging**:
```hcl
# In terraform/main.tf CloudFront resource
logging_config {
  bucket = aws_s3_bucket.logs.bucket_domain_name
  prefix = "cloudfront/"
}
```

2. **Enable DynamoDB point-in-time recovery**:
```hcl
# In terraform/main.tf DynamoDB resource
point_in_time_recovery {
  enabled = true
}
```

3. **Use custom domain with ACM certificate**:
- Set `use_custom_domain = true` in `terraform.tfvars`
- Create ACM certificate in `us-east-1` (required for CloudFront)
- Set `custom_domain` to your domain

4. **Rotate Cognito secrets regularly**
5. **Enable AWS WAF on CloudFront** (additional cost)

### Performance

1. **Increase Lambda memory** for better performance:
```hcl
lambda_memory_size = 1024  # In terraform.tfvars
```

2. **Enable DynamoDB auto-scaling** (already configured in main.tf)

3. **Monitor CloudWatch metrics**:
   - Lambda duration and errors
   - API Gateway latency
   - DynamoDB read/write capacity

### Cost Optimization

1. **Enable S3 lifecycle policies** for old contract PDFs
2. **Use CloudFront caching effectively** (already configured)
3. **Monitor AWS Cost Explorer** for unexpected charges
4. **Consider Reserved Capacity** for DynamoDB if usage is predictable

## Deployment Checklist

Before deploying to production:

- [ ] Configure custom domain and SSL certificate
- [ ] Set up CloudWatch alarms for errors
- [ ] Enable DynamoDB point-in-time recovery
- [ ] Configure backup strategy for S3 bucket
- [ ] Test admin user login
- [ ] Test PDF upload functionality
- [ ] Run full test suite
- [ ] Review IAM policies for least privilege
- [ ] Enable CloudFront logging
- [ ] Document admin credentials securely
- [ ] Set up monitoring dashboard

## Support Resources

- **Terraform AWS Provider Docs**: https://registry.terraform.io/providers/hashicorp/aws/latest/docs
- **AWS Lambda Docs**: https://docs.aws.amazon.com/lambda/
- **CloudFront Docs**: https://docs.aws.amazon.com/cloudfront/
- **DynamoDB Docs**: https://docs.aws.amazon.com/dynamodb/
- **Project Documentation**: See `/docs` directory