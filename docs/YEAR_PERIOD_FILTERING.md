# Year and Period Filtering Logic

The contract extraction system automatically filters salary data to include only the most relevant years and periods.

## Filtering Rules

### 1. Year Selection

**If contract has current or future years:**
- Include **all** current and future years
- Exclude **all** past years

**If contract only has past years:**
- Include only the **most recent** past year
- Exclude all older past years

**Year Format:**
- Years are stored as single values (e.g., "2025" not "2024-2025")
- When extracting "2024-2025", we take the ending/larger year: "2025"
- When extracting "July 1, 2024", we take the year: "2024"

**School Year Definition:**
- School years run July to June
- Current school year determined by:
  - July-December: current_year+1 (ending year)
  - January-June: current_year (ending year)

**Example (current date: November 2025):**
- Current school year ending: **2026** (for 2025-2026)
- Contract has: 2022, 2023, 2024 (extracted from "2021-2022", "2022-2023", "2023-2024")
- All are **past** years
- Result: Include only **2024** (most recent)

### 2. Period Selection

For each included year, only include the period that **sorts last alphabetically**.

**Common periods (sorted):**
1. `10-month` (starts with '1')
2. `full-year` (starts with 'f')
3. `summer` (starts with 's')

**Selection:** `summer` (sorts last)

**Most common case:**
- Contract has only `full-year` period
- Result: Include `full-year`

## Examples

### Example 1: All Past Years

**Input:**
- Current date: November 11, 2025
- Current school year ending: 2026
- Contract years: 2022, 2023, 2024 (from "2021-2022", "2022-2023", "2023-2024")
- Periods: full-year (for all years)
- Total records: 234 (78 per year)

**Output:**
- Selected year: **2024** (most recent past)
- Selected period: **full-year** (only period)
- Total records: **78** (67% reduction)

**Reasoning:**
- All three years are in the past
- Keep only most recent: 2024
- Only one period available: full-year

### Example 2: Mix of Past and Current Years

**Input:**
- Current date: November 11, 2025
- Current school year ending: 2026
- Contract years: 2025, 2026, 2027 (from "2024-2025", "2025-2026", "2026-2027")
- Periods: full-year (for all years)
- Total records: 234 (78 per year)

**Output:**
- Selected years: **2026, 2027** (current + future)
- Selected period: **full-year** (for each year)
- Total records: **156** (33% reduction)

**Reasoning:**
- Have current (2026) and future (2027) years
- Exclude past year (2025)
- Keep both current and future

### Example 3: Multiple Periods

**Input:**
- Current date: November 11, 2025
- Current school year ending: 2026
- Contract years: 2026 (from "2025-2026")
- Periods: 10-month, full-year, summer
- Records per period: 78
- Total records: 234

**Output:**
- Selected year: **2026** (current)
- Selected period: **summer** (sorts last: s > f > 1)
- Total records: **78** (67% reduction)

**Reasoning:**
- Current year 2026 is included
- Three periods available
- ASCII sort: "summer" > "full-year" > "10-month"
- Keep only summer period

### Example 4: Future Years Only

**Input:**
- Current date: January 15, 2025
- Current school year ending: 2025
- Contract years: 2026, 2027, 2028 (from "2025-2026", "2026-2027", "2027-2028")
- Periods: full-year (for all years)
- Total records: 234 (78 per year)

**Output:**
- Selected years: **2026, 2027, 2028** (all future)
- Selected period: **full-year** (for each year)
- Total records: **234** (no reduction)

**Reasoning:**
- All three years are in the future
- Keep all future years
- One period per year: full-year

## Benefits

### 1. **Reduces Data Storage**
- Typical reduction: 67% for 3-year contracts
- Example: 234 records → 78 records
- Saves S3 storage and DynamoDB costs

### 2. **Shows Most Relevant Data**
- Users see current/upcoming salaries
- Past years only shown if no current data
- Prevents confusion from outdated data

### 3. **Handles All Contract Types**
- **Active contracts:** Shows all current/future years
- **Historical contracts:** Shows most recent year
- **Multi-period contracts:** Shows preferred period

### 4. **Consistent Behavior**
- Same logic for text-based (pdfplumber) and image-based (Textract) PDFs
- Applies to both S3 processing and local testing
- Predictable results

## Implementation

### In Production (S3 Processing)

Filtering happens automatically in `hybrid_extractor.py`:

```python
records = self.extract_with_pdfplumber(pdf_bytes, filename)
records = self.filter_records_by_year_and_period(records)  # ← Automatic
```

### In Local Testing

Filtering happens in `test_extraction.py`:

```bash
$ python3 test_extraction.py Bedford_contract_1_conf85.pdf

Current school year ending: 2026
Including most recent past year: ['2024']
Year 2024: selected period 'full-year' from ['full-year']
Filtered from 234 to 78 records
```

### Disable Filtering (if needed)

To get unfiltered data for testing:

```python
# In hybrid_extractor.py, comment out the filter call:
records = self.extract_with_pdfplumber(pdf_bytes, filename)
# records = self.filter_records_by_year_and_period(records)  # Disabled
```

## Logging

The system logs filtering decisions:

```
Current school year ending: 2026
Including most recent past year: ['2024']
Year 2024: selected period 'full-year' from ['full-year']
Filtered from 234 to 78 records
```

This helps you understand:
- What the current school year ending is (e.g., 2026 for 2025-2026 school year)
- Which years were selected (as single values)
- Which period was chosen for each year
- How many records were kept

## Edge Cases

### No Valid Years
If no years can be parsed (all "unknown"):
- **Behavior:** Return all records unfiltered
- **Reason:** Can't determine past/current/future

### Unknown Period
If period is missing or invalid:
- **Default:** Uses "full-year"
- **Reason:** Most common period

### Year Parsing Errors
If year format is invalid (not "YYYY-YYYY"):
- **Behavior:** Skip that year
- **Logging:** Warning logged
- **Reason:** Can't categorize as past/current/future
