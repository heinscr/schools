# S3 Contract Processing with AWS Textract

Automated salary schedule extraction from teacher contract PDFs using a hybrid approach:
- **pdfplumber** for text-based PDFs (free, fast)
- **AWS Textract** for image-based PDFs ($15 per 1,000 pages, accurate)

## Quick Start

### Prerequisites

**1. Install Python dependencies:**
```bash
cd backend
pip install -r requirements.txt
```

**2. Set up AWS credentials:**
```bash
aws configure
# Or set AWS_PROFILE environment variable
```

**3. Ensure IAM permissions:**

Your AWS user/role needs these permissions:
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "s3:GetObject",
        "s3:PutObject",
        "s3:ListBucket"
      ],
      "Resource": [
        "arn:aws:s3:::crackpow-schools-918213481336/*",
        "arn:aws:s3:::crackpow-schools-918213481336"
      ]
    },
    {
      "Effect": "Allow",
      "Action": [
        "textract:StartDocumentAnalysis",
        "textract:GetDocumentAnalysis"
      ],
      "Resource": "*"
    }
  ]
}
```

### Usage

**Dry run (list files without processing):**
```bash
cd scripts
python3 process_s3_contracts.py --dry-run
```

Output:
```
Found 10 PDF files:
  1. Bedford_contract_1_conf85.pdf
  2. Agawam_contract_2_conf85.pdf
  ...

💰 Estimated cost (assuming 75% need Textract, avg 3 pages/PDF):
   8 PDFs × 3 pages × $15/1000 pages = $0.36
```

**Process all PDFs:**
```bash
python3 process_s3_contracts.py
```

**Custom buckets/prefixes:**
```bash
python3 process_s3_contracts.py \
  --input-bucket my-bucket \
  --input-prefix contracts/pdfs/ \
  --output-bucket my-bucket \
  --output-prefix contracts/data/
```

## How It Works

### 1. PDF Detection
```python
if is_text_based_pdf(pdf):
    # Use pdfplumber (free, fast)
else:
    # Use AWS Textract ($15/1000 pages)
```

### 2. Text-Based PDF Processing
- Extracts tables with pdfplumber
- Parses with regex patterns
- Detects salary table pages
- Extracts year from dates/text
- Maps education columns (BA, MA, DOC, etc.)

### 3. Image-Based PDF Processing (AWS Textract)
- Uploads PDF location to Textract
- Starts asynchronous document analysis job
- Polls for completion (2-5 seconds typical)
- Retrieves table structures from Textract
- Parses cells into salary records
- Validates table structure

### 4. Output Format

**S3 location:** `s3://crackpow-schools-918213481336/contracts/data/Bedford_contract_1.json`

**JSON structure:**
```json
{
  "metadata": {
    "source_file": "Bedford_contract_1_conf85.pdf",
    "extraction_method": "pdfplumber",
    "total_records": 234
  },
  "records": [
    {
      "district_id": "bedford",
      "district_name": "Bedford",
      "school_year": "2022-2023",
      "period": "full-year",
      "education": "B",
      "credits": 0,
      "step": 2,
      "salary": 47796.0
    },
    ...
  ]
}
```

## Cost Estimates

Based on sample contracts (25% text-based, 75% image-based, avg 3 pages/PDF):

| Districts | Text PDFs (free) | Image PDFs | Total Pages | Cost @ $15/1000 |
|-----------|------------------|------------|-------------|-----------------|
| 10        | 3                | 7          | 21          | **$0.32**       |
| 50        | 13               | 37         | 111         | **$1.67**       |
| 100       | 25               | 75         | 225         | **$3.38**       |
| 356       | 89               | 267        | 801         | **$12.02**      |

**AWS Textract Pricing:**
- Table extraction: $15 per 1,000 pages
- No minimum charge
- Pay only for what you use

## Textract vs Claude API Comparison

| Feature | AWS Textract | Claude API (previous) |
|---------|--------------|----------------------|
| **Cost** | $15/1000 pages | $3-15 per 1M tokens (~$0.03/page) |
| **Setup** | AWS credentials only | External API key needed |
| **Integration** | Native AWS | External service |
| **Table Detection** | Excellent | Excellent |
| **Speed** | 2-5 seconds/page | 3-10 seconds/page |
| **Accuracy** | Very Good | Excellent |
| **Best For** | AWS-native apps | Maximum accuracy |

**For 356 districts:**
- Textract: **$12.02** ✅ (chosen)
- Claude API: **$8.01**

Textract chosen for:
- ✅ Native AWS integration
- ✅ No external dependencies
- ✅ Simple IAM permissions
- ✅ Similar cost (~$4 difference)

## Troubleshooting

### "ModuleNotFoundError: No module named 'pdfplumber'"
```bash
pip install pdfplumber
```

### "NoCredentialsError: Unable to locate credentials"
```bash
aws configure
# Enter AWS Access Key ID and Secret Access Key
```

