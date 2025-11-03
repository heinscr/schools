# Salary Data Terraform Integration

## Summary

The salary data infrastructure has been successfully integrated into the existing Terraform configuration in `/infrastructure/terraform/`.

## Files Moved

1. **`infrastructure/dynamodb_salary_tables.tf`** → **`infrastructure/terraform/dynamodb_salary_tables.tf`**
2. **`infrastructure/lambda_salaries.tf`** → **`infrastructure/terraform/lambda_salaries.tf`**

## Changes Made

### 1. Resource Naming
Updated all resources to use `${var.project_name}` instead of `${var.environment}` to match the existing infrastructure pattern:

- **DynamoDB Tables:**
  - `dev-teacher-salaries` → `ma-teachers-contracts-teacher-salaries`
  - `dev-teacher-salary-schedules` → `ma-teachers-contracts-teacher-salary-schedules`

- **Lambda Function:**
  - `dev-salaries-api` → `ma-teachers-contracts-salaries-api`

- **IAM Role:**
  - `dev-salary-lambda-role` → `ma-teachers-contracts-salary-lambda-role`

### 2. S3 Bucket Reference
Fixed Lambda function to reference the correct S3 bucket:
- **Before:** `aws_s3_bucket.frontend.id`
- **After:** `aws_s3_bucket.main.id`

### 3. API Gateway
Created a new HTTP API Gateway (v2) for salary endpoints since the existing infrastructure uses REST API Gateway (v1):

```hcl
resource "aws_apigatewayv2_api" "salaries" {
  name          = "${var.project_name}-salaries-api"
  protocol_type = "HTTP"
  # ... CORS configuration
}
```

**Why separate API Gateway?**
- Existing infrastructure uses REST API Gateway with proxy integration
- Salary API uses HTTP API Gateway (v2) which is:
  - Simpler and cheaper
  - Better for Lambda proxy integrations
  - Easier to configure CORS
  - Auto-deploys changes

### 4. Tags
Updated all resources to use `merge(local.common_tags, {...})` pattern consistent with existing infrastructure.

### 5. Security Features
Added to DynamoDB tables:
- Point-in-time recovery
- Server-side encryption

## New Outputs

Added to Terraform outputs:

```hcl
output "salaries_api_endpoint" {
  value       = aws_apigatewayv2_stage.salaries.invoke_url
  description = "Salary API endpoint URL"
}

output "salaries_api_id" {
  value       = aws_apigatewayv2_api.salaries.id
  description = "Salary HTTP API Gateway ID"
}
```

## Updated Scripts

### `backend/scripts/load_salary_data.py`
Updated default table names to match new naming convention:
- **Before:** `dev-teacher-salaries`, `dev-teacher-salary-schedules`
- **After:** `ma-teachers-contracts-teacher-salaries`, `ma-teachers-contracts-teacher-salary-schedules`

The script is now located in `backend/scripts/` for easier access to the backend venv.

### `deploy.sh`
Already configured to package and deploy salary Lambda (no changes needed).

## Deployment

### First-time Setup

1. **Initialize Terraform** (if not already done):
   ```bash
   cd infrastructure/terraform
   terraform init
   ```

2. **Deploy infrastructure**:
   ```bash
   terraform plan  # Review changes
   terraform apply # Create resources
   ```

3. **Load salary data**:
   ```bash
   cd backend
   source venv/bin/activate
   python scripts/load_salary_data.py
   ```

4. **Deploy application**:
   ```bash
   ./deploy.sh
   ```

### Subsequent Deployments

Just run `./deploy.sh` from the project root - it handles everything automatically.

## API Endpoints

The salary API will be available at a separate endpoint from the main API:

- **Main API (districts):** `https://{api-id}.execute-api.us-east-1.amazonaws.com/prod/api/...`
- **Salary API:** `https://{http-api-id}.execute-api.us-east-1.amazonaws.com/api/...`

Get the salary API endpoint:
```bash
cd infrastructure/terraform
terraform output salaries_api_endpoint
```

## Verification

To verify the integration was successful:

```bash
cd infrastructure/terraform

# Validate configuration
terraform validate

# Check planned resources
terraform plan

# View outputs after deployment
terraform output
```

## Cost Impact

Adding the salary infrastructure:

| Resource | Monthly Cost |
|----------|-------------|
| DynamoDB Tables (2) | ~$0.01 (26MB storage) |
| Lambda Function | Free tier |
| HTTP API Gateway | $1 per million requests |
| **Total** | **< $1/month** |

## Frontend Integration

The frontend will need to use the separate salary API endpoint. Update your API configuration:

```javascript
// config.js
export const API_ENDPOINTS = {
  main: import.meta.env.DISTRICT_API_URL,        // District API
  salary: import.meta.env.VITE_SALARY_API_URL // Salary API
};
```

Or retrieve dynamically:
```javascript
const salaryEndpoint = await fetch(`${mainAPI}/api/config/salary-endpoint`);
```

## Documentation Updates

Updated documentation files:
- [x] `docs/SALARY_DATA_SUMMARY.md` - File paths corrected
- [x] `docs/SALARY_API_SETUP.md` - Paths and instructions updated
- [x] `backend/scripts/load_salary_data.py` - Moved from scripts/ to backend/scripts/
- [x] `backend/scripts/import_districts.py` - Moved with workflow integration
- [x] `backend/salaries.py` - Rewritten from Node.js to Python
- [x] This integration guide created

## Troubleshooting

### Terraform Errors

**"Resource already exists"**
- If tables were created manually, import them first:
  ```bash
  terraform import aws_dynamodb_table.teacher_salaries ma-teachers-contracts-teacher-salaries
  terraform import aws_dynamodb_table.teacher_salary_schedules ma-teachers-contracts-teacher-salary-schedules
  ```

**"Lambda function not found"**
- Deploy creates the Lambda, but code must be uploaded first
- The `deploy.sh` script handles this automatically

### Data Loading Errors

**"Table not found"**
- Ensure Terraform has been applied successfully
- Check table names with: `aws dynamodb list-tables`

**"Permission denied"**
- Ensure AWS credentials are configured
- Check region matches Terraform configuration
