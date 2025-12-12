# DynamoDB Layout and Architecture

This document provides a comprehensive overview of the DynamoDB single-table design used in the MA Teachers Contracts application.

## Table Overview

**Table Name:** `ma-teachers-contracts-data`

**Billing Mode:** Pay-per-request (on-demand)

**Features:**
- Point-in-time recovery enabled
- Server-side encryption enabled
- TTL enabled on `ttl` attribute for automatic cleanup of temporary items

## Primary Key Structure

The table uses a composite primary key:
- **PK** (Partition Key): String - Determines data distribution
- **SK** (Sort Key): String - Enables range queries within a partition

## Entity Types and Access Patterns

### 1. District Metadata

Stores core information about school districts.

**Key Structure:**
```
PK: DISTRICT#{districtId}
SK: METADATA
```

**Attributes:**
- `district_id`: UUID
- `name`: District name
- `name_lower`: Lowercase name for case-insensitive search
- `main_address`: District main office address
- `district_url`: District website URL
- `district_type`: One of: `municipal`, `regional_academic`, `regional_vocational`, `county_agricultural`, `charter`
- `contract_pdf`: S3 key for contract PDF (optional)
- `towns`: List of town names
- `created_at`: ISO timestamp
- `updated_at`: ISO timestamp
- `entity_type`: `"district"`

**Access Patterns:**
- Get district by ID: `GetItem` with PK=`DISTRICT#{id}` and SK=`METADATA`
- List all districts: Query GSI_METADATA with SK=`METADATA`
- Update district: `UpdateItem` on PK/SK

---

### 2. District-Town Relationships

Links districts to the towns they serve. Enables town-based district searches.

**Key Structure:**
```
PK: DISTRICT#{districtId}
SK: TOWN#{townName}
```

**GSI_TOWN (Global Secondary Index):**
```
GSI_TOWN_PK: TOWN#{townName}
GSI_TOWN_SK: DISTRICT#{districtName}
```

**Attributes:**
- `district_id`: UUID
- `district_name`: District name
- `town_name`: Town name
- `entity_type`: `"district_town"`

**Access Patterns:**
- Find districts by town: Query GSI_TOWN with GSI_TOWN_PK=`TOWN#{town}`
- Get all towns for a district: Query PK=`DISTRICT#{id}` and SK begins_with `TOWN#`

---

### 3. Salary Schedules

Individual salary entries for specific education/credit/step combinations.

**Key Structure:**
```
PK: DISTRICT#{districtId}
SK: SCHEDULE#{yyyy}#{period}#EDU#{edu}#CR#{credits}#STEP#{step}
```

**Example:**
```
PK: DISTRICT#abc-123
SK: SCHEDULE#2021-2022#FY#EDU#M#CR#030#STEP#05
```

**Attributes:**
- `district_id`: UUID
- `district_name`: District name
- `school_year`: e.g., "2021-2022"
- `period`: e.g., "FY" (Fiscal Year)
- `education`: "B" (Bachelor's), "M" (Master's), or "D" (Doctorate)
- `credits`: Additional credits (padded to 3 digits, e.g., 030)
- `step`: Step number (padded to 2 digits, e.g., 05)
- `salary`: Decimal salary amount
- `is_calculated`: Boolean indicating if this was calculated via fallback
- `is_calculated_from`: Original education/credit combo used for fallback (if calculated)

**GSI Attributes for Salary Comparisons:**

**GSI1 (ExactMatchIndex):**
```
GSI1PK: YEAR#{yyyy}#PERIOD#{period}#EDU#{edu}#CR#{credits}
GSI1SK: STEP#{step}#DISTRICT#{districtId}
```

**GSI2 (FallbackQueryIndex):**
```
GSI2PK: YEAR#{yyyy}#PERIOD#{period}#DISTRICT#{districtId}
GSI2SK: EDU#{edu}#CR#{credits}#STEP#{step}
```