### "Access Denied" to S3 bucket
- Verify IAM permissions for S3 read/write
- Check bucket name is correct
- Ensure AWS profile has proper permissions

### "AccessDeniedException" for Textract
Add these permissions to your IAM user/role:
```json
{
  "Effect": "Allow",
  "Action": [
    "textract:StartDocumentAnalysis",
    "textract:GetDocumentAnalysis"
  ],
  "Resource": "*"
}
```

### Textract job timing out
- Textract jobs are asynchronous
- Script polls every 2 seconds
- Typical processing: 2-5 seconds per page
- Large PDFs (50+ pages) may take 1-2 minutes

### "No tables found" for image-based PDF
- Textract detected the PDF but no tables matched salary schedule pattern
- Check PDF quality (scans should be 200+ DPI)
- Tables must have clear borders
- May need manual review

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│  S3 Input: contracts/pdfs/                              │
│  - Bedford_contract_1.pdf                               │
│  - Agawam_contract_2.pdf                                │
│  - ...                                                  │
└─────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────┐
│  Hybrid Extractor (process_s3_contracts.py)             │
│                                                         │
│  1. Download PDF from S3                                │
│  2. Detect: Text-based or Image-based?                  │
│                                                         │
│  ┌──────────────────┐       ┌──────────────────┐       │
│  │  Text-based PDF  │       │ Image-based PDF  │       │
│  │                  │       │                  │       │
│  │  pdfplumber +    │       │  AWS Textract    │       │
│  │  regex parsing   │       │  (async job)     │       │
│  │                  │       │  - Start job     │       │
│  │  FREE            │       │  - Poll status   │       │
│  │                  │       │  - Get tables    │       │
│  │                  │       │                  │       │
│  │                  │       │  $15/1000 pages  │       │
│  └──────────────────┘       └──────────────────┘       │
│                                                         │
│  3. Parse salary data                                   │
│  4. Upload JSON to S3                                   │
└─────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────┐
│  S3 Output: contracts/data/                             │
│  - Bedford_contract_1.json                              │
│  - Agawam_contract_2.json                               │
│  - ...                                                  │
└─────────────────────────────────────────────────────────┘
```

## Files

- **`backend/services/hybrid_extractor.py`** - Core extraction logic with Textract
- **`scripts/process_s3_contracts.py`** - CLI script for S3 processing
- **`backend/requirements.txt`** - Python dependencies

## Example Output

After running:
```
🚀 Contract PDF Processor (AWS Textract)
============================================================
Input:  s3://crackpow-schools-918213481336/contracts/pdfs/
Output: s3://crackpow-schools-918213481336/contracts/data/
============================================================

📄 Processing PDFs...

============================================================
Processing: Bedford_contract_1_conf85.pdf
============================================================
✓ Text-based PDF detected: Bedford_contract_1_conf85.pdf
Extracting with pdfplumber: Bedford_contract_1_conf85.pdf
✓ SUCCESS: 234 records via pdfplumber
✓ Saved to s3://crackpow-schools-918213481336/contracts/data/Bedford_contract_1.json

============================================================
Processing: Agawam_contract_2_conf85.pdf
============================================================
⚠ Image-based PDF detected: Agawam_contract_2_conf85.pdf
Extracting with AWS Textract: Agawam_contract_2_conf85.pdf
Started Textract job: abc123...
Textract job status: IN_PROGRESS, waiting...
Textract job status: SUCCEEDED
Retrieved 1247 blocks from Textract
Found 3 tables in Textract response
✓ SUCCESS: 312 records via textract
✓ Saved to s3://crackpow-schools-918213481336/contracts/data/Agawam_contract_2.json

============================================================
EXTRACTION SUMMARY
============================================================
Total files:      10
Successful:       9
Failed:           1
pdfplumber:       3
AWS Textract:     6
============================================================

DETAILED RESULTS:
  📝 Bedford_contract_1.pdf: 234 records (pdfplumber)
  🔍 Agawam_contract_2.pdf: 312 records (textract)
  🔍 Abington_contract_1.pdf: 156 records (textract)
  ...

💰 COST ESTIMATE:
   Textract calls: 6
   Estimated cost (avg 3 pages): $0.27
```

## Next Steps

After extraction:

1. **Verify Results**
   ```bash
   aws s3 ls s3://crackpow-schools-918213481336/contracts/data/
   aws s3 cp s3://crackpow-schools-918213481336/contracts/data/Bedford_contract_1.json -
   ```

2. **Load to DynamoDB**
   ```bash
   cd backend
   python scripts/load_salary_data.py <path-to-json>
   ```

3. **Review Failed Extractions**
   - Check logs for error messages
   - Manually review PDF structure
   - Re-upload with better quality if needed

## Support

- **pdfplumber docs:** https://github.com/jsvine/pdfplumber
- **AWS Textract docs:** https://docs.aws.amazon.com/textract/
- **AWS Textract pricing:** https://aws.amazon.com/textract/pricing/
