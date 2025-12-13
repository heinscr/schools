# Period Value Normalization Script

This script normalizes all period values in the DynamoDB table to the standardized format: `"Full Year"` (with capital F and Y).

## What It Does

The script scans the entire DynamoDB table and updates period values from any variation to `"Full Year"`:

- `"full year"` → `"Full Year"`
- `"full-year"` → `"Full Year"`
- `"FY"` → `"Full Year"`
- `"FULL_YEAR"` → `"Full Year"`
- etc.

It updates three types of items:

1. **Salary Schedule Items** (`DISTRICT#xxx / SCHEDULE#...`)
   - Updates the `period` attribute
   - Updates `SK` (Sort Key) containing `PERIOD#`
   - Updates `GSI1PK` containing `PERIOD#`
   - Updates `GSI2PK` containing `PERIOD#`

2. **Metadata Schedule Items** (`METADATA#SCHEDULES / YEAR#...`)
   - Updates the `period` attribute
   - Updates `SK` containing `PERIOD#`

3. **Availability Metadata Items** (`METADATA#AVAILABILITY / YEAR#...#PERIOD#...`)
   - Updates `SK` containing `PERIOD#`

## Usage

The script can be run in two ways:

### Option 1: Using backend/.env file (Recommended)

Set your DynamoDB configuration in `backend/.env`:

```
DYNAMODB_TABLE_NAME=ma-teachers-contracts-data
AWS_REGION=us-east-1
```

Then run the script:

```bash
# Dry run first (recommended)
python backend/scripts/normalize_period_values.py --dry-run

# Actual update
python backend/scripts/normalize_period_values.py
```

### Option 2: Command line argument

Pass the table name directly:

```bash
# Dry run first (recommended)
python backend/scripts/normalize_period_values.py ma-teachers-contracts-data --dry-run

# Actual update
python backend/scripts/normalize_period_values.py ma-teachers-contracts-data
```

### Dry Run (Always Recommended First)

Always run with `--dry-run` first to see what would be changed without making any modifications. This will show you all the items that would be updated.

### Confirmation

When running without `--dry-run`, you'll be prompted to confirm before any changes are made.

## Important Notes

1. **Immutable Keys**: Since DynamoDB keys (PK, SK, GSI keys) are immutable, the script:
   - Creates a new item with updated keys
   - Deletes the old item
   - This ensures all references are correctly updated

2. **Backup**: Consider backing up your data before running:
   ```bash
   aws dynamodb create-backup \
     --table-name ma-teachers-contracts-data \
     --backup-name before-period-normalization-$(date +%Y%m%d)
   ```

3. **GSI Updates**: Global Secondary Index entries are automatically updated because they're attributes on the items.

4. **Testing**: The script has been designed based on the DynamoDB layout documentation in `/docs/DYNAMODB_LAYOUT.md`.

## Example Output

```
INFO: Starting period normalization...
INFO: Table: ma-teachers-contracts-data
INFO: Region: us-east-1
INFO:   Schedule item: DISTRICT#abc-123 / SCHEDULE#2021-2022#full-year#EDU#M#CR#030#STEP#05
INFO:     Period: 'full-year' -> 'Full Year'
INFO:     Updated SK: SCHEDULE#2021-2022#full-year#EDU#M#CR#030#STEP#05 -> SCHEDULE#2021-2022#Full Year#EDU#M#CR#030#STEP#05
INFO:     Updated GSI1PK
INFO:     Updated GSI2PK
INFO:   Metadata item: METADATA#SCHEDULES / YEAR#2021-2022#PERIOD#full-year
INFO:     Period: 'full-year' -> 'Full Year'
INFO:     Updated SK: YEAR#2021-2022#PERIOD#full-year -> YEAR#2021-2022#PERIOD#Full Year
INFO:
INFO: Scan complete!
INFO: Total items scanned: 1523
INFO: Total items updated: 45
INFO:   - Schedule items: 38
INFO:   - Metadata schedule items: 5
INFO:   - Availability metadata items: 2
```

## Requirements

- Python 3.8+
- boto3
- AWS credentials configured (via environment or ~/.aws/credentials)
- Appropriate DynamoDB permissions (read, write, delete)
