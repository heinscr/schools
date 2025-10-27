# Quick Start Guide

## TL;DR - Get Running Fast

### First Time Setup

```bash
# 1. Install jq (if not installed)
sudo apt-get install jq

# 2. Configure AWS
aws configure

# 3. Create infrastructure
cd infrastructure/scripts
./setup-infrastructure.sh

# 4. Deploy backend
./deploy-backend.sh

# 5. Deploy frontend
./deploy-frontend.sh
```

Done! Your site is live.

## URLs

```bash
# Get your website URL
jq -r '.frontend.website_url' ../config/aws-config.json

# Get your API URL
jq -r '.backend.api_endpoint' ../config/aws-config.json
```

## Clean Up Everything

```bash
cd infrastructure/scripts
./cleanup-infrastructure.sh
```

Type `yes` when prompted.

## Redeploy After Code Changes

### Backend changes:
```bash
cd infrastructure/scripts
./deploy-backend.sh
```

### Frontend changes:
```bash
cd infrastructure/scripts
./deploy-frontend.sh
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
- IAMFullAccess (or at least role creation)

### "No such file: aws-config.json"
Run `./setup-infrastructure.sh` first

### CloudFront shows old version
Wait 5-10 minutes for cache invalidation, or force it:
```bash
CF_DIST=$(jq -r '.frontend.cloudfront_distribution_id' ../config/aws-config.json)
aws cloudfront create-invalidation --distribution-id $CF_DIST --paths "/*"
```

## File Structure

```
infrastructure/
├── scripts/
│   ├── setup-infrastructure.sh     # Run once to create AWS resources
│   ├── deploy-backend.sh          # Deploy backend changes
│   ├── deploy-frontend.sh         # Deploy frontend changes
│   └── cleanup-infrastructure.sh  # Delete everything
└── config/
    └── aws-config.json            # Created by setup (DO NOT COMMIT)
```

## What Gets Created in AWS

- **2 S3 Buckets**: Frontend hosting + Backend deployment packages
- **1 CloudFront Distribution**: CDN for frontend
- **1 API Gateway**: REST API endpoint
- **1 Lambda Function**: Backend API (when deployed)
- **1 IAM Role**: Lambda execution permissions
- **1 Origin Access Control**: CloudFront → S3 security

## Cost Estimate

With minimal traffic:
- **Free tier**: $0/month (first 12 months)
- **After free tier**: ~$5-20/month depending on traffic

## Development Workflow

```bash
# 1. Make changes to code locally
# 2. Test locally
npm run dev          # Frontend (http://localhost:5173)
uvicorn main:app --reload  # Backend (http://localhost:8000)

# 3. Deploy when ready
cd infrastructure/scripts
./deploy-backend.sh    # If backend changed
./deploy-frontend.sh   # If frontend changed
```

## Help

- Full docs: [README.md](README.md)
- Deployment guide: [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md)
- AWS issues: Check [Troubleshooting](README.md#troubleshooting) section
