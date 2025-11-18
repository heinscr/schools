"""
Hybrid PDF Contract Extraction with S3 Integration
Extraction order:
1. pdfplumber (fast, works for most PDFs)
2. PyMuPDF (better text extraction, handles column-oriented layouts)
3. AWS Textract (for image-based/scanned PDFs)
"""
import io
import json
import logging
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple
from decimal import Decimal, InvalidOperation

import boto3
import pdfplumber

# Import all utility functions and constants
from .extraction_utils import (
    PYMUPDF_AVAILABLE,
    PYPDFIUM_AVAILABLE,
    fitz,
    pdfium,
    roman_to_int,
    EDU_MAP,
    normalize_lane_key,
    tokenize_lane_labels,
    extract_lane_labels,
    collapse_multiplier_salary_columns,
    normalize_table_data,
    split_table_on_step_columns,
    split_row_tokens,
    looks_like_step_header,
    is_column_step_marker,
    is_column_salary_value,
    looks_like_lane_header_token,
    text_has_salary_signal,
    collect_lane_aliases,
    extract_step_value,
    parse_row_oriented_table,
    parse_column_oriented_tables_from_lines,
    parse_column_oriented_table_from_lines,
)

# Configure logging
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

        # Strategy 1: Look for YYYY-YYYY pattern (e.g., "2024-2025" or "July 1, 2024 - June 30, 2025")
        # Keep as is
        # Look for two 4-digit years with a dash/hyphen between them (may have text before/after)
        match = re.search(r'(20\d{2})\s*,?\s*[-–—]\s*.{0,15}?(20\d{2})', text)
        if match:
            year1 = match.group(1)
            year2 = match.group(2)
            # Only return if they're consecutive school years (year2 = year1 + 1)
            if int(year2) == int(year1) + 1:
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

        # Strategy 4: Look for "FY YYYY" or "FY YY" pattern
        # Matches: "FY26" → "2025-2026", "FY 2026" → "2025-2026"
        match = re.search(r'FY\s*(\d{2,4})', text, re.IGNORECASE)
        if match:
            year_str = match.group(1)
            if len(year_str) == 2:
                # FY26 -> 2025-2026
                year = 2000 + int(year_str)
                return f"{year - 1}-{year}"
            else:
                # FY 2022 -> 2021-2022
                year = int(year_str)
                return f"{year - 1}-{year}"

        # Strategy 5: Look for any standalone 4-digit year (2000-2099)
        # Matches: "2023" → "2023-2024"
        years = re.findall(r'\b(20\d{2})\b', text)
        if years:
            # Take the most recent year found
            year = int(max(years))
            return f"{year}-{year + 1}"

        # Strategy 6: Look for 2-digit year (e.g., "27" → "2027-2028")
        match = re.search(r'\b(\d{2})\b', text)
        if match:
            year_2digit = int(match.group(1))
            # Assume 20xx for years 00-99
            year = 2000 + year_2digit
            return f"{year}-{year + 1}"

        return "unknown"

    @staticmethod
    def is_valid_step_number(step: int) -> bool:
        """
        Check if a step number is valid (not garbage from bad text extraction).
        Valid step numbers are typically 0-35 (some districts go higher but rarely above 35).
        """
        return 0 <= step <= 35

    @staticmethod
    def deduplicate_records(records: List[Dict]) -> List[Dict]:
        """
        Deduplicate salary records based on their DynamoDB primary key.

        The primary key is: (district_id, school_year, period, education, credits, step)

        When duplicates are found (same table extracted via multiple methods),
        keeps the first occurrence.

        Args:
            records: List of salary records

        Returns:
            Deduplicated list of salary records
        """
        if not records:
            return records

        seen_keys = set()
        unique_records = []
        duplicates_removed = 0

        for record in records:
            # Create a key tuple matching DynamoDB primary key
            key = (
                record.get('district_id'),
                record.get('school_year'),
                record.get('period'),
                record.get('education'),
                record.get('credits'),
                record.get('step'),
            )

            if key not in seen_keys:
                seen_keys.add(key)
                unique_records.append(record)
            else:
                duplicates_removed += 1

        if duplicates_removed > 0:
            logger.debug(
                "Removed %d duplicate records (original: %d, unique: %d)",
                duplicates_removed,
                len(records),
                len(unique_records)
            )

        return unique_records

    def parse_salary_table(
        self,
        table: Sequence[Sequence[Any]],
        district: str,
        year: str,
        alias_map: Optional[Dict[str, str]] = None,
    ) -> List[Dict]:
        """
        Parse salary table into structured records with alias-aware lane mapping.
        Enhanced with step number validation and better education column detection.
        """
        if not table:
            return []

        normalized_table = normalize_table_data(table)
        if not normalized_table:
            return []

        alias_map = alias_map or {}
        records: List[Dict] = []
        invalid_steps = 0

        for sub_table in split_table_on_step_columns(normalized_table):
            if len(sub_table) < 2:
                continue

            header_row_idx = 0
            for idx, row in enumerate(sub_table):
                if row and str(row[0]).strip().upper() == 'STEP':
                    header_row_idx = idx
                    break

            if header_row_idx > 0:
                logger.debug("Skipping %d non-header row(s) at top of table", header_row_idx)

            raw_header = sub_table[header_row_idx]
            normalized_header = [normalize_lane_key(h) for h in raw_header]

            edu_columns: List[Tuple[int, str, Tuple[str, int]]] = []
            for col_idx, (raw_cell, normalized_cell) in enumerate(zip(raw_header, normalized_header)):
                if col_idx == 0:
                    continue

                display_label = str(raw_cell).strip() or normalized_cell
                normalized_label = normalize_lane_key(display_label)

                if normalized_cell in EDU_MAP:
                    edu_columns.append((col_idx, display_label, EDU_MAP[normalized_cell]))
                    continue

                mapped_key = alias_map.get(normalized_label) or alias_map.get(normalized_cell)
                if mapped_key and mapped_key in EDU_MAP:
                    edu_columns.append((col_idx, display_label, EDU_MAP[mapped_key]))
                else:
                    # Skip warning for known metadata columns
                    if normalized_cell.upper() not in ['MULTIPLIER', 'SALARY', 'EMPTY', 'NONE', '']:
                        logger.warning(
                            "Unknown education level '%s' (normalized: '%s') in column %s",
                            display_label,
                            normalized_cell,
                            col_idx,
                        )

            if not edu_columns:
                logger.debug("No valid education columns found in table")
                continue

            logger.debug(
                "Mapped %d columns: %s",
                len(edu_columns),
                [(header, edu, cr) for _, header, (edu, cr) in edu_columns],
            )

            for row_idx, row in enumerate(sub_table[header_row_idx + 1:], header_row_idx + 2):
                if not row or len(row) < 2:
                    continue

                step_str = str(row[0]).strip()
                step_match = re.search(r'(\d+)', step_str)
                if not step_match:
                    continue
                step = int(step_match.group(1))

                # Validate step number to filter garbage from bad text extraction
                if not self.is_valid_step_number(step):
                    invalid_steps += 1
                    continue

                for col_idx, _, (education, credits) in edu_columns:
                    if col_idx >= len(row):
                        continue

                    salary_str = str(row[col_idx]).strip()
                    if not salary_str:
                        continue

                    salary_cleaned = re.sub(r'[$,\s]', '', salary_str).replace('.', '')
                    try:
                        salary = float(Decimal(salary_cleaned))
                    except (ValueError, InvalidOperation):
                        logger.debug(
                            "Could not parse salary '%s' at row %s, col %s",
                            salary_str,
                            row_idx,
                            col_idx,
                        )
                        continue

                    # Validate salary range
                    if not (20000 <= salary <= 200000):
                        logger.debug("Salary %s out of valid range at row %s, col %s", salary, row_idx, col_idx)
                        continue

                    records.append({
                        'district_id': district.lower().replace(' ', '-'),
                        'district_name': district,
                        'school_year': year,
                        'period': 'full-year',
                        'education': education,
                        'credits': credits,
                        'step': step,
                        'salary': salary,
                    })

            if invalid_steps > 0:
                logger.debug("Filtered out %d rows with invalid step numbers (> 35)", invalid_steps)

        return records

    def is_salary_table(self, table: Sequence[Sequence[Any]]) -> bool:
        """
        Check if a table looks like a salary table based on structure

        Returns True if table has:
        - A 'Step' column
        - At least one education level column (B, M, MA, etc.)
        """
        if not table or len(table) < 2:
            return False

        # Education patterns to look for
        edu_patterns = ['B', 'M', 'BA', 'MA', 'B+', 'M+', 'CAGS', 'DOC']

        # Check all rows for potential headers
        for row in table[:5]:  # Check first 5 rows
            if not row:
                continue
            normalized_row = [str(h).strip().upper().replace(' ', '') for h in row]

            # Check if this row has Step and education columns
            has_step = any('STEP' in col for col in normalized_row)
            has_education = any(
                any(edu in col for edu in edu_patterns)
                for col in normalized_row
            )

            if has_step and has_education:
                return True

        return False

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
                    alias_map = collect_lane_aliases(text)
                    tables = page.extract_tables()

                    # Check if this is a salary table page (by keyword OR by table structure)
                    has_keyword = text_has_salary_signal(text)

                    if has_keyword:
                        year = self.extract_year_from_text(text)

                        for table in tables:
                            if table and len(table) > 1:
                                # Try to extract year from table itself (first row might have FY26, etc.)
                                table_year = year  # Default to page-level year
                                if table[0] and table[0][0]:
                                    first_cell = str(table[0][0]).strip()
                                    extracted = self.extract_year_from_text(first_cell)
                                    if extracted != "unknown":
                                        table_year = extracted

                                records = self.parse_salary_table(table, district, table_year, alias_map)
                                all_records.extend(records)
                                logger.debug(f"Page {page_num}: extracted {len(records)} records (keyword match)")
                    else:
                        # No keyword, but check if tables look like salary tables
                        year = self.extract_year_from_text(text)

                        for table in tables:
                            if table and len(table) > 1 and self.is_salary_table(table):
                                # Try to extract year from table itself (first row might have FY26, etc.)
                                table_year = year  # Default to page-level year
                                if table[0] and table[0][0]:
                                    first_cell = str(table[0][0]).strip()
                                    extracted = self.extract_year_from_text(first_cell)
                                    if extracted != "unknown":
                                        table_year = extracted

                                records = self.parse_salary_table(table, district, table_year, alias_map)
                                if records:  # Only extend if we got records
                                    all_records.extend(records)
                                    logger.debug(f"Page {page_num}: extracted {len(records)} records (structure match)")

            return all_records if all_records else None

        except Exception as e:
            logger.error(f"pdfplumber extraction failed: {e}")
            return None

    def extract_with_pypdfium(self, pdf_bytes: bytes, filename: str, district_name: str) -> Optional[List[Dict]]:
        """Extract salary data using pypdfium2 for robust text layout parsing."""
        if not PYPDFIUM_AVAILABLE or pdfium is None:  # type: ignore[truthy-bool]
            logger.warning("pypdfium2 not available, skipping PDFium extraction")
            return None

        try:
            logger.info(f"Extracting with pypdfium2: {filename}")

            district = district_name
            all_records: List[Dict] = []

            pdf = pdfium.PdfDocument(pdf_bytes)  # type: ignore[call-arg]
            for page_index in range(len(pdf)):
                page_num = page_index + 1
                page = pdf[page_index]
                textpage = page.get_textpage()
                text = textpage.get_text_range() or ''
                textpage.close()

                if not text_has_salary_signal(text):
                    continue

                year = self.extract_year_from_text(text)
                alias_map = collect_lane_aliases(text)
                lines = text.split('\n')

                column_tables = self.parse_column_oriented_tables(lines)
                for block_idx, table_data in enumerate(column_tables, start=1):
                    logger.debug(
                        "PDFium page %s: parsed column block %s (%s rows x %s cols)",
                        page_num,
                        block_idx,
                        len(table_data),
                        len(table_data[0]) if table_data else 0,
                    )
                    records = self.parse_salary_table(table_data, district, year, alias_map)
                    all_records.extend(records)

                row_table = parse_row_oriented_table(lines)
                if row_table:
                    logger.debug(
                        "PDFium page %s: parsed row-oriented fallback (%s rows x %s cols)",
                        page_num,
                        len(row_table),
                        len(row_table[0]) if row_table else 0,
                    )
                    records = self.parse_salary_table(row_table, district, year, alias_map)
                    all_records.extend(records)

                page.close()

            pdf.close()

            # Deduplicate records (same table might be extracted via column + row parsers)
            if all_records:
                all_records = self.deduplicate_records(all_records)

            return all_records if all_records else None

        except Exception as e:  # pragma: no cover - debugging helper
            logger.error(f"pypdfium2 extraction failed: {e}", exc_info=True)
            return None

    def parse_column_oriented_tables(self, lines: List[str]) -> List[List[List[str]]]:
        """Parse all column-oriented tables found within the provided text lines."""
        return parse_column_oriented_tables_from_lines(lines)

    def parse_column_oriented_table(self, lines: List[str]) -> Optional[List[List[str]]]:
        """Parse the first column-oriented table from the provided text lines."""
        return parse_column_oriented_table_from_lines(lines)

    def extract_with_pymupdf(self, pdf_bytes: bytes, filename: str, district_name: str) -> Optional[List[Dict]]:
        """
        Extract salary data using PyMuPDF

        Args:
            pdf_bytes: PDF file content
            filename: Original filename
            district_name: District name to use in records

        Returns:
            List of salary records or None if extraction fails
        """
        if not PYMUPDF_AVAILABLE or fitz is None:  # type: ignore[truthy-bool]
            logger.warning("PyMuPDF not available, skipping")
            return None

        try:
            logger.info(f"Extracting with PyMuPDF: {filename}")

            district = district_name
            all_records = []

            doc = fitz.open(stream=pdf_bytes, filetype="pdf")

            for page_index in range(len(doc)):
                page_num = page_index + 1
                page = doc[page_index]
                text = str(page.get_text() or '')

                # Check if this looks like a salary table page
                if not text_has_salary_signal(text):
                    continue

                year = self.extract_year_from_text(text)
                alias_map = collect_lane_aliases(text)

                # Try built-in table detection first
                table_finder = getattr(page, 'find_tables', None)
                tables = table_finder() if callable(table_finder) else None
                table_objects = getattr(tables, 'tables', None) if tables is not None else None
                if table_objects:
                    logger.debug(f"Page {page_num}: PyMuPDF found {len(table_objects)} tables with built-in detection")
                    for table_obj in table_objects:
                        table_data = table_obj.extract()
                        if table_data and len(table_data) > 1:
                            # Try to extract year from table itself (first row might have FY26, etc.)
                            table_year = year  # Default to page-level year
                            if table_data[0] and table_data[0][0]:
                                first_cell = str(table_data[0][0]).strip()
                                extracted = self.extract_year_from_text(first_cell)
                                if extracted != "unknown":
                                    table_year = extracted

                            records = self.parse_salary_table(table_data, district, table_year, alias_map)
                            all_records.extend(records)

                lines = text.split('\n')
                column_tables = self.parse_column_oriented_tables(lines)
                for block_idx, table_data in enumerate(column_tables, start=1):
                    logger.debug(
                        "Page %s: parsed column-oriented block %s (%s rows x %s cols)",
                        page_num,
                        block_idx,
                        len(table_data),
                        len(table_data[0]) if table_data else 0,
                    )
                    records = self.parse_salary_table(table_data, district, year, alias_map)
                    all_records.extend(records)

                row_table = parse_row_oriented_table(lines)
                if row_table:
                    logger.debug(
                        "Page %s: parsed row-oriented fallback (%s rows x %s cols)",
                        page_num,
                        len(row_table),
                        len(row_table[0]) if row_table else 0,
                    )
                    records = self.parse_salary_table(row_table, district, year, alias_map)
                    all_records.extend(records)

            doc.close()

            # Deduplicate records (same table might be extracted via built-in + column + row parsers)
            if all_records:
                all_records = self.deduplicate_records(all_records)

            return all_records if all_records else None

        except Exception as e:
            logger.error(f"PyMuPDF extraction failed: {e}", exc_info=True)
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

        Extraction order:
        1. pdfplumber (fast, works for most text PDFs)
        2. pypdfium2 (better for column-oriented layouts)
        3. PyMuPDF (better text extraction, handles encoding issues and column-oriented layouts)
        4. AWS Textract (for image-based/scanned PDFs)

        Falls back to next method if records found < 200

        Args:
            pdf_bytes: PDF file content
            filename: Original filename
            district_name: District name to use in records
            s3_bucket: S3 bucket where PDF is stored
            s3_key: S3 key of the PDF

        Returns:
            Tuple of (records, method_used)
        """
        MIN_RECORDS_THRESHOLD = 200

        # Try pdfplumber first for text-based PDFs
        if self.is_text_based_pdf(pdf_bytes):
            logger.info(f"✓ Text-based PDF detected: {filename}")
            records = self.extract_with_pdfplumber(pdf_bytes, filename, district_name)
            if records:
                # Filter records by year and period
                records = self.filter_records_by_year_and_period(records)
                # Final deduplication to prevent DynamoDB duplicate key errors
                records = self.deduplicate_records(records)
                if len(records) >= MIN_RECORDS_THRESHOLD:
                    logger.info(f"pdfplumber extracted {len(records)} records (>= {MIN_RECORDS_THRESHOLD})")
                    return records, "pdfplumber"
                else:
                    logger.warning(f"pdfplumber extracted only {len(records)} records (< {MIN_RECORDS_THRESHOLD}), trying next method")
            else:
                logger.warning("pdfplumber extraction returned no records")

            if PYPDFIUM_AVAILABLE and pdfium is not None:  # type: ignore[truthy-bool]
                logger.info(f"Trying pypdfium2 fallback: {filename}")
                records = self.extract_with_pypdfium(pdf_bytes, filename, district_name)
                if records:
                    records = self.filter_records_by_year_and_period(records)
                    # Final deduplication to prevent DynamoDB duplicate key errors
                    records = self.deduplicate_records(records)
                    if len(records) >= MIN_RECORDS_THRESHOLD:
                        logger.info(f"pypdfium2 extracted {len(records)} records (>= {MIN_RECORDS_THRESHOLD})")
                        return records, "pypdfium"
                    else:
                        logger.warning(f"pypdfium2 extracted only {len(records)} records (< {MIN_RECORDS_THRESHOLD}), trying next method")
                else:
                    logger.warning("pypdfium2 extraction returned no records, falling back to PyMuPDF")
            else:
                logger.info("pypdfium2 not available, skipping PDFium fallback")

            # Try PyMuPDF as fallback before Textract
            if PYMUPDF_AVAILABLE and fitz is not None:
                logger.info(f"Trying PyMuPDF fallback: {filename}")
                records = self.extract_with_pymupdf(pdf_bytes, filename, district_name)
                if records:
                    # Filter records by year and period
                    records = self.filter_records_by_year_and_period(records)
                    # Final deduplication to prevent DynamoDB duplicate key errors
                    records = self.deduplicate_records(records)
                    if len(records) >= MIN_RECORDS_THRESHOLD:
                        logger.info(f"PyMuPDF extracted {len(records)} records (>= {MIN_RECORDS_THRESHOLD})")
                        return records, "pymupdf"
                    else:
                        logger.warning(f"PyMuPDF extracted only {len(records)} records (< {MIN_RECORDS_THRESHOLD}), falling back to Textract")
                else:
                    logger.warning("PyMuPDF extraction returned no records, falling back to Textract")
            else:
                logger.warning("PyMuPDF not available, falling back to Textract")
        else:
            logger.info(f"⚠ Image-based PDF detected: {filename}")

        # Fall back to Textract for image-based PDFs or when other methods fail
        logger.info(f"Using AWS Textract for: {filename}")
        records = self.extract_with_textract(pdf_bytes, filename, district_name, s3_bucket, s3_key)
        if records:
            # Filter records by year and period
            records = self.filter_records_by_year_and_period(records)
            # Final deduplication to prevent DynamoDB duplicate key errors
            records = self.deduplicate_records(records)
            logger.info(f"Textract extracted {len(records)} records")
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
            'pymupdf_count': 0,
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

                # Extract district name from filename
                district_name = Path(filename).stem.split('_')[0].title()

                # Extract data
                records, method = self.extract_from_pdf(pdf_bytes, filename, district_name, input_bucket, pdf_key)

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
                    elif method == 'pymupdf':
                        results['pymupdf_count'] += 1
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
        logger.info(f"PyMuPDF:          {results['pymupdf_count']}")
        logger.info(f"AWS Textract:     {results['textract_count']}")
        logger.info(f"{'='*60}")

        return results