# DynamoDB Setup Guide

This document explains the DynamoDB implementation for the MA Teachers Contracts application.

## Table Design

### Districts Table

The application uses a single-table design with the following schema:

**Table Name:** `ma-teachers-contracts-districts`

**Primary Key:**
- `PK` (String, Partition Key): `DISTRICT#{district_id}`
- `SK` (String, Sort Key): `METADATA` or `TOWN#{town_name}`

**Global Secondary Index (GSI_TOWN):**
- `GSI_TOWN_PK` (String, Partition Key): `TOWN#{town_name}`
- `GSI_TOWN_SK` (String, Sort Key): `DISTRICT#{district_name}`

**Attributes:**
- `district_id`: Unique UUID for the district
- `name`: District name
- `name_lower`: Lowercase district name (for case-insensitive search)
- `main_address`: District main office address
- `towns`: List of town names
- `created_at`: ISO timestamp
- `updated_at`: ISO timestamp
- `entity_type`: Either "district" or "district_town"

### Access Patterns

1. **Get district by ID**: Query PK=`DISTRICT#{id}` and SK=`METADATA`
2. **Search districts by name**: Scan with filter on `name_lower`
3. **Search districts by town**: Query GSI_TOWN with GSI_TOWN_PK=`TOWN#{town}`
4. **List all districts**: Scan with filter on `entity_type=district`

## Local Development

### Option 1: Use AWS DynamoDB (Requires AWS Account)

1. Create a `.env` file from `.env.example`:
   ```bash
   cp .env.example .env
   ```

2. Ensure you have AWS credentials configured:
   ```bash
   aws configure
   ```

3. Deploy the Terraform infrastructure to create the table:
   ```bash
   cd ../infrastructure/terraform
   terraform init
   terraform apply
   ```

4. Run the sample data script:
   ```bash
   cd ../../backend
   source venv/bin/activate
   python init_dynamodb_sample_data.py
   ```

5. Start the API:
   ```bash
   uvicorn main:app --reload
   ```

### Option 2: Use DynamoDB Local (No AWS Account Needed)

1. Install and run DynamoDB Local using Docker:
   ```bash
   docker run -p 8000:8000 amazon/dynamodb-local
   ```

2. Create a `.env` file and set the endpoint:
   ```bash
   cp .env.example .env
   # Edit .env and uncomment:
   DYNAMODB_ENDPOINT=http://localhost:8000
   ```

3. Run the sample data script (it will create the table locally):
   ```bash
   source venv/bin/activate
   python init_dynamodb_sample_data.py
   ```

4. Start the API on a different port (DynamoDB Local uses 8000):
   ```bash
   uvicorn main:app --reload --port 8001
   ```

## Production Deployment

### Terraform Resources

The following resources are created by Terraform:

1. **DynamoDB Table**: `aws_dynamodb_table.districts`
   - Billing mode: PAY_PER_REQUEST (on-demand)
   - Point-in-time recovery: Enabled
   - Encryption: Enabled

2. **IAM Policy**: Attached to Lambda execution role
   - Permissions: GetItem, PutItem, UpdateItem, DeleteItem, Query, Scan
   - Resources: Table and all indexes

### Environment Variables for Lambda

When deploying to Lambda, set these environment variables:

```bash
AWS_REGION=us-east-1
DYNAMODB_DISTRICTS_TABLE=ma-teachers-contracts-districts
```

The table name will be output by Terraform after `terraform apply`.

## API Endpoints

All endpoints remain the same as before:

- `GET /api/districts` - List districts with optional filters
  - Query params: `name`, `town`, `limit`, `offset`
- `GET /api/districts/search?q={query}` - Search by name or town
- `GET /api/districts/{district_id}` - Get specific district
- `POST /api/districts` - Create new district
- `PUT /api/districts/{district_id}` - Update district
- `DELETE /api/districts/{district_id}` - Delete district

## Cost Estimate

With DynamoDB on-demand pricing (as of 2025):

**Storage:** $0.25/GB/month
- ~1000 districts × ~2KB each = ~2MB = **$0.01/month**

**Reads:** $0.25 per million reads
- Estimate 10,000 reads/month = **$0.003/month**

**Writes:** $1.25 per million writes
- Estimate 100 writes/month = **$0.0001/month**

**Total estimated cost: ~$0.30-$1/month** for typical usage

This is significantly cheaper than RDS (~$12+/month) for small-scale applications.

## Data Migration

If you have existing data in SQLite, you can migrate it:

1. Export data from SQLite
2. Transform to DynamoDB format
3. Use the `DynamoDBDistrictService.create_district()` method to insert

(Migration script not included - can be created if needed)

## Monitoring

Use AWS CloudWatch to monitor:
- Read/Write capacity consumption
- Throttled requests
- User errors
- Table size

## Troubleshooting

**Issue:** "ResourceNotFoundException: Requested resource not found"
- **Solution**: Ensure Terraform has been applied and table exists in AWS

**Issue:** Slow queries when searching by name
- **Solution**: Name searches use Scan operations which are slower. Consider adding a GSI for name searches if this becomes a bottleneck.

**Issue:** Connection timeout when using AWS DynamoDB
- **Solution**: Check your AWS credentials and network connectivity

**Issue:** "ValidationException: One or more parameter values were invalid"
- **Solution**: Check that your item structure matches the schema defined in `dynamodb_district_service.py`
