# Salary Processing Implementation Summary

## ✅ Completed: Backend & Infrastructure

### 1. Infrastructure (Terraform)

**File: `infrastructure/terraform/salary_processing.tf`**
- ✅ SQS queue for PDF processing (`salary-processing` + DLQ)
- ✅ Lambda function: `salary-processor` (PDF extraction)
- ✅ Lambda function: `salary-normalizer` (global normalization)
- ✅ IAM roles and policies for:
  - S3 access (contracts/pdfs/, contracts/json/)
  - DynamoDB access
  - Textract access
  - SQS consume
  - Lambda invoke
- ✅ SQS trigger for processor Lambda

**File: `infrastructure/terraform/main.tf`** (updated)
- ✅ TTL enabled on DynamoDB table (attribute: `ttl`)
- ✅ API Lambda environment variables updated:
  - `S3_BUCKET_NAME`
  - `SALARY_PROCESSING_QUEUE_URL`
  - `SALARY_NORMALIZER_LAMBDA_ARN`

### 2. Backend Service Layer

**File: `backend/services/salary_jobs.py`**
- ✅ `SalaryJobsService` class with methods:
  - `create_job()` - Upload PDF, create job, send to SQS
  - `get_job()` - Get job status
  - `update_job_status()` - Update processing status
  - `delete_job()` - Delete job and S3 files
  - `get_extracted_data_preview()` - Preview extracted data
  - `apply_salary_data()` - Replace district salary data
  - `get_normalization_status()` - Check if normalization needed
  - `start_normalization_job()` - Trigger global normalization
  - `get_normalization_job()` - Get running normalization job

**Features:**
- ✅ Metadata change detection (max_step, edu_credit_combos)
- ✅ Automatic normalization flag setting
- ✅ Only one normalization job at a time
- ✅ TTL on job records (30 days)

### 3. Admin API Endpoints

**File: `backend/main.py`** (added endpoints)
- ✅ `POST /api/admin/districts/{district_id}/salary-schedule/upload`
  - Uploads PDF, creates job, returns job_id
  - Protected with `require_admin_role`

- ✅ `GET /api/admin/districts/{district_id}/salary-schedule/jobs/{job_id}`
  - Returns job status, records_count, years_found, preview data
  - Shows error if failed

- ✅ `PUT /api/admin/districts/{district_id}/salary-schedule/apply/{job_id}`
  - Deletes old salary data
  - Loads new salary data
  - Updates metadata if changed
  - Returns needs_global_normalization flag

- ✅ `DELETE /api/admin/districts/{district_id}/salary-schedule/jobs/{job_id}`
  - Rejects job and deletes S3 files

- ✅ `GET /api/admin/global/normalization/status`
  - Returns needs_normalization, job_running, last_normalized_at

- ✅ `POST /api/admin/global/normalize`
  - Starts global normalization (async Lambda invocation)
  - Returns job_id

### 4. Lambda Functions

**File: `backend/lambdas/processor.py`**
- ✅ Triggered by SQS messages
- ✅ Downloads PDF from S3
- ✅ Uses `HybridContractExtractor` (pdfplumber + Textract)
- ✅ Stores extracted JSON to S3
- ✅ Updates job status (processing → completed/failed)
- ✅ Error handling with job status updates

**File: `backend/lambdas/normalizer.py`**
- ✅ Runs normalization logic from `scripts/normalize_salaries.py`
- ✅ Phase 1: Fill down (missing steps)
- ✅ Phase 2: Fill right (missing edu+credit combos)
- ✅ Updates METADATA#MAXVALUES
- ✅ Clears needs_normalization flag
- ✅ Tracks normalization job status

## DynamoDB Schema Changes

### New Item Types

**Processing Jobs:**
```
PK: JOB#{jobId}
SK: METADATA
Attributes:
  - job_id
  - district_id
  - district_name
  - status: pending|processing|completed|failed
  - s3_pdf_key: contracts/pdfs/{districtId}.pdf
  - s3_json_key: contracts/json/{districtId}.json
  - extracted_records_count
  - years_found[]
  - error_message
  - uploaded_by (cognito sub)
  - created_at, updated_at
  - ttl (30 days)
```

**Normalization Status:**
```
PK: METADATA#NORMALIZATION
SK: STATUS
Attributes:
  - needs_normalization: boolean
  - last_normalized_at
  - last_normalization_job_id
```

**Normalization Job (running):**
```
PK: NORMALIZATION_JOB#RUNNING
SK: METADATA
Attributes:
  - job_id
  - status: running
  - started_at
  - triggered_by (cognito sub)
  - ttl (30 days)
```

**Normalization Job (completed/failed):**
```
PK: NORMALIZATION_JOB#{jobId}
SK: METADATA
Attributes:
  - job_id
  - status: completed|failed
  - completed_at / failed_at
  - records_created
  - error_message
```

## S3 Structure

```
s3://{bucket}/contracts/
├── pdfs/
│   ├── {districtId}.pdf   # One per district, replaced on new upload
│   └── ...
└── json/
    ├── {districtId}.json  # Extracted data, replaced on new upload
    └── ...
```

## API Flow