**GSI5 (ComparisonIndex):**
```
GSI_COMP_PK: EDU#{edu}#CR#{credits}#STEP#{step}
GSI_COMP_SK: SALARY#{salary_padded}#YEAR#{yyyy}#DISTRICT#{districtId}
```

**Access Patterns:**
- Get all salaries for a district: Query PK=`DISTRICT#{id}` and SK begins_with `SCHEDULE#`
- Get salaries for specific year: Query PK=`DISTRICT#{id}` and SK begins_with `SCHEDULE#{year}`
- Compare salaries across districts: Query GSI5 (ComparisonIndex) with GSI_COMP_PK
- Query specific year/period for district: Query GSI2 (FallbackQueryIndex)

---

### 4. Salary Metadata

Global metadata about available salary schedules.

#### 4a. Schedule Metadata

Tracks which year/period combinations exist in the system.

**Key Structure:**
```
PK: METADATA#SCHEDULES
SK: YEAR#{yyyy}#PERIOD#{period}
```

**Example:**
```
PK: METADATA#SCHEDULES
SK: YEAR#2021-2022#PERIOD#FY
```

**Attributes:**
- `school_year`: e.g., "2021-2022"
- `period`: e.g., "FY"

**Access Patterns:**
- Get all available schedules: Query PK=`METADATA#SCHEDULES`

#### 4b. Max Values Metadata

Stores global constraints and valid combinations.

**Key Structure:**
```
PK: METADATA#MAXVALUES
SK: GLOBAL
```

**Attributes:**
- `max_step`: Maximum step value (e.g., 15)
- `edu_credit_combos`: Array of valid education+credit combinations (e.g., `["B+0", "M+30", "M+45", "D+0"]`)

**Access Patterns:**
- Get global metadata: `GetItem` with PK=`METADATA#MAXVALUES` and SK=`GLOBAL`
- Used for validation and fallback logic

---

### 5. Job Records

Temporary records for PDF processing jobs (salary schedule uploads).

**Key Structure:**
```
PK: JOB#{jobId}
SK: METADATA
```

**Attributes:**
- `job_id`: UUID
- `district_id`: Associated district
- `status`: `"pending"`, `"processing"`, `"completed"`, `"failed"`
- `created_at`: ISO timestamp
- `updated_at`: ISO timestamp
- `error_message`: Error details (if failed)
- `ttl`: Unix timestamp for automatic deletion (30 days)

**Access Patterns:**
- Get job status: `GetItem` with PK=`JOB#{id}` and SK=`METADATA`
- Update job status: `UpdateItem`
- Automatic cleanup: TTL expires records after 30 days

---

## Global Secondary Indices

### GSI1: ExactMatchIndex

**Purpose:** Cross-district salary comparisons for exact education/credit combinations

**Keys:**
- Hash: `GSI1PK` = `YEAR#{yyyy}#PERIOD#{period}#EDU#{edu}#CR#{credits}`
- Range: `GSI1SK` = `STEP#{step}#DISTRICT#{districtId}`

**Projection:** ALL

**Use Case:** Query all districts offering a specific education/credit/step combination in a given year/period.

---

### GSI2: FallbackQueryIndex

**Purpose:** Retrieve all salary entries for a specific district's schedule (used in fallback logic)

**Keys:**
- Hash: `GSI2PK` = `YEAR#{yyyy}#PERIOD#{period}#DISTRICT#{districtId}`
- Range: `GSI2SK` = `EDU#{edu}#CR#{credits}#STEP#{step}`

**Projection:** ALL

**Use Case:** When an exact match isn't found, query all education/credit combinations for a district to find the best fallback.

---

### GSI3: GSI_TOWN

**Purpose:** Town-based district search

**Keys:**
- Hash: `GSI_TOWN_PK` = `TOWN#{townName}`
- Range: `GSI_TOWN_SK` = `DISTRICT#{districtName}`

**Projection:** ALL

**Use Case:** Find all districts serving a specific town.

---

### GSI4: GSI_METADATA

**Purpose:** Efficient queries for district metadata by name

**Keys:**
- Hash: `SK` = `METADATA`
- Range: `name_lower` = lowercase district name

