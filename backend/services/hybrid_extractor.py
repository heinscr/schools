"""
Hybrid PDF Contract Extraction with S3 Integration
Uses pdfplumber for text-based PDFs, Claude API for image-based PDFs
"""
import io
import json
import logging
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from decimal import Decimal
import base64

import boto3
import pdfplumber
from pdf2image import convert_from_bytes
from anthropic import Anthropic

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class HybridContractExtractor:
    """
    Hybrid extraction: pdfplumber for text PDFs, Claude for image PDFs
    """

    def __init__(self, anthropic_api_key: Optional[str] = None):
        """
        Initialize extractor

        Args:
            anthropic_api_key: Claude API key (or set ANTHROPIC_API_KEY env var)
        """
        self.s3 = boto3.client('s3')
        self.anthropic = Anthropic(api_key=anthropic_api_key) if anthropic_api_key else Anthropic()

    def is_text_based_pdf(self, pdf_bytes: bytes) -> bool:
        """
        Determine if PDF is text-based or image-based

        Args:
            pdf_bytes: PDF file content

        Returns:
            True if text-based, False if image-based
        """
        try:
            with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
                # Check first few pages
                for page in pdf.pages[:3]:
                    text = page.extract_text() or ""
                    # If we find substantial text, it's text-based
                    if len(text.strip()) > 100:
                        return True
            return False
        except Exception as e:
            logger.error(f"Error checking PDF type: {e}")
            return False

    def extract_year_from_text(self, text: str) -> str:
        """Extract school year from text using multiple strategies"""
        if not text:
            return "unknown"

        # Strategy 1: YYYY-YYYY pattern
        match = re.search(r'(\d{4})\s*[-–—]\s*(\d{4})', text)
        if match:
            return f"{match.group(1)}-{match.group(2)}"

        # Strategy 2: Effective Month Day, YYYY
        match = re.search(
            r'Effective\s+(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s+(\d{4})',
            text, re.IGNORECASE
        )
        if match:
            year = int(match.group(1))
            return f"{year}-{year + 1}"

        # Strategy 3: Month YYYY
        match = re.search(
            r'(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{4})',
            text, re.IGNORECASE
        )
        if match:
            year = int(match.group(1))
            return f"{year}-{year + 1}"

        # Strategy 4: Standalone year
        years = re.findall(r'\b(20\d{2})\b', text)
        if years:
            year = int(max(years))
            return f"{year}-{year + 1}"

        return "unknown"

    def parse_salary_table(self, table: List[List[str]], district: str, year: str) -> List[Dict]:
        """Parse salary table into structured records"""
        if not table or len(table) < 2:
            return []

        # Education column mapping
        edu_map = {
            'BA': ('B', 0), 'B': ('B', 0),
            'BA+15': ('B', 15), 'B+15': ('B', 15),
            'BA+30': ('B', 30), 'B+30': ('B', 30), 'B30/MA': ('M', 0), 'B30': ('M', 0),
            'MA': ('M', 0), 'M': ('M', 0), 'MASTERS': ('M', 0),
            'MA+15': ('M', 15), 'M+15': ('M', 15),
            'MA+30': ('M', 30), 'M+30': ('M', 30),
            'MA+45': ('M', 45), 'M+45': ('M', 45), 'MA+45/CAGS': ('M', 45),
            'CAGS': ('M', 60), 'CAGS/DOC': ('D', 0),
            'DOC': ('D', 0), 'DOCTORATE': ('D', 0),
        }

        records = []

        # Parse header
        header = [str(h).strip().upper().replace(' ', '') for h in table[0]]
        edu_columns = [h for h in header if h and h not in ['', 'STEPS', 'STEP']]

        # Parse data rows
        for row in table[1:]:
            if not row or len(row) < 2:
                continue

            # Extract step number
            step_match = re.search(r'\b(\d+)\b', str(row[0]))
            if not step_match:
                continue
            step = int(step_match.group(1))

            # Extract salaries for each education level
            for col_idx, edu_col in enumerate(edu_columns):
                if col_idx + 1 < len(row):
                    salary_str = str(row[col_idx + 1])
                    salary_cleaned = re.sub(r'[$,\s]', '', salary_str)

                    try:
                        salary = float(Decimal(salary_cleaned))

                        if edu_col in edu_map:
                            education, credits = edu_map[edu_col]

                            records.append({
                                'district_id': district.lower(),
                                'district_name': district,
                                'school_year': year,
                                'period': 'full-year',
                                'education': education,
                                'credits': credits,
                                'step': step,
                                'salary': salary
                            })
                    except:
                        pass

        return records

    def extract_with_pdfplumber(self, pdf_bytes: bytes, filename: str) -> Optional[List[Dict]]:
        """
        Extract salary data using pdfplumber + regex

        Args:
            pdf_bytes: PDF file content
            filename: Original filename

        Returns:
            List of salary records or None if extraction fails
        """
        try:
            logger.info(f"Extracting with pdfplumber: {filename}")

            # Extract district name from filename
            district = Path(filename).stem.split('_')[0].title()

            # Extract tables
            all_records = []
            with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
                for page_num, page in enumerate(pdf.pages, 1):
                    text = page.extract_text() or ""
                    tables = page.extract_tables()

                    # Check if this is a salary table page
                    if re.search(r'(SALARY|COMPENSATION|TEACHERS?)\s+SCHEDULE', text, re.I):
                        year = self.extract_year_from_text(text)

                        for table in tables:
                            if table and len(table) > 1:
                                records = self.parse_salary_table(table, district, year)
                                all_records.extend(records)
                                logger.debug(f"Page {page_num}: extracted {len(records)} records")

            return all_records if all_records else None

        except Exception as e:
            logger.error(f"pdfplumber extraction failed: {e}")
            return None

    def extract_with_claude(self, pdf_bytes: bytes, filename: str) -> Optional[List[Dict]]:
        """
        Extract salary data using Claude API with vision

        Args:
            pdf_bytes: PDF file content
            filename: Original filename

        Returns:
            List of salary records or None if extraction fails
        """
        try:
            logger.info(f"Extracting with Claude API: {filename}")

            # Convert PDF pages to images
            images = convert_from_bytes(pdf_bytes, dpi=200)
            district = Path(filename).stem.split('_')[0].title()

            all_records = []

            for page_num, image in enumerate(images, 1):
                logger.info(f"Processing page {page_num}/{len(images)} with Claude")

                # Convert image to base64
                img_byte_arr = io.BytesIO()
                image.save(img_byte_arr, format='PNG')
                img_base64 = base64.b64encode(img_byte_arr.getvalue()).decode()

                # Call Claude API
                prompt = f"""Extract the teacher salary schedule table from this contract page.

District: {district}

Return a JSON array with this exact format:
[
  {{
    "district_id": "{district.lower()}",
    "district_name": "{district}",
    "school_year": "YYYY-YYYY",
    "period": "full-year",
    "education": "B or M or D",
    "credits": 0 or 15 or 30 or 45 or 60,
    "step": 1-15,
    "salary": numeric value
  }}
]

Rules:
- education: B=Bachelor's, M=Master's, D=Doctorate
- Map BA to B+0, BA+15 to B+15, MA to M+0, MA+15 to M+15, MA+30 to M+30, MA+45/CAGS to M+45 or M+60, DOC to D+0
- Extract the school year from text like "2022-2023" or "Effective July 1, 2022" (convert to "2022-2023")
- Include ALL steps and education levels in the table
- Return ONLY valid JSON, no other text

If no salary table is found on this page, return an empty array: []"""

                response = self.anthropic.messages.create(
                    model="claude-sonnet-4-5",
                    max_tokens=4000,
                    messages=[
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "image",
                                    "source": {
                                        "type": "base64",
                                        "media_type": "image/png",
                                        "data": img_base64
                                    }
                                },
                                {
                                    "type": "text",
                                    "text": prompt
                                }
                            ]
                        }
                    ]
                )

                # Parse JSON response
                response_text = response.content[0].text.strip()

                # Extract JSON from response (sometimes Claude adds markdown)
                json_match = re.search(r'\[.*\]', response_text, re.DOTALL)
                if json_match:
                    records = json.loads(json_match.group(0))
                    all_records.extend(records)
                    logger.info(f"Extracted {len(records)} records from page {page_num}")

            return all_records if all_records else None

        except Exception as e:
            logger.error(f"Claude extraction failed: {e}", exc_info=True)
            return None

    def extract_from_pdf(self, pdf_bytes: bytes, filename: str) -> Tuple[List[Dict], str]:
        """
        Extract salary data using hybrid approach

        Args:
            pdf_bytes: PDF file content
            filename: Original filename

        Returns:
            Tuple of (records, method_used)
        """
        # Try pdfplumber first for text-based PDFs
        if self.is_text_based_pdf(pdf_bytes):
            logger.info(f"✓ Text-based PDF detected: {filename}")
            records = self.extract_with_pdfplumber(pdf_bytes, filename)
            if records:
                return records, "pdfplumber"
            else:
                logger.warning("pdfplumber extraction failed, falling back to Claude")

        # Fall back to Claude for image-based PDFs
        logger.info(f"⚠ Image-based PDF detected: {filename}")
        records = self.extract_with_claude(pdf_bytes, filename)
        if records:
            return records, "claude"

        return [], "failed"

    def process_s3_bucket(
        self,
        input_bucket: str,
        input_prefix: str,
        output_bucket: str,
        output_prefix: str
    ) -> Dict:
        """
        Process all PDFs in an S3 bucket

        Args:
            input_bucket: S3 bucket with PDFs
            input_prefix: Prefix/folder in input bucket
            output_bucket: S3 bucket for JSON output
            output_prefix: Prefix/folder in output bucket

        Returns:
            Summary statistics
        """
        logger.info(f"Processing PDFs from s3://{input_bucket}/{input_prefix}")

        # List PDFs in input bucket
        response = self.s3.list_objects_v2(
            Bucket=input_bucket,
            Prefix=input_prefix
        )

        pdf_files = [
            obj['Key'] for obj in response.get('Contents', [])
            if obj['Key'].lower().endswith('.pdf')
        ]

        logger.info(f"Found {len(pdf_files)} PDF files")

        results = {
            'total_files': len(pdf_files),
            'successful': 0,
            'failed': 0,
            'pdfplumber_count': 0,
            'claude_count': 0,
            'files': []
        }

        for pdf_key in pdf_files:
            filename = Path(pdf_key).name
            logger.info(f"\n{'='*60}")
            logger.info(f"Processing: {filename}")
            logger.info(f"{'='*60}")

            try:
                # Download PDF from S3
                pdf_obj = self.s3.get_object(Bucket=input_bucket, Key=pdf_key)
                pdf_bytes = pdf_obj['Body'].read()

                # Extract data
                records, method = self.extract_from_pdf(pdf_bytes, filename)

                if records:
                    # Upload JSON to output bucket
                    output_key = f"{output_prefix}{Path(filename).stem}.json"

                    json_data = {
                        'metadata': {
                            'source_file': filename,
                            'extraction_method': method,
                            'total_records': len(records)
                        },
                        'records': records
                    }

                    self.s3.put_object(
                        Bucket=output_bucket,
                        Key=output_key,
                        Body=json.dumps(json_data, indent=2),
                        ContentType='application/json'
                    )

                    logger.info(f"✓ SUCCESS: {len(records)} records via {method}")
                    logger.info(f"✓ Saved to s3://{output_bucket}/{output_key}")

                    results['successful'] += 1
                    if method == 'pdfplumber':
                        results['pdfplumber_count'] += 1
                    elif method == 'claude':
                        results['claude_count'] += 1

                    results['files'].append({
                        'filename': filename,
                        'success': True,
                        'method': method,
                        'records': len(records)
                    })
                else:
                    logger.error(f"✗ FAILED: No data extracted")
                    results['failed'] += 1
                    results['files'].append({
                        'filename': filename,
                        'success': False,
                        'error': 'No data extracted'
                    })

            except Exception as e:
                logger.error(f"✗ ERROR: {e}", exc_info=True)
                results['failed'] += 1
                results['files'].append({
                    'filename': filename,
                    'success': False,
                    'error': str(e)
                })

        # Print summary
        logger.info(f"\n{'='*60}")
        logger.info("EXTRACTION SUMMARY")
        logger.info(f"{'='*60}")
        logger.info(f"Total files:      {results['total_files']}")
        logger.info(f"Successful:       {results['successful']}")
        logger.info(f"Failed:           {results['failed']}")
        logger.info(f"pdfplumber:       {results['pdfplumber_count']}")
        logger.info(f"Claude API:       {results['claude_count']}")
        logger.info(f"{'='*60}")

        return results
