# Terraform Infrastructure Improvements

This document describes the Terraform configuration updates for complete infrastructure-as-code management.

## What's New

The Terraform configuration now manages:

1. ✅ **Lambda Function** - Fully managed with configuration
2. ✅ **API Gateway Integration** - Complete Lambda proxy setup
3. ✅ **API Gateway Deployment** - Automatic deployments with triggers
4. ✅ **Lambda Permissions** - API Gateway invoke permissions
5. ✅ **Environment Variables** - DynamoDB table name auto-configured

## Resources Added

### Lambda Function (`aws_lambda_function.api`)

```hcl
- Function name from project variables
- Handler: main.handler
- Runtime: Python 3.12
- S3 bucket deployment
- Environment variables for DynamoDB
- Proper IAM dependencies
```

### API Gateway Resources

```hcl
- aws_api_gateway_resource.proxy - {proxy+} catch-all route
- aws_api_gateway_method.proxy - ANY method for proxy
- aws_api_gateway_integration.lambda - Lambda proxy integration
- aws_api_gateway_method.proxy_root - Root path handler
- aws_api_gateway_integration.lambda_root - Root integration
- aws_api_gateway_deployment.main - Deployment with triggers
- aws_api_gateway_stage.prod - Production stage
- aws_lambda_permission.api_gateway - Invoke permissions
```

## Benefits

### Before (Manual Configuration)
- Lambda created by deployment script
- API Gateway configured manually via AWS CLI
- Environment variables set separately
- Permissions added ad-hoc
- Hard to reproduce
- State drift between deployments

### After (Terraform Managed)
- Complete infrastructure as code
- Reproducible deployments
- Consistent environments
- Easy to review changes
- Version controlled
- Automatic dependency management

## Deployment Workflow

### Initial Setup

```bash
cd infrastructure/terraform
terraform init
terraform plan
terraform apply
```

This creates:
- S3 bucket
- CloudFront distribution
- DynamoDB table
- Lambda function (placeholder)
- API Gateway with Lambda integration
- IAM roles and policies

### Code Updates

```bash
# Use the new simplified deployment script
./deploy-simple.sh
```

Or manually:

```bash
# 1. Build and upload Lambda code
cd backend
pip install -r requirements.txt -t package/
cp *.py services/ package/
cd package && zip -r ../lambda-deployment.zip . && cd ..
aws s3 cp lambda-deployment.zip s3://your-bucket/backend/

# 2. Update Lambda via Terraform
cd ../infrastructure/terraform
terraform apply -target=aws_lambda_function.api

# 3. Build and deploy frontend
cd ../../frontend
npm run build
aws s3 sync dist/ s3://your-bucket/frontend/
aws cloudfront create-invalidation --distribution-id XXXXX --paths "/*"
```

## Important Notes

### Lambda Code Deployment

The Lambda function resource in Terraform references `s3://bucket/backend/lambda-deployment.zip`. This file must exist before running `terraform apply`.

**First Time Setup:**
1. Upload a dummy/initial Lambda package to S3
2. Run `terraform apply`
3. Use deployment script for updates

**Subsequent Updates:**
- Terraform tracks the Lambda function
- Code updates via S3 trigger automatic redeployment
- Use `terraform apply -target=aws_lambda_function.api` to force update

### API Gateway Redeployment

The `aws_api_gateway_deployment` resource uses triggers to automatically redeploy when:
- Integration changes
- Method changes
- Resource changes

This ensures API Gateway always reflects the latest configuration.

### Environment Variables

The Lambda function automatically gets:
- `DYNAMODB_DISTRICTS_TABLE` - Set by Terraform from table name
- `AWS_REGION` - Automatically provided by Lambda runtime

## State Management

### Current State
- State stored locally in `terraform.tfstate`
- Suitable for single developer

### Recommended for Team
```hcl
terraform {
  backend "s3" {
    bucket = "your-terraform-state-bucket"
    key    = "ma-teachers-contracts/terraform.tfstate"
    region = "us-east-2"
    encrypt = true
    dynamodb_table = "terraform-state-lock"
  }
}
```

## Troubleshooting

### Lambda function fails to create
**Error:** "Error creating Lambda Function: ResourceConflictException"
**Solution:** Function may already exist from old deployment. Import it:
```bash
terraform import aws_lambda_function.api crackpow-schools-api
```

### API Gateway returns 500 errors
**Check:**
1. Lambda handler is correct (`main.handler`)
2. Lambda has API Gateway invoke permissions
3. Environment variables are set
4. CloudWatch logs for Lambda errors

### Changes not reflected
**Fix:**
```bash
# Force Lambda update
terraform apply -target=aws_lambda_function.api

# Force API Gateway redeployment
terraform taint aws_api_gateway_deployment.main
terraform apply
```

## Migration Guide

If migrating from manually created resources:

### 1. Import Existing Lambda
```bash
terraform import aws_lambda_function.api your-function-name
```

### 2. Import API Gateway Resources
```bash
terraform import aws_api_gateway_rest_api.main api-id
terraform import aws_api_gateway_resource.proxy resource-id
# etc.
```

### 3. Verify Plan
```bash
terraform plan
# Should show minimal changes
```

### 4. Apply
```bash
terraform apply
```

## Best Practices

1. **Always use deployment script** - Ensures consistent process
2. **Review plans before apply** - Check for unexpected changes
3. **Version control everything** - All Terraform files in git
4. **Use workspaces for environments** - dev, staging, prod
5. **Tag all resources** - For cost tracking and organization

## Cost Impact

Terraform management has **no additional cost**. Resources remain the same:
- Lambda: Pay per execution
- API Gateway: Pay per request
- DynamoDB: Pay per request (on-demand)
- S3: Pay per storage/transfer
- CloudFront: Pay per request/transfer

## Security Improvements

With Terraform:
- IAM policies are code-reviewed
- Least privilege by default
- Consistent security configurations
- Easy to audit
- No manual permission changes

## Next Steps

1. ✅ Lambda and API Gateway fully managed
2. 🔄 Consider adding:
   - CloudWatch Alarms for monitoring
   - Lambda function URLs (alternative to API Gateway)
   - WAF rules for API protection
   - Custom domain for API Gateway
   - API Gateway usage plans and API keys