**Projection:** ALL

**Use Case:**
- List all districts efficiently
- Search districts by name (case-insensitive)

---

### GSI5: ComparisonIndex (Optimization)

**Purpose:** Fast single-query salary comparisons across all districts

**Keys:**
- Hash: `GSI_COMP_PK` = `EDU#{edu}#CR#{credits}#STEP#{step}`
- Range: `GSI_COMP_SK` = `SALARY#{salary_padded}#YEAR#{yyyy}#DISTRICT#{districtId}`

**Projection:** ALL

**Use Case:**
- One query retrieves all districts with a specific education/credit/step combination
- Results naturally sorted by salary (descending) for ranking
- Eliminates need for year/period fan-out queries

**Note:** Salary is zero-padded to 10 digits in the sort key for proper lexicographic ordering.

---

## Data Flow and System Interactions

### District Management Flow

1. **Create District:**
   - Insert district metadata (PK=`DISTRICT#{id}`, SK=`METADATA`)
   - Insert town relationships (PK=`DISTRICT#{id}`, SK=`TOWN#{town}`)

2. **Search Districts:**
   - By name: Scan GSI_METADATA with filter on `name_lower`
   - By town: Query GSI_TOWN with `GSI_TOWN_PK=TOWN#{town}`
   - List all: Query GSI_METADATA with SK=`METADATA`

3. **Update District:**
   - Update metadata item
   - Delete old town items, insert new ones (if towns changed)

4. **Delete District:**
   - Query all items with PK=`DISTRICT#{id}`
   - Delete all matching items (metadata, towns, salary schedules)

---

### Salary Data Flow

1. **Upload PDF Contract:**
   - User uploads PDF via frontend
   - API uploads to S3 (`contracts/{district_id}/{filename}`)
   - Creates job record (PK=`JOB#{jobId}`)
   - Sends SQS message to processing queue

2. **PDF Processing (Lambda: salary_processor):**
   - Triggered by SQS message
   - Downloads PDF from S3
   - Extracts salary data (text-based or Textract for images)
   - Stores extracted data to S3 (`contracts/extracted_data/{job_id}.json`)
   - Updates job status to "completed"
   - Invokes normalizer Lambda

