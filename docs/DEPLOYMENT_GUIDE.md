# Deployment Guide - Quick Reference

## Prerequisites Checklist

- [ ] AWS CLI installed (`aws --version`)
- [ ] AWS credentials configured (`aws configure`)
- [ ] jq installed (`jq --version`) - JSON processor for scripts
- [ ] Node.js 18+ installed (`node --version`)
- [ ] Python 3.12 installed (`python3 --version`)

### Installing jq

```bash
# Ubuntu/Debian
sudo apt-get install jq

# macOS
brew install jq
```

## First Time Setup

### 1. Configure AWS Credentials

```bash
aws configure
```

Enter:
- AWS Access Key ID
- AWS Secret Access Key
- Default region (e.g., `us-east-1`)
- Output format: `json`

### 2. Create Infrastructure

```bash
cd infrastructure/scripts
./setup-infrastructure.sh
```

Wait for completion (5-10 minutes). This creates:
- S3 buckets
- CloudFront distribution
- API Gateway
- IAM roles

### 3. Verify Configuration

```bash
cat ../config/aws-config.json
```

Save this file securely - it contains your deployment configuration.

## Regular Deployments

### Deploy Backend Changes

```bash
cd infrastructure/scripts
./deploy-backend.sh
```

Time: ~2-3 minutes

### Deploy Frontend Changes

```bash
cd infrastructure/scripts
./deploy-frontend.sh
```

Time: ~3-5 minutes (includes build + upload + CloudFront invalidation)

## Testing Deployments

### Test Backend

```bash
# Get API endpoint
API_ENDPOINT=$(jq -r '.backend.api_endpoint' ../config/aws-config.json)

# Test endpoints
curl $API_ENDPOINT/
curl $API_ENDPOINT/health
```

### Test Frontend

```bash
# Get website URL
WEBSITE_URL=$(jq -r '.frontend.website_url' ../config/aws-config.json)

# Open in browser
echo $WEBSITE_URL
```

## Common Workflows

### Full Deployment (Backend + Frontend)

```bash
cd infrastructure/scripts

# Deploy backend first
./deploy-backend.sh

# Wait for deployment
sleep 10

# Deploy frontend
./deploy-frontend.sh
```

### View Backend Logs

```bash
aws logs tail /aws/lambda/ma-teachers-contracts-api --follow
```

### Force CloudFront Cache Refresh

```bash
CF_DIST=$(jq -r '.frontend.cloudfront_distribution_id' ../config/aws-config.json)
aws cloudfront create-invalidation --distribution-id $CF_DIST --paths "/*"
```

## Troubleshooting

### Script fails with "config not found"
**Solution**: Run `setup-infrastructure.sh` first

### Backend returns 500 errors
**Solution**: Check Lambda logs:
```bash
aws logs tail /aws/lambda/ma-teachers-contracts-api --since 10m
```

### Frontend shows old version
**Solution**: Wait 5-10 minutes for CloudFront cache invalidation, or force invalidation

### Permission denied on scripts
**Solution**: Make scripts executable:
```bash
chmod +x infrastructure/scripts/*.sh
```

## Configuration Backup

### Backup Configuration

```bash
# Backup config to secure location
cp infrastructure/config/aws-config.json ~/aws-config-backup-$(date +%Y%m%d).json
```

### Restore Configuration

```bash
# Restore from backup
cp ~/aws-config-backup-YYYYMMDD.json infrastructure/config/aws-config.json
```

## Team Collaboration

### For Team Lead

1. Run `setup-infrastructure.sh` once
2. Share `aws-config.json` securely with team (encrypted email/secure file share)
3. Commit code changes (scripts are safe to commit)

### For Team Members

1. Receive `aws-config.json` from team lead
2. Place in `infrastructure/config/aws-config.json`
3. Run deployment scripts as needed

## Security Reminders

- ✓ Scripts are safe to commit to git
- ✗ **NEVER** commit `aws-config.json`
- ✗ **NEVER** commit `.env` files
- ✓ Use `.gitignore` to prevent accidental commits
- ✓ Share configs through secure channels only

## Cleanup & Reset

### Remove All AWS Resources

To delete everything and start fresh:

```bash
cd infrastructure/scripts
./cleanup-infrastructure.sh
```

The script will:
1. Ask for confirmation (type `yes` to proceed)
2. Delete Lambda function
3. Delete API Gateway
4. Disable CloudFront (takes 15-30 minutes to fully delete)
5. Empty and delete S3 buckets
6. Delete IAM role
7. Remove config file

After cleanup completes, you can run `./setup-infrastructure.sh` again to create fresh resources.

### Quick Cleanup (if you know what you're doing)

```bash
# Get current resource IDs
FRONTEND_BUCKET=$(jq -r '.frontend.s3_bucket' ../config/aws-config.json)
BACKEND_BUCKET=$(jq -r '.backend.s3_bucket' ../config/aws-config.json)

# Delete S3 buckets (fastest cleanup)
aws s3 rm s3://$FRONTEND_BUCKET --recursive && aws s3 rb s3://$FRONTEND_BUCKET
aws s3 rm s3://$BACKEND_BUCKET --recursive && aws s3 rb s3://$BACKEND_BUCKET

# Delete config to re-run setup
rm ../config/aws-config.json
```

## Cost Monitoring

Check current AWS costs:
```bash
aws ce get-cost-and-usage \
    --time-period Start=$(date -d '1 month ago' +%Y-%m-%d),End=$(date +%Y-%m-%d) \
    --granularity MONTHLY \
    --metrics BlendedCost
```

## Quick Commands Reference

```bash
# View all resources
jq '.' infrastructure/config/aws-config.json

# Get API endpoint
jq -r '.backend.api_endpoint' infrastructure/config/aws-config.json

# Get website URL
jq -r '.frontend.website_url' infrastructure/config/aws-config.json

# List Lambda functions
aws lambda list-functions --query 'Functions[?starts_with(FunctionName, `ma-teachers`)]'

# List S3 buckets
aws s3 ls | grep ma-teachers

# Check CloudFront distributions
aws cloudfront list-distributions --query 'DistributionList.Items[].{ID:Id,Domain:DomainName}'
```