### Upload Flow
```
1. Admin uploads PDF
   → POST /api/admin/districts/{id}/salary-schedule/upload

2. API validates admin, uploads to S3
   → Creates job record (status: pending)
   → Sends message to SQS
   → Returns job_id

3. Frontend polls job status every 2 seconds
   → GET /api/admin/districts/{id}/salary-schedule/jobs/{job_id}

4. SQS triggers processor Lambda
   → Updates job (status: processing)
   → Extracts data with HybridContractExtractor
   → Stores JSON to S3
   → Updates job (status: completed) with records_count, years_found

5. Frontend shows preview data
   → Admin reviews extracted data
   → Admin clicks "Apply" or "Reject"

6. If Apply:
   → PUT /api/admin/districts/{id}/salary-schedule/apply/{job_id}
   → Deletes existing salary data for district
   → Loads new salary data
   → Checks if metadata changed
   → Returns needs_global_normalization flag

7. If metadata changed:
   → Frontend prompts: "Normalize all districts?"
   → If yes: POST /api/admin/global/normalize
   → Triggers normalizer Lambda (async)
   → Sets normalization badge visible

8. Normalization runs in background
   → Badge stays visible while needs_normalization=true
   → When complete, badge disappears
```

## 📋 TODO: Frontend Components

### 1. SalaryUploadModal Component
**Location:** `frontend/src/components/admin/SalaryUploadModal.jsx`

**Features needed:**
- Show district name
- File picker (PDF only)
- Upload progress bar
- Processing status (polling job endpoint)
- Preview table (using SalaryTable component)
- Accept/Reject buttons
- Warning message if metadata changed

### 2. User Profile Button Badge
**Location:** `frontend/src/components/UserProfileButton.jsx`

**Features needed:**
- Red dot indicator when needs_normalization=true
- Poll `/api/admin/global/normalization/status` every 30 seconds
- Only visible to admins

### 3. User Profile Menu Item
**Location:** `frontend/src/components/UserProfileMenu.jsx`

**Features needed:**
- "Normalize All Districts" menu item
- Click opens confirmation modal
- Shows "Normalizing..." state while running
- Calls `POST /api/admin/global/normalize`

### 4. District Browser Integration
**Location:** `frontend/src/pages/DistrictBrowser.jsx`

**Features needed:**
- Upload icon in salary table header (admin only)
- Opens SalaryUploadModal on click
- Refreshes district data after successful apply

## 📋 TODO: Deployment Scripts

### Lambda Deployment

Need to create/update deployment scripts to package and deploy Lambda functions:

1. **Processor Lambda Package:**
   - Include: `lambdas/processor.py`
   - Include: `services/hybrid_extractor.py`
   - Include: `services/contract_processor.py`
   - Include: `services/table_extractor.py`
   - Include: dependencies (boto3, pdfplumber, etc.)
   - Deploy to: `s3://{bucket}/backend/salary-processor.zip`

2. **Normalizer Lambda Package:**
   - Include: `lambdas/normalizer.py`
   - Include: dependencies (boto3)
   - Deploy to: `s3://{bucket}/backend/salary-normalizer.zip`

3. **Update existing deploy script:**
   - Add Lambda packaging steps
   - Upload to S3
   - Update Lambda function code

## Testing Checklist

### Backend Testing (Ready Now)
- [ ] Deploy Terraform changes
- [ ] Test API endpoints with Postman/curl:
  - [ ] Upload PDF (should create job)
  - [ ] Poll job status (should show processing → completed)
  - [ ] Get preview data
  - [ ] Apply salary data
  - [ ] Check normalization status
  - [ ] Start normalization

### Frontend Testing (After Implementation)
- [ ] Upload modal opens
- [ ] PDF upload works
- [ ] Status polling shows progress
- [ ] Preview data displays correctly
- [ ] Apply/Reject buttons work
- [ ] Normalization badge appears/disappears
- [ ] Normalization menu item works

### Integration Testing
- [ ] End-to-end: Upload Bedford contract PDF
- [ ] Verify extraction (should get 234 records)
- [ ] Apply to district
- [ ] Verify salary schedule updated
- [ ] Trigger normalization
- [ ] Verify all districts normalized

## Next Steps

1. **Test Backend Immediately:**
   ```bash
   # Deploy Terraform
   cd infrastructure/terraform
   terraform init
   terraform plan
   terraform apply

   # Test API locally
   cd ../../backend
   python -m uvicorn main:app --reload
   ```

2. **Create Frontend Components** (pending)

3. **Update Deployment Scripts** (pending)

4. **End-to-End Testing**

## Environment Variables Needed

**Backend (.env):**
```
DYNAMODB_TABLE_NAME=schools-data
S3_BUCKET_NAME=schools-{account-id}
SALARY_PROCESSING_QUEUE_URL=https://sqs.us-east-1.amazonaws.com/...
SALARY_NORMALIZER_LAMBDA_ARN=arn:aws:lambda:us-east-1:...
COGNITO_USER_POOL_ID=...
COGNITO_CLIENT_ID=...
COGNITO_REGION=us-east-1
```

**Lambda Environment (set by Terraform):**
- Processor: `DYNAMODB_TABLE_NAME`, `S3_BUCKET_NAME`, `CONTRACTS_PREFIX`
- Normalizer: `DYNAMODB_TABLE_NAME`

## Notes

- ✅ All admin endpoints require `require_admin_role` dependency
- ✅ PDF files are replaced per district (not versioned)
- ✅ JSON files are replaced per district (not versioned)
- ✅ Job records auto-expire after 30 days (TTL)
- ✅ Only one normalization job can run at a time
- ✅ Error handling stores failed jobs for debugging
- ✅ Extracted data preview limited to 10 records
- ✅ Years are in "YYYY-YYYY" format (e.g., "2024-2025")
