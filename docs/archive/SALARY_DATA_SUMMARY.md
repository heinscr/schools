# Teacher Salary Data - Implementation Summary

## What Was Created

### 1. Data File ✓
**Location:** `/data/salary_data.json`

- Converted from CSV to JSON format
- 312 salary records (Millis + Medway, 2021-2022)
- Easy to edit locally and extend with more districts

### 2. DynamoDB Tables ✓
**Files:** `infrastructure/terraform/dynamodb_salary_tables.tf`

Two tables created:
- **teacher-salaries** (normalized): One row per salary cell, enables flexible queries
- **teacher-salary-schedules** (aggregated): One row per schedule, fast grid display

Both with Global Secondary Indexes for efficient querying.

### 3. Lambda API Function ✓
**Files:**
- `backend/salaries.py` - Handler code (Python)
- `infrastructure/terraform/lambda_salaries.tf` - Terraform config

Four API endpoints:
1. `GET /api/salary-schedule/:districtId/:year?` - Display salary grid
2. `GET /api/salary-compare?education=M&credits=30&step=5` - Compare districts
3. `GET /api/salary-heatmap?education=M&credits=30&step=5` - Heatmap data
4. `GET /api/districts/:id/salary-metadata` - Available years, ranges

This script will:
1. ✓ Package Python Lambda (districts API)
2. ✓ **Package Python Lambda (salary API)** ← Automated!
3. ✓ Upload both to S3

### 5. Documentation ✓
**Files:**
- `docs/SALARY_DATA_DESIGN.md` - Architecture and design decisions
- `docs/SALARY_API_SETUP.md` - Deployment and usage guide

## Data Model

### Normalized Table (teacher-salaries)
```
PK: district_id (e.g., "medway")
SK: composite_key (e.g., "2021-2022#days-92-183#M#30#5")

Attributes:
- school_year, period, education, credits, step, salary
- district_name, district_type
- GSI1PK, GSI1SK (for type/year queries)
- GSI2PK, GSI2SK (for cross-district comparisons)
```

### Aggregated Table (teacher-salary-schedules)
```
PK: district_id
SK: schedule_key (e.g., "2021-2022#days-92-183")

Attributes:
- district_name, district_type, school_year, period
- lanes: {B, B+15, M, M+30, ...}
- steps: [{step: 1, B: 49875.50, M: 54568.09, ...}, ...]
- contract_term, contract_expiration, notes
```

## Use Cases Supported

### ✓ Current (Immediate)
1. **Display salary grid** for a district
   - Single query to schedules table
   - Returns full steps × lanes grid
   - Fast response (< 100ms)

2. **Show lane definitions** (Bachelor's + 30, Master's + 15, etc.)
   - Included in schedule response
   - Formatted labels ready for UI

3. **Contract metadata** (term, expiration)
   - Fields available in schedule items
   - To be populated from contract extraction

### ✓ Future (Analytical)
1. **Top paying districts** for specific credentials
   - Query: `education=M, credits=30, step=5`
   - Returns ranked list via GSI1
   - Can filter by district type

2. **Salary heatmap** for Massachusetts
   - Query: `education=M, credits=30, step=5`
   - Returns all districts via GSI2
   - Includes statistics (min, max, avg, median)

3. **Comparison by district type**
   - Regional vs Municipal vs Vocational
   - Filter available in all queries

## Next Steps

### Immediate
1. **Deploy infrastructure (one-time)**
   ```bash
   cd infrastructure/terraform
   terraform apply
   ```

2. **Load sample data**
   ```bash
   cd backend
   source venv/bin/activate
   python scripts/load_salary_data.py
   ```

3. **Deploy application (Lambda packaging is automated!)**
   ```bash
   ./deploy.sh
   ```

4. **Test API**
   ```bash
   curl https://YOUR_API_URL/api/salary-schedule/medway
   ```

**Note:** The `deploy.sh` script now automatically packages both Lambda functions (Python + Node.js), so step 2 from the old process is no longer needed!

### Short Term
1. **Add more districts** to salary_data.json
   - Can manually enter from contracts
   - Or extract using AWS Bedrock script (from feature branch)

2. **Build frontend components**
   - SalaryGrid component
   - SalaryComparison component
   - SalaryHeatmap component

3. **Integrate with existing UI**
   - Add salary tab to district details
   - Link from DistrictBrowser

### Long Term
1. **Extract all 77 contracts**
   - Return to `feature/contract-extraction` branch
   - Run Bedrock extraction script
   - Process and load all districts

2. **Add historical data**
   - Multiple years per district
   - Trend analysis
   - Growth calculations

3. **Advanced analytics**
   - Cost of living adjustments
   - Regional comparisons
   - Benefit package data

## File Structure

```
backend/
├── scripts/                          # Data loading scripts
│   ├── import_districts.py           # Import district metadata
│   ├── import_problem_districts.py   # Import problematic districts
│   └── load_salary_data.py           # Load salary data
├── salaries.py                       # Salaries API Lambda (Python)
├── services/                         # Service layer
│   ├── district_service.py
│   └── dynamodb_district_service.py
├── main.py                           # Districts API Lambda
├── database.py                       # Database utilities
├── models.py, schemas.py             # Data models
├── venv/                             # Python virtual environment
└── requirements.txt
```

## API Examples

### Display Grid
```javascript
// Frontend code
const schedule = await fetch('/api/salary-schedule/medway/2021-2022');
// Renders steps × lanes table
```

### Compare Districts
```javascript
// "What are top 10 districts for Master's + 30, Step 5?"
const top10 = await fetch('/api/salary-compare?education=M&credits=30&step=5&limit=10');
// Returns: [{rank: 1, district: "Medway", salary: 68130.14}, ...]
```

### Heatmap
```javascript
// "Show all districts for Master's + 30, Step 5"
const heatmap = await fetch('/api/salary-heatmap?education=M&credits=30&step=5');
// Returns: {statistics: {...}, data: [{district, salary}, ...]}
```

## Cost Estimate

- **Storage**: $0.01/month (26MB across both tables)
- **Queries**: Free tier covers typical usage (< 25M RCU/month)
- **Lambda**: Free tier covers typical usage (< 1M requests/month)
- **Total**: **< $1/month**

## Questions?

See detailed documentation:
- Architecture: `docs/SALARY_DATA_DESIGN.md`
- Setup guide: `docs/SALARY_API_SETUP.md`
