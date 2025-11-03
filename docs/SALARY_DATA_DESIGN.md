# Teacher Salary Data Schema Design

## DynamoDB Table Structure

### Option 1: Normalized (One Item Per Salary Cell) - RECOMMENDED

**Partition Key:** `district_id` (e.g., "millis", "medway")
**Sort Key:** `composite_key` = `{school_year}#{period}#{education}#{credits}#{step}`

Example: `2021-2022#full-year#M#30#5`

#### Item Structure:
```json
{
  "district_id": "medway",
  "composite_key": "2021-2022#full-year#M#30#5",
  "school_year": "2021-2022",
  "period": "full-year",
  "education": "M",
  "credits": 30,
  "step": 5,
  "salary": 68130.14,
  "district_name": "Medway",
  "district_type": "municipal",

  // Denormalized for queries
  "GSI1PK": "SALARY#2021-2022#municipal",
  "GSI1SK": "M#30#5#68130.14",

  // For heatmap queries
  "GSI2PK": "COMPARE#M#30#5",
  "GSI2SK": "68130.14#medway"
}
```

#### Indexes:

**Base Table:**
- PK: `district_id`
- SK: `composite_key`
- Use: Get all salaries for a district (for salary grid display)

**GSI1 (SalaryByTypeIndex):**
- PK: `GSI1PK` = `SALARY#{school_year}#{district_type}`
- SK: `GSI1SK` = `{education}#{credits}#{step}#{salary}`
- Use: Find top-paying districts for a given education/credits/step

**GSI2 (CompareDistrictsIndex):**
- PK: `GSI2PK` = `COMPARE#{education}#{credits}#{step}`
- SK: `GSI2SK` = `{salary}#{district_id}`
- Use: Get all districts for a specific lane/step (for heatmaps)

#### Pros:
✓ Flexible for any query pattern
✓ Easy to update individual salaries
✓ Efficient for analytical queries
✓ Can add new districts/years without schema changes

#### Cons:
✗ More items in DynamoDB (higher storage cost)
✗ Need to aggregate to display full grid

---

### Option 2: Aggregated (One Item Per Schedule)

**Partition Key:** `district_id`
**Sort Key:** `schedule_key` = `{school_year}#{period}`

#### Item Structure:
```json
{
  "district_id": "medway",
  "schedule_key": "2021-2022#days-92-183",
  "school_year": "2021-2022",
  "period": "days-92-183",
  "district_name": "Medway",
  "district_type": "municipal",
  "contract_term": "2021-2024",
  "contract_expiration": "2024-08-31",
  "lanes": {
    "B": {"label": "Bachelor's", "credits": 0},
    "B+15": {"label": "Bachelor's + 15", "credits": 15},
    "B+30": {"label": "Bachelor's + 30", "credits": 30},
    "M": {"label": "Master's", "credits": 0},
    "M+15": {"label": "Master's + 15", "credits": 15},
    "M+30": {"label": "Master's + 30", "credits": 30},
    "M+45": {"label": "Master's + 45", "credits": 45},
    "M+60": {"label": "Master's + 60", "credits": 60}
  },
  "steps": [
    {
      "step": 1,
      "B": 49875.50,
      "B+15": 51961.21,
      "B+30": 53529.04,
      "M": 54568.09,
      "M+15": 56135.91,
      "M+30": 57173.87,
      "M+45": 58742.78,
      "M+60": 60314.96
    },
    {
      "step": 2,
      "B": 52478.02,
      "B+15": 54568.09,
      "B+30": 56135.91,
      "M": 56658.16,
      "M+15": 58227.07,
      "M+30": 59791.63,
      "M+45": 61352.92,
      "M+60": 62915.31
    }
    // ... more steps
  ],
  "notes": "Additional compensation notes",

  // For queries - denormalize key salary points
  "GSI1PK": "SALARY#2021-2022#municipal",
  "GSI1SK": "medway",
  "max_salary": 97111.87,
  "min_salary": 49875.50,
  "M30_step5": 68130.14  // Denormalize common query points
}
```

#### Pros:
✓ Very efficient for displaying salary grids
✓ Fewer items (lower cost)
✓ All schedule data in one query
✓ Easy to add metadata (contract terms, notes)

#### Cons:
✗ Hard to query across districts for specific education/credits/step
✗ Need to denormalize common query points
✗ 400KB item size limit (unlikely but possible)

---

## Recommendation: Hybrid Approach

Use **Option 1 (Normalized)** for the main data, but also store **Option 2 (Aggregated)** as a cached view.

### Main Table (Normalized):
```
Table: teacher-salaries
PK: district_id
SK: {year}#{period}#{education}#{credits}#{step}
```

### Cache Table (Aggregated):
```
Table: teacher-salary-schedules
PK: district_id
SK: {year}#{period}
```

### Why Both?

