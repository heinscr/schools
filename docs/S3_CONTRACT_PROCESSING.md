# S3 Contract Processing with Hybrid Extraction

Automated salary schedule extraction from teacher contract PDFs using a hybrid approach:
- **pdfplumber** for text-based PDFs (free, fast)
- **Claude API** for image-based PDFs (~$0.03 each, high accuracy)

## Quick Start

### Prerequisites

**1. Install Python dependencies:**
```bash
cd backend
pip install -r requirements.txt
```

**2. Install system dependencies (for pdf2image):**
```bash
# Ubuntu/Debian
sudo apt-get install poppler-utils

# macOS
brew install poppler
```

**3. Set up AWS credentials:**
```bash
aws configure
# Or set AWS_PROFILE environment variable
```

**4. Get Claude API key:**
- Visit: https://console.anthropic.com/
- Create API key
- Export it:
```bash
export ANTHROPIC_API_KEY=sk-ant-...
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

💰 Estimated cost (assuming 75% need Claude API):
   10 files × 75% × $0.03 = $0.23
```

**Process all PDFs:**
```bash
export ANTHROPIC_API_KEY=sk-ant-...
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
    # Use Claude API (accurate, ~$0.03)
```

### 2. Text-Based PDF Processing
- Extracts tables with pdfplumber
- Parses with regex patterns
- Detects salary table pages
- Extracts year from dates/text
- Maps education columns (BA, MA, DOC, etc.)

### 3. Image-Based PDF Processing
- Converts pages to images (200 DPI)
- Sends to Claude API with structured prompt
- Claude returns JSON salary data
- Validates and saves results

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

Based on sample contracts (25% text-based, 75% image-based):

| Districts | Text PDFs (free) | Image PDFs (@$0.03) | Total Cost |
|-----------|------------------|---------------------|------------|
| 10        | 3                | 7                   | $0.21      |
| 50        | 13               | 37                  | $1.11      |
| 100       | 25               | 75                  | $2.25      |
| 356       | 89               | 267                 | **$8.01**  |

## Troubleshooting

### "ModuleNotFoundError: No module named 'pdf2image'"
```bash
pip install pdf2image pillow
```

### "Unable to load pdf2image - poppler not installed"
```bash
# Ubuntu/Debian
sudo apt-get install poppler-utils

# macOS
brew install poppler
```

### "ANTHROPIC_API_KEY not set"
```bash
export ANTHROPIC_API_KEY=sk-ant-your-key-here
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
│  │  pdfplumber +    │       │  pdf2image +     │       │
│  │  regex parsing   │       │  Claude API      │       │
│  │                  │       │                  │       │
│  │  FREE            │       │  ~$0.03 each     │       │
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

- **`backend/services/hybrid_extractor.py`** - Core extraction logic
- **`scripts/process_s3_contracts.py`** - CLI script for S3 processing
- **`backend/requirements.txt`** - Python dependencies

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
   - Adjust patterns or use Claude fallback

## Support

- **pdfplumber docs:** https://github.com/jsvine/pdfplumber
- **Claude API docs:** https://docs.anthropic.com/
- **pdf2image docs:** https://github.com/Belval/pdf2image
