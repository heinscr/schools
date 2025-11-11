"""
Hybrid PDF Contract Extraction with S3 Integration
Uses pdfplumber for text-based PDFs, AWS Textract for image-based PDFs
"""
import io
import json
import logging
import re
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from decimal import Decimal

import boto3
import pdfplumber

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class HybridContractExtractor:
    """
    Hybrid extraction: pdfplumber for text PDFs, AWS Textract for image PDFs
    """

    def __init__(self):
        """Initialize extractor with AWS clients"""
        self.s3 = boto3.client('s3')
        self.textract = boto3.client('textract')

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
        """
        Extract year from text using multiple strategies

        Returns school year in "YYYY-YYYY" format

        Examples:
            "2024-2025" → "2024-2025" (keep as is)
            "2023" → "2023-2024" (convert to range)
            "Effective July 1, 2027" → "2027-2028" (convert to range)
            "July 2024" → "2024-2025" (convert to range)
            "27" → "2027-2028" (expand and convert to range)
        """
        import re

        if not text:
            return "unknown"

        # Strategy 1: Look for YYYY-YYYY pattern (e.g., "2024-2025")
        # Keep as is
        match = re.search(r'(\d{4})\s*[-–—]\s*(\d{4})', text)
        if match:
            year1 = match.group(1)
            year2 = match.group(2)
            return f"{year1}-{year2}"

        # Strategy 2: Look for "Effective [Month] [Day,] YYYY" pattern
        # Matches: "Effective July 1, 2027" → "2027-2028"
        match = re.search(
            r'Effective\s+(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s+(\d{4})',
            text, re.IGNORECASE
        )
        if match:
            year = int(match.group(1))
            return f"{year}-{year + 1}"

        # Strategy 3: Look for month name followed by year
        # Matches: "July 2024" → "2024-2025"
        match = re.search(
            r'(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{4})',
            text, re.IGNORECASE
        )
        if match:
            year = int(match.group(1))
            return f"{year}-{year + 1}"

        # Strategy 4: Look for any standalone 4-digit year (2000-2099)
        # Matches: "2023" → "2023-2024"
        years = re.findall(r'\b(20\d{2})\b', text)
        if years:
            # Take the most recent year found
            year = int(max(years))
            return f"{year}-{year + 1}"

        # Strategy 5: Look for 2-digit year (e.g., "27" → "2027-2028")
        match = re.search(r'\b(\d{2})\b', text)
        if match:
            year_2digit = int(match.group(1))
            # Assume 20xx for years 00-99
            year = 2000 + year_2digit
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

    def extract_with_pdfplumber(self, pdf_bytes: bytes, filename: str, district_name: str) -> Optional[List[Dict]]:
        """
        Extract salary data using pdfplumber + regex

        Args:
            pdf_bytes: PDF file content
            filename: Original filename
            district_name: District name to use in records

        Returns:
            List of salary records or None if extraction fails
        """
        try:
            logger.info(f"Extracting with pdfplumber: {filename}")

            # Use provided district name
            district = district_name

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

    def extract_with_textract(self, pdf_bytes: bytes, filename: str, district_name: str, s3_bucket: str, s3_key: str) -> Optional[List[Dict]]:
        """
        Extract salary data using AWS Textract

        Args:
            pdf_bytes: PDF file content
            filename: Original filename
            district_name: District name to use in records
            s3_bucket: S3 bucket where PDF is stored
            s3_key: S3 key of the PDF

        Returns:
            List of salary records or None if extraction fails
        """
        try:
            logger.info(f"Extracting with AWS Textract: {filename}")

            # Use provided district name
            district = district_name

            # Start Textract job for table extraction
            response = self.textract.start_document_analysis(
                DocumentLocation={
                    'S3Object': {
                        'Bucket': s3_bucket,
                        'Name': s3_key
                    }
                },
                FeatureTypes=['TABLES']
            )

            job_id = response['JobId']
            logger.info(f"Started Textract job: {job_id}")

            # Wait for job completion
            while True:
                result = self.textract.get_document_analysis(JobId=job_id)
                status = result['JobStatus']

                if status == 'SUCCEEDED':
                    break
                elif status == 'FAILED':
                    logger.error(f"Textract job failed: {result.get('StatusMessage')}")
                    return None

                logger.info(f"Textract job status: {status}, waiting...")
                time.sleep(2)

            # Extract all pages
            blocks = result['Blocks']

            # Get additional pages if multipage
            next_token = result.get('NextToken')
            while next_token:
                result = self.textract.get_document_analysis(
                    JobId=job_id,
                    NextToken=next_token
                )
                blocks.extend(result['Blocks'])
                next_token = result.get('NextToken')

            logger.info(f"Retrieved {len(blocks)} blocks from Textract")

            # Extract text for year detection
            full_text = ' '.join([
                block.get('Text', '') for block in blocks
                if block['BlockType'] == 'LINE'
            ])

            # Parse tables from Textract response
            all_records = []
            tables = self._parse_textract_tables(blocks)

            logger.info(f"Found {len(tables)} tables in Textract response")

            for table_data in tables:
                year = self.extract_year_from_text(full_text)
                records = self.parse_salary_table(table_data, district, year)
                all_records.extend(records)

            return all_records if all_records else None

        except Exception as e:
            logger.error(f"Textract extraction failed: {e}", exc_info=True)
            return None

    def _parse_textract_tables(self, blocks: List[Dict]) -> List[List[List[str]]]:
        """
        Parse tables from Textract blocks

        Args:
            blocks: Textract response blocks

        Returns:
            List of tables (each table is a 2D array of strings)
        """
        # Build block map
        block_map = {block['Id']: block for block in blocks}

        # Find all table blocks
        table_blocks = [block for block in blocks if block['BlockType'] == 'TABLE']

        tables = []

        for table_block in table_blocks:
            # Skip small tables (likely not salary tables)
            row_count = sum(1 for rel in table_block.get('Relationships', [{}])[0].get('Ids', [])
                          if block_map.get(rel, {}).get('BlockType') == 'CELL')
            if row_count < 10:  # Need at least header + several data rows
                continue

            # Extract cells
            cells = {}
            if 'Relationships' in table_block:
                for relationship in table_block['Relationships']:
                    if relationship['Type'] == 'CHILD':
                        for cell_id in relationship['Ids']:
                            cell_block = block_map.get(cell_id)
                            if cell_block and cell_block['BlockType'] == 'CELL':
                                row_index = cell_block.get('RowIndex', 0)
                                col_index = cell_block.get('ColumnIndex', 0)

                                # Get cell text
                                cell_text = self._get_cell_text(cell_block, block_map)
                                cells[(row_index, col_index)] = cell_text

            # Convert to 2D array
            if cells:
                max_row = max(row for row, col in cells.keys())
                max_col = max(col for row, col in cells.keys())

                table_data = []
                for row in range(1, max_row + 1):
                    row_data = []
                    for col in range(1, max_col + 1):
                        cell_text = cells.get((row, col), '')
                        row_data.append(cell_text)
                    table_data.append(row_data)

                # Check if this looks like a salary table
                if self._is_salary_table(table_data):
                    tables.append(table_data)

        return tables

    def _get_cell_text(self, cell_block: Dict, block_map: Dict) -> str:
        """Extract text from a Textract cell block"""
        text = ''
        if 'Relationships' in cell_block:
            for relationship in cell_block['Relationships']:
                if relationship['Type'] == 'CHILD':
                    for word_id in relationship['Ids']:
                        word_block = block_map.get(word_id)
                        if word_block and word_block['BlockType'] == 'WORD':
                            text += word_block.get('Text', '') + ' '
        return text.strip()

    def _is_salary_table(self, table: List[List[str]]) -> bool:
        """Check if a table looks like a salary schedule"""
        if not table or len(table) < 2:
            return False

        # Check header for education columns
        header_text = ' '.join(table[0]).upper()
        has_edu_cols = any(kw in header_text for kw in ['BA', 'MA', 'DOC', 'STEP'])

        # Check first column for step numbers
        first_col = ' '.join([row[0] for row in table[:5] if row]).upper()
        has_steps = 'STEP' in first_col or any(str(i) in first_col for i in range(1, 6))

        return has_edu_cols and has_steps

    def filter_records_by_year_and_period(self, records: List[Dict]) -> List[Dict]:
        """
        Filter records to include only relevant years and periods.

        Rules:
        1. Only include past years if there are no current or future years
        2. If including past year, only include one year (most recent)
        3. Include all current and future years
        4. For each year, only include the period that sorts last alphabetically

        Args:
            records: List of salary records

        Returns:
            Filtered list of salary records
        """
        if not records:
            return records

        from datetime import datetime

        # Determine current school year
        # School year spans July-June, so if we're in July-Dec, it's year to year+1
        # If we're in Jan-June, it's year-1 to year
        today = datetime.now()
        if today.month >= 7:  # July or later
            current_year_start = today.year
        else:  # January-June
            current_year_start = today.year - 1
        current_school_year = f"{current_year_start}-{current_year_start + 1}"

        logger.info(f"Current school year: {current_school_year}")

        # Group records by year
        years_data = {}
        for record in records:
            year = record.get('school_year', 'unknown')
            if year not in years_data:
                years_data[year] = []
            years_data[year].append(record)

        # Categorize years as past, current, or future
        past_years = []
        current_future_years = []

        for year in years_data.keys():
            if year == 'unknown':
                continue

            # Parse year (format: "YYYY-YYYY")
            try:
                year_start = int(year.split('-')[0])
                if year_start < current_year_start:
                    past_years.append(year)
                else:
                    current_future_years.append(year)
            except:
                logger.warning(f"Could not parse year: {year}")
                continue

        # Determine which years to include
        if current_future_years:
            # Have current or future years - use only those
            years_to_include = sorted(current_future_years)
            logger.info(f"Including current/future years: {years_to_include}")
        elif past_years:
            # Only have past years - use most recent one
            most_recent_past = max(past_years)
            years_to_include = [most_recent_past]
            logger.info(f"Including most recent past year: {years_to_include}")
        else:
            # No valid years found
            logger.warning("No valid years found in records")
            return records

        # For each year to include, filter to only the period that sorts last
        filtered_records = []
        for year in years_to_include:
            year_records = years_data[year]

            # Group by period
            periods = {}
            for record in year_records:
                period = record.get('period', 'full-year')
                if period not in periods:
                    periods[period] = []
                periods[period].append(record)

            # Select period that sorts last alphabetically
            selected_period = max(periods.keys())
            logger.info(f"Year {year}: selected period '{selected_period}' from {list(periods.keys())}")

            # Add all records for this year+period
            filtered_records.extend(periods[selected_period])

        logger.info(f"Filtered from {len(records)} to {len(filtered_records)} records")
        return filtered_records

    def extract_from_pdf(self, pdf_bytes: bytes, filename: str, district_name: str, s3_bucket: str, s3_key: str) -> Tuple[List[Dict], str]:
        """
        Extract salary data using hybrid approach

        Args:
            pdf_bytes: PDF file content
            filename: Original filename
            district_name: District name to use in records
            s3_bucket: S3 bucket where PDF is stored
            s3_key: S3 key of the PDF

        Returns:
            Tuple of (records, method_used)
        """
        # Try pdfplumber first for text-based PDFs
        if self.is_text_based_pdf(pdf_bytes):
            logger.info(f"✓ Text-based PDF detected: {filename}")
            records = self.extract_with_pdfplumber(pdf_bytes, filename, district_name)
            if records:
                # Filter records by year and period
                records = self.filter_records_by_year_and_period(records)
                return records, "pdfplumber"
            else:
                logger.warning("pdfplumber extraction failed, falling back to Textract")

        # Fall back to Textract for image-based PDFs
        logger.info(f"⚠ Image-based PDF detected: {filename}")
        records = self.extract_with_textract(pdf_bytes, filename, district_name, s3_bucket, s3_key)
        if records:
            # Filter records by year and period
            records = self.filter_records_by_year_and_period(records)
            return records, "textract"

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
            'textract_count': 0,
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
                records, method = self.extract_from_pdf(pdf_bytes, filename, input_bucket, pdf_key)

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
                    elif method == 'textract':
                        results['textract_count'] += 1

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
        logger.info(f"AWS Textract:     {results['textract_count']}")
        logger.info(f"{'='*60}")

        return results
