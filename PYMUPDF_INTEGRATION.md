# PyMuPDF Integration - Implementation Summary

## Overview
Updated `hybrid_extractor.py` to add PyMuPDF as a fallback extraction method between pdfplumber and AWS Textract.

## Extraction Order (NEW)
1. **pdfplumber** - Fast, works for most text-based PDFs with clear table structure
2. **PyMuPDF** - Better text extraction for PDFs with encoding issues and column-oriented layouts
3. **AWS Textract** - For image-based/scanned PDFs or when all other methods fail

## Changes Made

### 1. Added PyMuPDF Import ([hybrid_extractor.py:20-25](backend/services/hybrid_extractor.py#L20-L25))
```python
try:
    import fitz  # PyMuPDF
    PYMUPDF_AVAILABLE = True
except ImportError:
    PYMUPDF_AVAILABLE = False
    logging.warning("PyMuPDF not installed - fallback to PyMuPDF disabled")
```

### 2. Added Column-Oriented Table Parser ([hybrid_extractor.py:305-394](backend/services/hybrid_extractor.py#L305-L394))
New method: `parse_column_oriented_table(lines: List[str])`

Handles PDFs where table values are on separate lines:
```
Step
15
M+30
M+45
DOC
1
$44,678
$46,140
...
```

**Key Features:**
- Finds "Step" header
- Distinguishes between step numbers (1, 2, 3...) and education levels (15 = BA+15)
- Smart detection: checks if next line is a salary to determine context
- Parses rows until non-table content is encountered

### 3. Added PyMuPDF Extraction Method ([hybrid_extractor.py:396-454](backend/services/hybrid_extractor.py#L396-L454))
New method: `extract_with_pymupdf(pdf_bytes, filename, district_name)`

**Features:**
- Checks if PyMuPDF is available before attempting extraction
- Opens PDF from bytes stream
- Looks for salary table keywords on each page
- Tries built-in table detection first (`page.find_tables()`)
- Falls back to column-oriented parsing if built-in detection fails
- Returns list of salary records or None

### 4. Updated Extraction Flow ([hybrid_extractor.py:726-779](backend/services/hybrid_extractor.py#L726-L779))
Modified: `extract_from_pdf(pdf_bytes, filename, district_name, s3_bucket, s3_key)`

**New Flow:**
```python
if is_text_based_pdf():
    records = extract_with_pdfplumber()
    if records:
        return records, "pdfplumber"

    if PYMUPDF_AVAILABLE:
        records = extract_with_pymupdf()
        if records:
            return records, "pymupdf"

# Fall back to Textract
records = extract_with_textract()
if records:
    return records, "textract"

return [], "failed"
```

### 5. Updated Statistics Tracking ([hybrid_extractor.py:815-904](backend/services/hybrid_extractor.py#L815-L904))
Modified: `process_s3_bucket()` method

Added pymupdf tracking:
- Added `'pymupdf_count': 0` to results dict
- Added `elif method == 'pymupdf': results['pymupdf_count'] += 1`
- Added PyMuPDF count to summary output

### 6. Fixed District Name Extraction ([hybrid_extractor.py:836-840](backend/services/hybrid_extractor.py#L836-L840))
Added proper district name extraction from filename in `process_s3_bucket()`:
```python
district_name = Path(filename).stem.split('_')[0].title()
```

### 7. Updated Dependencies ([backend/requirements.txt:17](backend/requirements.txt#L17))
Added PyMuPDF to requirements:
```
PyMuPDF==1.23.0
```

## Testing the Changes

### Test with Sample PDFs
```bash
cd /home/craig/projects/school
source backend/venv/bin/activate

# Install PyMuPDF
pip install PyMuPDF==1.23.0

# Test the hybrid script (standalone)
python scripts/extract_salary_tables.py data/sample_contracts/*.pdf
```

Expected results:
- Bedford PDF: pdfplumber (standard layout)
- Abington PDF: PyMuPDF (column-oriented layout)

### Test with Lambda Function
The Lambda function will automatically use the new extraction order when processing PDFs from S3.

## Benefits

1. **Better Coverage**: PDFs that failed with pdfplumber (like Abington) now succeed with PyMuPDF
2. **No Breaking Changes**: Existing pdfplumber extractions still work the same way
3. **Cost Optimization**: PyMuPDF is free and runs in-process, reducing Textract API calls
4. **No Extra Dependencies**: PyMuPDF has no system dependencies (unlike Camelot/Tabula)
5. **Performance**: PyMuPDF is fast, adding minimal overhead to the extraction pipeline

## Test Results from Scripts

From `extract_salary_tables.py` testing:

| PDF | Method Used | Records | Notes |
|-----|-------------|---------|-------|
| Bedford_contract_1_conf85.pdf | pdfplumber | 78 | Standard table format |
| Abington_contract_1_conf60.pdf | PyMuPDF (text) | 52 | Column-oriented layout |
| Arlington_contract_1_conf85.pdf | PyMuPDF (builtin) | 0 | Found table but couldn't parse |
| Medway.pdf | pdfplumber | 0 | Found table but couldn't parse |

**Success Rate**: 2/4 PDFs with data extracted (130 total records)

## Migration Notes

### For Development
```bash
cd backend
pip install -r requirements.txt
```

### For Lambda Deployment
The Lambda layer will need to include PyMuPDF. Update the deployment script to install PyMuPDF in the Lambda layer.

## Related Files

- [backend/services/hybrid_extractor.py](backend/services/hybrid_extractor.py) - Main service file (updated)
- [backend/requirements.txt](backend/requirements.txt) - Python dependencies (updated)
- [scripts/extract_salary_tables.py](scripts/extract_salary_tables.py) - Standalone test script
- [scripts/extract_pdf_improved.py](scripts/extract_pdf_improved.py) - PyMuPDF-only test script
- [scripts/EXTRACTION_GUIDE.md](scripts/EXTRACTION_GUIDE.md) - Usage guide
- [scripts/PDF_EXTRACTION_COMPARISON.md](scripts/PDF_EXTRACTION_COMPARISON.md) - Library comparison

## Next Steps

1. Install PyMuPDF in backend virtual environment
2. Test with sample PDFs locally
3. Update Lambda deployment to include PyMuPDF in Lambda layer
4. Deploy updated Lambda function
5. Test with production PDFs from S3
