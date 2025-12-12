# Teacher Salary API Setup Guide

## Overview

This guide covers deploying the teacher salary data infrastructure and API endpoints.

## Architecture

```
┌─────────────────┐
│  salary_data.json│  ← Edit this file locally
└────────┬────────┘
         │
         ▼
┌─────────────────────────────────────────┐
│  DynamoDB Tables                        │
├─────────────────────────────────────────┤
│  1. teacher-salaries (normalized)       │
│     - One item per salary cell          │
│     - GSI1: Query by type/year          │
│     - GSI2: Compare districts           │
│                                         │
│  2. teacher-salary-schedules (cache)    │
│     - One item per schedule             │
│     - Fast salary grid display          │
└────────┬────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────┐
│  Lambda Function: salaries-api          │
│  Routes:                                │
│  - GET /api/salary-schedule/:id/:year?  │
│  - GET /api/salary-compare              │
│  - GET /api/salary-heatmap              │
│  - GET /api/districts/:id/salary-metadata│
└─────────────────────────────────────────┘
```

## Data File

### Location
`/data/salary_data.json`

### Format
```json
[
  {
    "district_id": "medway",
    "district_name": "Medway",
    "school_year": "2021-2022",
    "period": "days-92-183",
    "education": "M",
    "credits": 30,
    "step": 5,
    "salary": 68130.14
  }
]
```

### Adding New Data
1. Edit `/data/salary_data.json` directly
2. Run the load script to update DynamoDB:
   ```bash
   cd backend
   source venv/bin/activate
   python scripts/load_salary_data.py
   ```

## Deployment Steps

### 1. Deploy DynamoDB Tables (One-time setup)

```bash
cd infrastructure/terraform

# Initialize Terraform (if not done)
terraform init

# Plan the changes
terraform plan

# Apply the salary table infrastructure
terraform apply
```

This creates:
- `ma-teachers-contracts-teacher-salaries` - Main normalized table
- `ma-teachers-contracts-teacher-salary-schedules` - Cache table
- Salary Lambda function
- API Gateway routes (integrated with main API)

### 2. Load Data into DynamoDB

```bash
# Install boto3 if needed
cd backend
source venv/bin/activate

# Load data (uses default table names)
python scripts/load_salary_data.py

# Or specify custom table names
python scripts/load_salary_data.py prod-teacher-salaries prod-teacher-salary-schedules prod-districts-table
```

Output:
```
Loading salary data from JSON...
✓ Loaded 312 salary records

Creating normalized items...
✓ Created 312 normalized items

Creating aggregated schedule items...
✓ Created 4 schedule items

Writing to DynamoDB...
  Progress: 312/312 items written
✓ Normalized items complete: Written: 312, Failed: 0

  Progress: 4/4 items written
✓ Schedule items complete: Written: 4, Failed: 0
```

### 3. Deploy Application (Including Salary Lambda)

The `deploy.sh` script now automatically packages and deploys the salary Lambda:

```bash
# From project root
./deploy.sh
```

This script will:
1. ✓ Package Python Lambda (districts API)
2. ✓ **Package Python Lambda (salary API)** ← Automated!
3. ✓ Upload both to S3
4. ✓ Deploy Lambda functions
5. ✓ Build and deploy frontend
6. ✓ Invalidate CloudFront cache

### 4. Test the API

Get your API Gateway URL:
```bash
terraform output api_gateway_url
```

Test endpoints:
```bash
# Get salary schedule for a district
curl https://YOUR_API_URL/api/salary-schedule/medway

# Compare salaries across districts
curl "https://YOUR_API_URL/api/salary-compare?education=M&credits=30&step=5&limit=10"

# Get heatmap data
curl "https://YOUR_API_URL/api/salary-heatmap?education=M&credits=30&step=5"

# Get district salary metadata
curl https://YOUR_API_URL/api/districts/medway/salary-metadata
```

## API Endpoints

### 1. GET /api/salary-schedule/:districtId/:year?

Get full salary schedule(s) for a district.

**Parameters:**
- `districtId` (path): District ID (e.g., "medway")
- `year` (path, optional): School year (e.g., "2021-2022")

**Response:**
```json
[
  {
    "district_id": "medway",
    "district_name": "Medway",
    "school_year": "2021-2022",
    "period": "days-92-183",
    "lanes": {
      "B": {"label": "Bachelor's", "education": "B", "credits": 0},
      "M+30": {"label": "Master's + 30", "education": "M", "credits": 30}
    },
    "steps": [
      {"step": 1, "B": 49875.50, "M+30": 57173.87},
      {"step": 2, "B": 52478.02, "M+30": 59791.63}
    ]
  }
]
```

### 2. GET /api/salary-compare

Compare salaries across districts for specific credentials.

**Query Parameters:**
- `education` (required): B, M, or D
- `credits` (required): 0, 15, 30, 45, or 60
- `step` (required): 1-14
- `districtType` (optional): municipal, regional_academic, etc.
- `year` (optional): School year (default: "2021-2022")
- `limit` (optional): Max results (default: 10)

**Example:**
```
GET /api/salary-compare?education=M&credits=30&step=5&limit=10
```

**Response:**
```json
{
  "query": {
    "education": "M",
    "credits": 30,
    "step": 5,
    "year": "2021-2022"
  },
  "results": [
    {
      "rank": 1,
      "district_id": "medway",
      "district_name": "Medway",
      "district_type": "municipal",
      "salary": 68130.14
    }
  ],
  "total": 10
}
```

### 3. GET /api/salary-heatmap

Get salary data for all districts (for heatmap visualization).

**Query Parameters:**
- `education` (required): B, M, or D
- `credits` (required): 0, 15, 30, 45, or 60
- `step` (required): 1-14
- `year` (optional): School year (default: "2021-2022")

