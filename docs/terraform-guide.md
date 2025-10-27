# Terraform Infrastructure

Infrastructure as Code for the MA Teachers Contracts application using Terraform.

## What This Creates

- **S3 Bucket**: Single bucket with `/frontend` and `/backend` prefixes
- **CloudFront Distribution**: CDN for frontend with Origin Access Control
- **API Gateway**: REST API endpoint for backend
- **IAM Role**: Lambda execution role with basic permissions

**Note**: The Lambda function itself is deployed separately via the deployment script, since code changes frequently.

## Prerequisites

1. **Terraform** installed (>= 1.0)
   ```bash
   # Ubuntu/Debian
   wget -O- https://apt.releases.hashicorp.com/gpg | sudo gpg --dearmor -o /usr/share/keyrings/hashicorp-archive-keyring.gpg
   echo "deb [signed-by=/usr/share/keyrings/hashicorp-archive-keyring.gpg] https://apt.releases.hashicorp.com $(lsb_release -cs) main" | sudo tee /etc/apt/sources.list.d/hashicorp.list
   sudo apt update && sudo apt install terraform

   # macOS
   brew install terraform

   # Verify
   terraform --version
   ```

2. **AWS CLI** configured
   ```bash
   aws configure
   ```

## Quick Start

### 1. Configure Variables

Create `terraform.tfvars`:
```bash
cp terraform.tfvars.example terraform.tfvars
```

Edit `terraform.tfvars`:
```hcl
project_name = "ma-teachers-contracts"
aws_region   = "us-east-1"
environment  = "prod"
```

### 2. Initialize Terraform

```bash
terraform init
```

This downloads the AWS provider and sets up the working directory.

### 3. Preview Changes

```bash
terraform plan
```

This shows what Terraform will create without making any changes.

### 4. Create Infrastructure

```bash
terraform apply
```

Type `yes` when prompted. This creates all AWS resources (~5-10 minutes).

### 5. View Outputs

```bash
terraform output
```

Or get a specific value:
```bash
terraform output website_url
terraform output api_endpoint
```

## Deployment Workflow

After infrastructure is created:

```bash
# Deploy backend
cd ../scripts
./deploy-backend-tf.sh

# Deploy frontend
./deploy-frontend-tf.sh
```

The deployment scripts automatically read values from Terraform outputs.

## Common Commands

```bash
# Initialize Terraform
terraform init

# Format code
terraform fmt

# Validate configuration
terraform validate

# Plan changes
terraform plan

# Apply changes
terraform apply

# Show current state
terraform show

# List all outputs
terraform output

# Get specific output
terraform output -raw s3_bucket

# Destroy everything
terraform destroy
```

## File Structure

```
terraform/
├── main.tf                    # Main infrastructure definitions
├── variables.tf               # Input variables
├── outputs.tf                 # Output values (used by deployment scripts)
├── terraform.tfvars.example   # Example variables file
├── terraform.tfvars          # Your variables (git-ignored)
├── .gitignore                # Terraform-specific ignores
└── README.md                 # This file
```

## Modifying Infrastructure

### Change Project Name

Edit `terraform.tfvars`:
```hcl
project_name = "new-project-name"
```

Then apply:
```bash
terraform apply
```

**Warning**: Changing the project name will recreate resources with new names.

### Change AWS Region

Edit `terraform.tfvars`:
```hcl
aws_region = "us-west-2"
```

**Warning**: This will recreate all resources in the new region.

### Update Lambda Settings

Edit `terraform.tfvars`:
```hcl
lambda_timeout = 60
lambda_memory  = 1024
```

Then apply:
```bash
terraform apply
```

## State Management

### Local State (Default)

Terraform stores state in `terraform.tfstate` (git-ignored).

**Important**: Don't delete this file! It tracks what resources exist.

### Remote State (Recommended for Teams)

Uncomment in `main.tf`:
```hcl
backend "s3" {
  bucket = "your-terraform-state-bucket"
  key    = "ma-teachers-contracts/terraform.tfstate"
  region = "us-east-1"
}
```

Then initialize:
```bash
terraform init -migrate-state
```

## Troubleshooting

### Issue: "Error: Error acquiring the state lock"

Someone else is running Terraform, or a previous run was interrupted.

**Solution**: Wait a few minutes, then try again. If stuck, you can force unlock (be careful):
```bash
terraform force-unlock <LOCK_ID>
```

### Issue: "NoSuchBucket" during apply

The state bucket doesn't exist.

**Solution**: Create the bucket first, or use local state.

### Issue: "InsufficientPermissions"

Your AWS user doesn't have required permissions.

**Solution**: Add these AWS managed policies:
- AmazonS3FullAccess
- CloudFrontFullAccess
- AWSLambda_FullAccess
- AmazonAPIGatewayAdministrator
- IAMFullAccess

### Issue: Changes show every time I run `terraform plan`

Some AWS resources have read-only attributes that change.

**Solution**: This is usually normal. Look for actual resource changes (create, update, destroy).

## Cleanup

To delete all infrastructure:

```bash
terraform destroy
```

Type `yes` when prompted. This removes:
- S3 bucket (must be empty first)
- CloudFront distribution (takes 15-30 minutes to fully delete)
- API Gateway
- IAM role
- All other resources

**Note**: Delete Lambda function manually first:
```bash
aws lambda delete-function --function-name ma-teachers-contracts-api
```

## Integration with Deployment Scripts

Deployment scripts read Terraform outputs:

```bash
# Get S3 bucket
terraform output -raw s3_bucket

# Get API endpoint
terraform output -raw api_endpoint

# Get all config as JSON
terraform output -json deployment_config
```

This ensures scripts always use the correct infrastructure values.

## Best Practices

1. **Always run `terraform plan` before `apply`**
   - Review changes before making them

2. **Use version control for .tf files**
   - Track infrastructure changes over time

3. **Never commit `terraform.tfvars`**
   - Contains project-specific settings
   - Already git-ignored

4. **Use remote state for teams**
   - Prevents conflicts
   - Provides state backup

5. **Tag resources appropriately**
   - Edit `tags` in `terraform.tfvars`

6. **Keep Terraform version consistent**
   - Specified in `main.tf`

## Resources Created

| Resource | Name | Purpose |
|----------|------|---------|
| S3 Bucket | `${project_name}-${account_id}` | Static hosting + deployment packages |
| CloudFront | `${project_name}-cloudfront` | CDN for frontend |
| API Gateway | `${project_name}-api` | REST API endpoint |
| IAM Role | `${project_name}-lambda-role` | Lambda execution permissions |
| OAC | `${project_name}-oac` | Secure CloudFront → S3 access |

## Additional Resources

- [Terraform AWS Provider Docs](https://registry.terraform.io/providers/hashicorp/aws/latest/docs)
- [Terraform CLI Commands](https://www.terraform.io/cli/commands)
- [Terraform Best Practices](https://www.terraform-best-practices.com/)
