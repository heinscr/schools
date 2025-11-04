# Terraform Setup - API Key Management

## Overview

The API key for authentication is now **automatically managed by Terraform**. This eliminates manual key generation and stores the key securely in Terraform state.

## What Changed

### New Terraform Resources

1. **[infrastructure/terraform/api_key.tf](infrastructure/terraform/api_key.tf)** (new file)
   - Generates a secure 32-character API key using `random_password`
   - Stored in Terraform state
   - Provides outputs to retrieve the key

2. **[infrastructure/terraform/main.tf](infrastructure/terraform/main.tf)** (updated)
   - Added `random` provider to required providers
   - Lambda environment now includes `API_KEY` from Terraform

3. **[deploy.sh](deploy.sh)** (updated)
   - Retrieves API key from Terraform output instead of `.env`
   - Automatically configures Lambda with the Terraform-managed key

## First Time Setup

After you've made these changes, you need to run Terraform to generate the API key:

```bash
cd infrastructure/terraform

# Initialize the new random provider
terraform init -upgrade

# Apply changes to generate the API key
terraform apply
```

Terraform will:
1. Generate a cryptographically secure API key
2. Store it in Terraform state
3. Update the Lambda function with the new key
4. Create a sensitive output so you can retrieve it

## Retrieving the API Key

### View the API Key

```bash
cd infrastructure/terraform
terraform output -raw api_key
```

**Important:** This output is marked as `sensitive`, so you'll need to explicitly request it.

### Store for Local Development

```bash
cd infrastructure/terraform
echo "API_KEY=$(terraform output -raw api_key)" >> ../backend/.env
```

Or manually copy the key to your `backend/.env` file.

## Deployment Workflow

The deployment script now handles everything automatically:

```bash
./deploy.sh
```

The script will:
1. Read the API key from Terraform output
2. Package the backend code
3. Deploy to Lambda with the API key as an environment variable

## Key Rotation

If you need to rotate the API key:

```bash
cd infrastructure/terraform

# Mark the key for recreation
terraform taint random_password.api_key

# Generate new key
terraform apply

# Deploy to update Lambda
cd ../..
./deploy.sh
```

## Security Benefits

✅ **No manual key generation** - Terraform handles it
✅ **Stored in Terraform state** - Use remote backend with encryption for production
✅ **No keys in .env committed** - Cleaner version control
✅ **Consistent across environments** - Same process for dev/prod
✅ **Easy rotation** - One Terraform command
✅ **Audit trail** - Terraform tracks changes

## Troubleshooting

### "API_KEY not found in Terraform" warning during deployment

This means Terraform hasn't generated the key yet. Run:

```bash
cd infrastructure/terraform
terraform apply
```

### Want to use a custom key for local testing

You can still override in your local `.env`:

```env
API_KEY=my-custom-local-key-for-testing
```

The deployment script prioritizes the Terraform-managed key for production deployments.