**Example:**
```
GET /api/salary-heatmap?education=M&credits=30&step=5
```

**Response:**
```json
{
  "query": {
    "education": "M",
    "credits": 30,
    "step": 5,
    "year": "2021-2022"
  },
  "statistics": {
    "min": 58000,
    "max": 72000,
    "avg": 65123.45,
    "median": 65500
  },
  "data": [
    {
      "district_id": "medway",
      "district_name": "Medway",
      "district_type": "municipal",
      "salary": 68130.14
    }
  ]
}
```

### 4. GET /api/districts/:id/salary-metadata

Get available salary data for a district.

**Response:**
```json
{
  "district_id": "medway",
  "district_name": "Medway",
  "available_years": ["2021-2022"],
  "latest_year": "2021-2022",
  "salary_range": {
    "min": 49875.50,
    "max": 97111.87
  },
  "schedules": [
    {
      "school_year": "2021-2022",
      "period": "days-92-183",
      "contract_term": "2021-2024",
      "contract_expiration": "2024-08-31"
    }
  ]
}
```

## Frontend Integration

### Example: Display Salary Grid

```javascript
import { useState, useEffect } from 'react';

function SalaryGrid({ districtId, schoolYear }) {
  const [schedule, setSchedule] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchSchedule = async () => {
      const url = schoolYear
        ? `/api/salary-schedule/${districtId}/${schoolYear}`
        : `/api/salary-schedule/${districtId}`;

      const response = await fetch(url);
      const data = await response.json();
      setSchedule(data[0]); // Use first schedule
      setLoading(false);
    };

    fetchSchedule();
  }, [districtId, schoolYear]);

  if (loading) return <div>Loading...</div>;
  if (!schedule) return <div>No data available</div>;

  return (
    <div>
      <h2>{schedule.district_name} - {schedule.school_year}</h2>
      <p>Period: {schedule.period}</p>

      <table>
        <thead>
          <tr>
            <th>Step</th>
            {Object.entries(schedule.lanes).map(([key, lane]) => (
              <th key={key} title={lane.label}>{key}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {schedule.steps.map((step) => (
            <tr key={step.step}>
              <td>{step.step}</td>
              {Object.keys(schedule.lanes).map((laneKey) => (
                <td key={laneKey}>
                  ${step[laneKey]?.toLocaleString() || 'N/A'}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
```

### Example: Compare Districts

```javascript
function SalaryComparison() {
  const [results, setResults] = useState(null);
  const [params, setParams] = useState({
    education: 'M',
    credits: 30,
    step: 5
  });

  const handleSearch = async () => {
    const query = new URLSearchParams(params).toString();
    const response = await fetch(`/api/salary-compare?${query}&limit=10`);
    const data = await response.json();
    setResults(data);
  };

  return (
    <div>
      <h2>Compare Salaries</h2>

      <div>
        <label>Education:
          <select value={params.education} onChange={(e) => setParams({...params, education: e.target.value})}>
            <option value="B">Bachelor's</option>
            <option value="M">Master's</option>
            <option value="D">Doctorate</option>
          </select>
        </label>

        <label>Credits:
          <select value={params.credits} onChange={(e) => setParams({...params, credits: e.target.value})}>
            <option value="0">0</option>
            <option value="15">15</option>
            <option value="30">30</option>
            <option value="45">45</option>
            <option value="60">60</option>
          </select>
        </label>

        <label>Step:
          <input type="number" min="1" max="14" value={params.step}
            onChange={(e) => setParams({...params, step: e.target.value})} />
        </label>

        <button onClick={handleSearch}>Search</button>
      </div>

      {results && (
        <div>
          <h3>Top 10 Districts</h3>
          <ol>
            {results.results.map((result) => (
              <li key={result.district_id}>
                <strong>{result.district_name}</strong>: ${result.salary.toLocaleString()}
                <small> ({result.district_type})</small>
              </li>
            ))}
          </ol>
        </div>
      )}
    </div>
  );
}
```

## Maintenance

### Update Salary Data

1. Edit `/data/salary_data.json`
2. Run: `cd backend && source venv/bin/activate && python scripts/load_salary_data.py`
3. Data is immediately available via API (no redeployment needed)

### Add New Districts

Just add records to `salary_data.json` with the new district_id and run the load script.

### Monitor Usage

```bash
# View Lambda logs
aws logs tail /aws/lambda/dev-salaries-api --follow

# Check DynamoDB metrics
aws cloudwatch get-metric-statistics \
  --namespace AWS/DynamoDB \
  --metric-name ConsumedReadCapacityUnits \
  --dimensions Name=TableName,Value=dev-teacher-salaries \
  --start-time 2024-01-01T00:00:00Z \
  --end-time 2024-01-02T00:00:00Z \
  --period 3600 \
  --statistics Sum
```

## Cost Tracking

- **DynamoDB Storage**: ~$0.01/month (26MB)
- **DynamoDB Reads**: Free tier covers typical usage
- **Lambda Executions**: Free tier covers typical usage
- **API Gateway**: $1 per million requests

**Expected monthly cost: < $1**

## Troubleshooting

### Lambda can't find tables

Check environment variables:
```bash
aws lambda get-function-configuration --function-name dev-salaries-api \
  --query 'Environment.Variables'
```

### Permission errors

Verify IAM role has DynamoDB permissions:
```bash
aws iam get-role-policy --role-name dev-salary-lambda-role \
  --policy-name dev-salary-lambda-dynamodb
```

### No data returned

Check if data loaded:
```bash
aws dynamodb scan --table-name dev-teacher-salaries --max-items 5
```
