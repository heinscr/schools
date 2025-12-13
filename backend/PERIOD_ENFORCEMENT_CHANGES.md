# Period Value Enforcement - Backend Changes

This document summarizes the backend changes made to enforce the "Full Year" period normalization.

## Overview

All period values are now normalized to `"Full Year"` (with capital F and Y, space separated) throughout the backend to ensure consistency with the frontend and API contracts.

## New Utility Module

### `backend/utils/period_normalizer.py`

A new utility module that provides period normalization functions:

- `normalize_period(period: Optional[str]) -> str`
  - Converts variations like "full-year", "FY", "full year" to "Full Year"
  - Preserves other period types (spring, fall, 10-month, etc.)
  - Returns "Full Year" for None/empty values

- `normalize_period_in_record(record: dict) -> dict`
  - Normalizes the period field in a single salary record

- `normalize_periods_in_records(records: list) -> list`
  - Normalizes period fields in a list of salary records

## Files Modified

### 1. Data Extractors

#### `backend/services/hybrid_extractor.py`
- **Line 340**: Changed `'period': 'full-year'` to `'period': 'Full Year'`
- **Impact**: All extracted salary data now uses the standard format

#### `backend/services/table_extractor.py`
- **Line 361** (docstring): Updated example from `"full-year"` to `"Full Year"`
- **Line 386**: Changed `'period': 'full-year'` to `'period': 'Full Year'`
- **Impact**: All table-extracted salary data uses the standard format

### 2. Service Layer

#### `backend/services/salary_jobs.py`
- **Line 15**: Added import: `from utils.period_normalizer import normalize_period`
- **Line 389**: Changed period assignment to normalize input:
  ```python
  period = normalize_period(record.get('period', 'Full Year'))
  ```
- **Impact**: All salary records loaded into DynamoDB are normalized regardless of input format

### 3. API Routers

#### `backend/routers/salary_admin.py`
- **Line 17**: Added import: `from utils.period_normalizer import normalize_period`
- **Line 612**: Added normalization in `get_districts_without_contracts` endpoint:
  ```python
  # Normalize period to standard format
  period = normalize_period(period)
  ```
- **Lines 248-250**: Added normalization in `manual_apply_salary_schedule` endpoint:
  ```python
  # Normalize period to "Full Year" format
  if 'period' in r:
      r['period'] = normalize_period(r['period'])
  ```
- **Impact**: All API inputs are normalized before database queries

## Data Flow Coverage

### ✅ PDF Upload → Extraction → Database
1. User uploads PDF
2. PDF processor extracts data
3. **Extractors** (hybrid_extractor.py, table_extractor.py) create records with "Full Year"
4. **Service layer** (salary_jobs.py) normalizes any variation before writing to DB

### ✅ Manual Data Entry → Database
1. Admin manually submits salary records via API
2. **Router** (salary_admin.py) normalizes period values in request
3. **Service layer** (salary_jobs.py) applies second layer of normalization
4. Records written to DB with "Full Year"

### ✅ API Queries
1. Frontend or API client sends query with period parameter
2. **Router** (salary_admin.py) normalizes the period value
3. Database queried with normalized period
4. Consistent results regardless of input format

## Backward Compatibility

The normalization functions are **backward compatible**:
- Accept any variation: "full-year", "FY", "full year", "FULL YEAR", etc.
- Convert to standard: "Full Year"
- Preserve non-full-year periods: "spring", "fall", "10-month", etc.

This means:
- Existing data with "full-year" will be found via normalized queries
- New data will be written with "Full Year"
- The migration script handles updating existing data

## Testing Recommendations

After deploying these changes:

1. **Test Extractors**:
   ```bash
   # Test that extractors produce "Full Year"
   python backend/services/test_extractor.py
   ```

2. **Test API Normalization**:
   ```bash
   # Test with various period formats
   curl -X GET "http://api/admin/districts/missing-contracts?year=2025-2026&period=full-year"
   curl -X GET "http://api/admin/districts/missing-contracts?year=2025-2026&period=FY"
   curl -X GET "http://api/admin/districts/missing-contracts?year=2025-2026&period=Full+Year"
   # All should return the same results
   ```

3. **Test Manual Entry**:
   ```bash
   # Submit records with "full-year" - should be normalized to "Full Year"
   curl -X POST "http://api/admin/districts/{id}/salary-schedule/manual-apply" \
     -H "Content-Type: application/json" \
     -d '{"records": [{"school_year": "2024-2025", "period": "full-year", ...}]}'

   # Verify in DynamoDB that period is "Full Year"
   ```

## Migration Path

1. **Deploy backend changes** (this PR)
   - All new data uses "Full Year"
   - All queries work with any period format

2. **Run migration script**:
   ```bash
   # Dry run first
   DYNAMODB_TABLE_NAME=ma-teachers-contracts-data AWS_REGION=us-east-1 \
     python backend/scripts/normalize_period_values.py --dry-run

   # Then actual migration
   DYNAMODB_TABLE_NAME=ma-teachers-contracts-data AWS_REGION=us-east-1 \
     python backend/scripts/normalize_period_values.py
   ```

3. **Verify consistency**:
   ```bash
   # Check all periods in database
   aws dynamodb scan \
     --table-name ma-teachers-contracts-data \
     --filter-expression "attribute_exists(period)" \
     --projection-expression "period" \
     | jq '.Items[].period.S' | sort | uniq -c

   # Should see only "Full Year" (and any other legitimate period types)
   ```

## Summary

These changes create a comprehensive normalization layer that:
- ✅ Normalizes at data extraction time
- ✅ Normalizes at API input time
- ✅ Normalizes at database write time
- ✅ Handles backward compatibility
- ✅ Preserves non-full-year period types
- ✅ Works seamlessly with existing and future data

The system now enforces "Full Year" as the standard while gracefully handling legacy data and various input formats.
