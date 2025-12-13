# Period Value Normalization Summary

## Current State

Based on code analysis, the following period value variations exist in the system:

### In Database (from tests and code):
- `"full-year"` - Used in tests and extractors (lowercase with hyphen)
- `"Full Year"` - Used in API defaults and frontend (Title Case with space)
- `"regular"` - Used in some salary jobs
- `"spring"` - Used in test data (for multi-period schedules)

### Target Standard

The standardized format is: **`"Full Year"`** (with capital F and Y, space separated)

This aligns with:
- Frontend default: `period = 'Full Year'` ([api.js:723](frontend/src/services/api.js#L723))
- API default: `period: str = Query("Full Year", ...)` ([salary_admin.py:592](backend/routers/salary_admin.py#L592))
- Edit modal: `period: 'Full Year'` ([EditSalaryModal.jsx:192](frontend/src/components/EditSalaryModal.jsx#L192))

## What the Script Does

The script ([normalize_period_values.py](backend/scripts/normalize_period_values.py)) will:

1. **Scan the entire DynamoDB table** for items with period attributes
2. **Identify variations** that should be normalized to "Full Year":
   - `"full year"` (lowercase with space)
   - `"full-year"` (lowercase with hyphen)
   - `"FY"` (abbreviation)
   - `"FULL_YEAR"` (uppercase with underscore)
   - Any case variation of "full year"

3. **Update three types of items**:

   a. **Salary Schedule Items** (Example: `DISTRICT#abc-123 / SCHEDULE#2021-2022#full-year#EDU#M#CR#030#STEP#05`)
      - Updates `period` attribute
      - Recreates item with updated `SK` key
      - Updates `GSI1PK` and `GSI2PK` keys

   b. **Metadata Schedule Items** (Example: `METADATA#SCHEDULES / YEAR#2021-2022#PERIOD#full-year`)
      - Updates `period` attribute
      - Recreates item with updated `SK` key

   c. **Availability Metadata Items** (Example: `METADATA#AVAILABILITY / YEAR#2021-2022#PERIOD#full-year`)
      - Recreates item with updated `SK` key

4. **Preserve other period types**: The script only normalizes variations of "full year". Other period types like:
   - `"spring"` - Kept as-is (for spring semester schedules)
   - `"fall"` - Kept as-is (for fall semester schedules)
   - `"10-month"` - Kept as-is (for 10-month schedules)
   - etc.

## Why This Matters

1. **Consistency**: Ensures all queries and comparisons work correctly
2. **User Experience**: Frontend displays expect "Full Year" format
3. **API Contracts**: API defaults and documentation specify "Full Year"
4. **Future-Proofing**: Prevents bugs from case-sensitivity issues

## Expected Impact

Based on the codebase analysis:
- **Test data**: Uses `"full-year"` format (will be updated)
- **Extractors**: Generate `"full-year"` format (code should be updated separately)
- **Database items**: Likely contain both formats (will be normalized)

## Next Steps After Running Script

1. Update code generators to use "Full Year":
   - [table_extractor.py:361](backend/services/table_extractor.py#L361) - change `"full-year"` to `"Full Year"`
   - [table_extractor.py:386](backend/services/table_extractor.py#L386) - change `"full-year"` to `"Full Year"`
   - [hybrid_extractor.py:340](backend/services/hybrid_extractor.py#L340) - change `"full-year"` to `"Full Year"`

2. Update test fixtures:
   - Update test data in [test_salary_service.py](backend/tests/test_salary_service.py) to use `"Full Year"`
   - Update test data in [test_utils_normalization.py](backend/tests/test_utils_normalization.py) to use `"Full Year"`

3. Verify normalization worked:
   ```bash
   # Query DynamoDB to check period values
   aws dynamodb scan \
     --table-name ma-teachers-contracts-data \
     --filter-expression "attribute_exists(period)" \
     --projection-expression "period" \
     | jq '.Items[].period.S' | sort | uniq -c
   ```

## Running the Script

See [NORMALIZE_PERIOD_README.md](./NORMALIZE_PERIOD_README.md) for detailed usage instructions.

Quick start (using backend/.env for configuration):
```bash
# Dry run first
python backend/scripts/normalize_period_values.py --dry-run

# Then run for real
python backend/scripts/normalize_period_values.py
```

Or pass the table name directly:
```bash
# Dry run first
python backend/scripts/normalize_period_values.py ma-teachers-contracts-data --dry-run

# Then run for real
python backend/scripts/normalize_period_values.py ma-teachers-contracts-data
```