3. **Normalization (Lambda: salary_normalizer):**
   - Processes extracted salary data
   - Applies fallback logic to fill missing education/credit combinations
   - Calculates missing entries based on available data
   - Writes salary schedule items to DynamoDB
   - Updates global metadata (METADATA#SCHEDULES, METADATA#MAXVALUES)

4. **Salary Comparison Query:**
   - Frontend requests salary comparison for education/credit/step
   - API queries ComparisonIndex (GSI5) with `GSI_COMP_PK`
   - Returns ranked list of all districts with that combination
   - Filters to Municipal and Regional Academic districts only
   - Deduplicates by district (keeps oldest year/period)
   - Fetches district metadata (towns, types) via batch operations

5. **Caching:**
   - Salary queries are cached in-memory (Lambda container scope)
   - Cache TTL: 60 seconds (configurable)
   - Cache invalidated when new salary data is uploaded

---

### Backup and Reapply Flow

1. **Backup Salary Data:**
   - Before processing new PDF, current salary data is backed up
   - Backup stored to S3 (`contracts/backups/{district_id}/{timestamp}.json`)

2. **Reapply Backup (Lambda: backup_reapply_worker):**
   - Admin can restore previous salary data
   - Downloads backup JSON from S3
   - Deletes current salary schedule items
   - Writes backed-up items to DynamoDB
   - Invokes normalizer to update global metadata

---

## Performance Optimizations

### 1. Single-Table Design
- Reduces cross-table joins
- Enables efficient queries with GSIs
- Minimizes read/write operations

### 2. Intelligent Indexing
- ComparisonIndex (GSI5) enables single-query cross-district comparisons
- GSI_METADATA enables efficient "list all districts" operations
- GSI_TOWN enables fast town-based searches

### 3. Caching
- In-memory Lambda cache for salary queries (60s TTL)
- Reduces DynamoDB read costs
- Improves response times for repeated queries

### 4. Batch Operations
- District metadata fetched via `batch_get_item` for comparison queries
- Reduces N+1 query problems

### 5. Projection Expressions
- Only fetch needed attributes to reduce data transfer
- Particularly important for salary schedule queries

### 6. DoS Protection
- Maximum fetch limit (1000 items) to prevent resource exhaustion
- Minimum search query length (3 characters) to prevent expensive scans

---

## Cost Estimation

**Storage:** ~$0.25/GB/month
- ~1000 districts × 2KB = ~2MB
- ~50 salary schedules/district × 500 bytes × 1000 districts = ~25MB
- **Total: ~30MB = ~$0.01/month**

**Reads:** ~$0.25 per million reads
- Estimate: 50,000 reads/month
- **Cost: ~$0.01/month**

**Writes:** ~$1.25 per million writes
- Estimate: 1,000 writes/month
- **Cost: ~$0.001/month**

**Total estimated cost: ~$0.30-$2/month** for typical usage

This is significantly cheaper than RDS (~$12+/month) for this use case.

---

## Monitoring and Troubleshooting

### CloudWatch Metrics to Monitor

1. **Read/Write Capacity:**
   - Monitor consumed capacity
   - Alert on throttling events

2. **User Errors:**
   - `UserErrors` metric indicates validation failures
   - Review query patterns if elevated

3. **System Errors:**
   - `SystemErrors` metric indicates DynamoDB issues
   - Check AWS service health dashboard

4. **Table Size:**
   - Monitor storage consumption
   - Verify TTL is cleaning up job records

### Common Issues

**Issue:** Slow district searches by name
- **Cause:** Scan operations on GSI_METADATA
- **Solution:** Use contains filter, require minimum 3-character queries

**Issue:** Salary comparison queries returning unexpected results
- **Cause:** Missing global metadata or stale cache
- **Solution:** Run normalizer Lambda, clear cache

**Issue:** Job records not expiring
- **Cause:** TTL not enabled or incorrect timestamp
- **Solution:** Verify TTL is enabled on `ttl` attribute, check timestamp format (Unix epoch)

**Issue:** District deduplication in comparisons
- **Cause:** Multiple year/period combinations per district
- **Solution:** Fallback logic keeps oldest year/period per district

---

## Schema Evolution Considerations

### Adding New Attributes
- DynamoDB is schema-less; new attributes can be added without migration
- Update code to handle missing attributes (defensive programming)

### Adding New GSIs
- Can be added without downtime
- Initial backfill may take time for large tables
- Plan for eventual consistency during backfill

### Changing Sort Key Patterns
- Requires data migration (write new items, delete old)
- Plan migration strategy: dual-write, backfill, cutover

### Partition Key Hotspots
- Monitor for hot partitions (single district with high traffic)
- Consider adding randomization suffix if needed
- Current design distributes well (district-level partitioning)

---

## Security Considerations

1. **IAM Policies:**
   - Lambda execution roles have minimal required permissions
   - Separate roles for processor, normalizer, and main API
   - S3 access limited to specific prefixes

2. **Encryption:**
   - Server-side encryption enabled at rest
   - In-transit encryption via HTTPS

3. **API Gateway:**
   - Cognito JWT validation for admin endpoints
   - Public endpoints rate-limited

4. **Data Validation:**
   - Input validation on all writes
   - Education levels restricted to B/M/D
   - Credits and steps validated against metadata

---

## Future Enhancements

1. **Composite GSI for Advanced Searches:**
   - Add GSI for searching by district_type + year

2. **DynamoDB Streams:**
   - Enable streams for audit logging
   - Track all changes to salary data

3. **Global Tables:**
   - If multi-region deployment is needed
   - Automatic replication across regions

4. **Point-in-Time Recovery Testing:**
   - Regularly test PITR recovery procedures
   - Document recovery process

5. **Analytics Pipeline:**
   - Export data to S3 via DynamoDB export
   - Run analytics with Athena or QuickSight
