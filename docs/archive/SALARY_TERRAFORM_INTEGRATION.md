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

### 3. API Gateway (Updated: Consolidated)
**Previously** used a separate HTTP API Gateway (v2), but **now consolidated** into the main REST API Gateway:

```hcl
resource "aws_api_gateway_resource" "salary_schedule_proxy" {
  rest_api_id = aws_api_gateway_rest_api.main.id
  parent_id   = aws_api_gateway_resource.salary_schedule_path.id
  path_part   = "{proxy+}"
}
```

**Consolidated Architecture:**
- Single REST API Gateway for all endpoints (districts + salaries)
- Both Lambdas use AWS_PROXY integration
- Simplifies infrastructure and reduces costs (no second API Gateway)
- All endpoints share the same domain and stage
- Salary routes: `/api/salary-schedule/{proxy+}`, `/api/salary-compare`, `/api/salary-heatmap`

### 4. Tags
Updated all resources to use `merge(local.common_tags, {...})` pattern consistent with existing infrastructure.

### 5. Security Features
Added to DynamoDB tables:
- Point-in-time recovery
- Server-side encryption

## Terraform Outputs

Added Lambda function outputs:

```hcl
output "salaries_lambda_function_name" {
  value       = aws_lambda_function.salaries.function_name
  description = "Name of the salaries Lambda function"
}

output "salaries_lambda_function_arn" {
  value       = aws_lambda_function.salaries.arn
  description = "ARN of the salaries Lambda function"
}
```

**Note:** Salary endpoints now use the main API Gateway endpoint (same as districts API).

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

**All endpoints now use the same API Gateway:**

- **Unified API:** `https://{api-id}.execute-api.us-east-2.amazonaws.com/prod/api/...`
  - Districts: `/api/districts/*`
  - Salary Schedule: `/api/salary-schedule/{districtId}`
  - Salary Compare: `/api/salary-compare`
  - Salary Heatmap: `/api/salary-heatmap`

Get the API endpoint:
```bash
cd infrastructure/terraform
terraform output api_endpoint
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
| REST API Gateway | $3.50 per million requests (shared with main API) |
| **Total** | **< $1/month** |

**Cost Savings:** Eliminated separate HTTP API Gateway (~$1-2/month savings).

## Frontend Integration

The frontend uses a single API endpoint for all requests:

```javascript
// frontend/src/services/api.js
const API_BASE_URL = import.meta.env.VITE_API_URL || import.meta.env.DISTRICT_API_URL || 'http://localhost:8000';

// All methods use the same base URL
async getSalarySchedules(districtId, year = null) {
  const url = `${API_BASE_URL}/api/salary-schedule/${districtId}${year || ''}`;
  // ...
}

async compareSalaries(education, credits, step, options = {}) {
  const url = `${API_BASE_URL}/api/salary-compare?${queryParams}`;
  // ...
}
```

**Environment Variable:** Set `VITE_API_URL` to your API Gateway endpoint.

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