1. **For UI Display (salary grid):** Query the cache table → Fast, single-item fetch
2. **For Analytics (comparisons, heatmaps):** Query the main table with GSI → Flexible queries
3. **Updates:** Write to main table, regenerate cache table items as needed

---

## Query Patterns

### 1. Display salary grid for a district
```javascript
// Query cache table
const params = {
  TableName: 'teacher-salary-schedules',
  KeyConditionExpression: 'district_id = :did',
  ExpressionAttributeValues: {
    ':did': 'medway'
  }
};
```

### 2. Find top 10 paying districts for M+30, Step 5
```javascript
// Query main table with GSI2
const params = {
  TableName: 'teacher-salaries',
  IndexName: 'CompareDistrictsIndex',
  KeyConditionExpression: 'GSI2PK = :pk',
  ExpressionAttributeValues: {
    ':pk': 'COMPARE#M#30#5'
  },
  ScanIndexForward: false,  // Descending by salary
  Limit: 10
};
```

### 3. Get all salaries for heatmap (all districts, specific lane/step)
```javascript
// Query main table with GSI2
const params = {
  TableName: 'teacher-salaries',
  IndexName: 'CompareDistrictsIndex',
  KeyConditionExpression: 'GSI2PK = :pk',
  ExpressionAttributeValues: {
    ':pk': 'COMPARE#M#30#5'
  }
};
```

### 4. Get salary schedules by district type
```javascript
// Query cache table with a new GSI
const params = {
  TableName: 'teacher-salary-schedules',
  IndexName: 'ByDistrictTypeIndex',
  KeyConditionExpression: 'district_type = :type AND begins_with(schedule_key, :year)',
  ExpressionAttributeValues: {
    ':type': 'regional_academic',
    ':year': '2021-2022'
  }
};
```

---

## Data Loading Strategy

### Phase 1: Extract from PDFs (AWS Bedrock)
- Use Claude to extract salary tables → JSON
- Save raw JSON files per district

### Phase 2: Normalize and Load
- Parse JSON into normalized rows
- Calculate composite keys
- Batch write to DynamoDB main table

### Phase 3: Generate Cache
- Aggregate normalized data by district + year + period
- Write to cache table

### Phase 4: Update Districts Table
- Add reference to latest salary schedule
- Add salary range metadata

```json
{
  "PK": "DISTRICT#medway",
  "SK": "METADATA",
  // ... existing district data
  "salary_data": {
    "available_years": ["2021-2022", "2022-2023"],
    "latest_year": "2021-2022",
    "salary_range": {
      "min": 49875.50,
      "max": 97111.87
    }
  }
}
```

---

## Frontend Components

### 1. SalaryGrid Component
```jsx
<SalaryGrid
  district="medway"
  schoolYear="2021-2022"
  period="full-year"
/>
```
- Fetches from cache table
- Displays steps × lanes grid
- Highlights selected cell
- Shows lane definitions

### 2. SalaryComparison Component
```jsx
<SalaryComparison
  education="M"
  credits={30}
  step={5}
  districtType="regional_academic"
  limit={10}
/>
```
- Queries main table GSI1
- Shows ranked list
- Click to see full schedule

### 3. SalaryHeatmap Component
```jsx
<SalaryHeatmap
  education="M"
  credits={30}
  step={5}
  mapType="choropleth"  // or "bubble"
/>
```
- Queries main table GSI2
- Creates geographic heatmap
- Color-coded by salary ranges

---

## API Routes

### GET /api/salary-schedule/:districtId/:year?
Returns aggregated salary schedule (cache table)

### GET /api/salary-compare
Query params: `education`, `credits`, `step`, `districtType`, `limit`
Returns ranked list of districts (main table GSI1)

### GET /api/salary-heatmap
Query params: `education`, `credits`, `step`
Returns all districts with salaries (main table GSI2)

### GET /api/districts/:id/salary-metadata
Returns available years, salary ranges (from districts table)

---

## Cost Estimation

### Storage:
- **Main table:** ~200 items/district × 85 districts × 1KB = ~17MB
- **Cache table:** ~2 items/district × 85 districts × 50KB = ~8.5MB
- **Total:** ~26MB → **$0.0065/month**

### Queries:
- **Grid display:** 1 query, 1 item = 0.5 RCU
- **Comparison:** 1 query, 10 items = 2.5 RCU
- **Heatmap:** 1 query, 85 items = 21 RCU

With 1000 users/month doing 10 queries each:
- 10,000 queries × 5 RCU avg = 50,000 RCU
- First 25 million RCU free → **$0/month**

**Total estimated cost: $0.0065/month**

---

## Next Steps

1. ✅ Review this design
2. Create DynamoDB tables with GSI definitions
3. Extract salary data from PDFs (AWS Bedrock script)
4. Build data loading pipeline
5. Create API routes
6. Build frontend components
