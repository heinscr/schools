# Terraform Quick Start

Get your infrastructure running in 5 minutes!

## Step 1: Install Terraform

```bash
# Ubuntu/Debian
sudo apt-get update && sudo apt-get install -y gnupg software-properties-common
wget -O- https://apt.releases.hashicorp.com/gpg | \
    gpg --dearmor | \
    sudo tee /usr/share/keyrings/hashicorp-archive-keyring.gpg
echo "deb [signed-by=/usr/share/keyrings/hashicorp-archive-keyring.gpg] \
    https://apt.releases.hashicorp.com $(lsb_release -cs) main" | \
    sudo tee /etc/apt/sources.list.d/hashicorp.list
sudo apt update && sudo apt install terraform

# macOS
brew install terraform

# Verify
terraform --version
```

## Step 2: Configure AWS

```bash
aws configure
# Enter your AWS credentials
```

## Step 3: Setup Terraform

```bash
cd infrastructure/terraform

# Create variables file
cp terraform.tfvars.example terraform.tfvars

# Edit if needed (optional - defaults work fine)
# nano terraform.tfvars

# Initialize
terraform init
```

## Step 4: Create Infrastructure

```bash
# Preview what will be created
terraform plan

# Create everything
terraform apply
# Type: yes
```

Wait 5-10 minutes for resources to be created.

## Step 5: Deploy Application

```bash
cd ../scripts

# Deploy backend
./deploy-backend-tf.sh

# Deploy frontend
./deploy-frontend-tf.sh
```

## Done!

Get your website URL:
```bash
cd infrastructure/terraform
terraform output website_url
```

## Daily Workflow

```bash
# Make code changes to frontend or backend

# Deploy backend if changed
cd infrastructure/scripts
./deploy-backend-tf.sh

# Deploy frontend if changed
./deploy-frontend-tf.sh
```

## Make Infrastructure Changes

```bash
cd infrastructure/terraform

# Edit terraform.tfvars or *.tf files

# Preview changes
terraform plan

# Apply changes
terraform apply
```

## View Current State

```bash
cd infrastructure/terraform

# See all resources
terraform show

# See outputs
terraform output

# See specific value
terraform output -raw website_url
```

## Clean Up Everything

```bash
cd infrastructure/terraform

# Delete Lambda first (not managed by Terraform)
aws lambda delete-function --function-name ma-teachers-contracts-api

# Empty S3 bucket
aws s3 rm s3://$(terraform output -raw s3_bucket) --recursive

# Destroy infrastructure
terraform destroy
# Type: yes
```

## Troubleshooting

### "command not found: terraform"
Install Terraform (see Step 1)

### "NoCredentialProviders"
Run `aws configure` (see Step 2)

### "Error acquiring the state lock"
Wait a few minutes, someone else is running Terraform

### "Error creating CloudFront Distribution"
CloudFront takes time. Wait 5-10 minutes and retry.

### Deployment scripts fail
Make sure you ran `terraform apply` first

## Comparison: Terraform vs Bash Scripts

### Old Way (Bash Scripts):
```bash
./setup-infrastructure.sh    # Create infrastructure
./deploy-backend.sh           # Deploy code
./deploy-frontend.sh          # Deploy code
./cleanup-infrastructure.sh   # Delete everything
```

### New Way (Terraform + Bash):
```bash
# One time: Create infrastructure
terraform apply

# Daily: Deploy code
./deploy-backend-tf.sh
./deploy-frontend-tf.sh

# Cleanup
terraform destroy
```

## Why This is Better

✅ **Idempotent**: Safe to run multiple times
✅ **Trackable**: See what changed
✅ **Reversible**: Easy rollback
✅ **Declarative**: Describe what you want
✅ **Industry standard**: Used everywhere

## Next Steps

- Read [terraform/README.md](terraform/README.md) for detailed docs
- Learn Terraform: https://learn.hashicorp.com/terraform
- Customize `terraform.tfvars` for your project
