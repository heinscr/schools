"""
Table Detection and Extraction Module
Detects and parses salary schedule tables from contract text
"""
import re
import logging
from typing import Dict, List, Optional, Tuple
from decimal import Decimal
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class SalaryTable:
    """Represents an extracted salary schedule table"""
    district_name: str
    school_year: str
    effective_date: str
    steps: List[int]
    education_columns: List[str]
    data: Dict[Tuple[int, str], Decimal]  # (step, edu_col) -> salary
    metadata: Dict
    page_number: int


class TableDetector:
    """
    Detect and classify salary schedule tables in contract text
    """

    # Patterns to identify salary tables
    SALARY_TABLE_PATTERNS = [
        r'SALARY\s+SCHEDULE',
        r'COMPENSATION\s+SCHEDULE',
        r'TEACHERS?\s+SCHEDULE',
        r'APPENDIX\s+A',
        r'SCHEDULE\s+A',
        r'Article\s+46'  # Agawam uses this
    ]

    # Pattern to extract effective dates
    DATE_PATTERNS = [
        r'Effective\s+(?:July|September)\s+\d{1,2},?\s+(\d{4})',
        r'(?:July|September)\s+\d{1,2},?\s+(\d{4})'
    ]

    # Pattern to extract school years
    YEAR_PATTERN = r'(\d{4})-(\d{4})'

    def find_salary_tables(self, pages: List[Dict]) -> List[Dict]:
        """
        Locate pages containing salary tables

        Args:
            pages: List of page dictionaries with 'text' and 'tables'

        Returns:
            List of table page metadata with extracted year/date info
        """
        table_pages = []

        for page in pages:
            text = page.get('text', '')

            # Check if page contains salary table keywords
            if self._is_salary_table_page(text):
                # Extract year/effective date
                year = self._extract_school_year(text)
                effective_date = self._extract_effective_date(text)

                table_pages.append({
                    'page_number': page['page_number'],
                    'school_year': year,
                    'effective_date': effective_date,
                    'text': text,
                    'tables': page.get('tables', [])
                })

                logger.info(
                    f"Found salary table on page {page['page_number']}: "
                    f"year={year}, effective={effective_date}"
                )

        return table_pages

    def _is_salary_table_page(self, text: str) -> bool:
        """Check if page contains a salary table"""
        for pattern in self.SALARY_TABLE_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE):
                return True
        return False

    def _extract_school_year(self, text: str) -> Optional[str]:
        """
        Extract school year using multiple pattern matching strategies

        Tries in order:
        1. School year format: "2022-2023"
        2. Effective date with month: "Effective July 1, 2022"
        3. Month followed by year: "July 2022"
        4. Any 4-digit year in 2000-2099 range

        Examples:
            "2022-2023" → "2022-2023"
            "Effective July 1, 2022" → "2022-2023"
            "Teachers Salary Schedule 2023-2024" → "2023-2024"
            "July 2022" → "2022-2023"
        """
        if not text:
            return None

        # Strategy 1: Look for YYYY-YYYY pattern (e.g., "2022-2023")
        match = re.search(r'(\d{4})\s*[-–—]\s*(\d{4})', text)
        if match:
            year1, year2 = match.group(1), match.group(2)
            return f"{year1}-{year2}"

        # Strategy 2: Look for "Effective [Month] [Day,] YYYY" pattern
        # Matches: "Effective July 1, 2022" or "Effective September 1, 2023"
        match = re.search(
            r'Effective\s+(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s+(\d{4})',
            text,
            re.IGNORECASE
        )
        if match:
            year = int(match.group(1))
            # Convert to school year format (e.g., 2022 -> "2022-2023")
            return f"{year}-{year + 1}"

        # Strategy 3: Look for month name followed by year
        # Matches: "July 2022" or "September 2023"
        match = re.search(
            r'(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{4})',
            text,
            re.IGNORECASE
        )
        if match:
            year = int(match.group(1))
            # Convert to school year format
            return f"{year}-{year + 1}"

        # Strategy 4: Look for any standalone 4-digit year (2000-2099)
        # This is a fallback and less reliable
        years = re.findall(r'\b(20\d{2})\b', text)
        if years:
            # Take the most recent year found
            year = int(max(years))
            return f"{year}-{year + 1}"

        return None

    def _extract_effective_date(self, text: str) -> Optional[str]:
        """
        Extract effective date year

        Examples:
            "Effective July 1, 2022" → "2022"
            "Effective September 1, 2023" → "2023"
        """
        for pattern in self.DATE_PATTERNS:
            match = re.search(pattern, text)
            if match:
                return match.group(1)
        return None


class TableParser:
    """
    Parse extracted table data into structured salary records
    """

    # Education column mappings to (education_code, credits)
    # Based on your config: education in {B, M, D}, credits in {0, 15, 30, 45, 60}
    EDUCATION_MAPPINGS = {
        'BA': ('B', 0),
        'B': ('B', 0),
        'BA+15': ('B', 15),
        'B+15': ('B', 15),
        'BA+30': ('B', 30),
        'B+30': ('B', 30),
        'B30/MA': ('M', 0),
        'B30': ('M', 0),
        'MA': ('M', 0),
        'M': ('M', 0),
        'MASTERS': ('M', 0),
        'MA+15': ('M', 15),
        'M+15': ('M', 15),
        'MA+30': ('M', 30),
        'M+30': ('M', 30),
        'MA+45': ('M', 45),
        'M+45': ('M', 45),
        'MA+45/CAGS': ('M', 45),
        'CAGS': ('M', 60),
        'CAGS/DOC': ('D', 0),
        'DOC': ('D', 0),
        'DOCTORATE': ('D', 0),
    }

    def parse_table(
        self,
        raw_table: List[List[str]],
        district_name: str,
        school_year: str,
        page_number: int
    ) -> Optional[SalaryTable]:
        """
        Parse a raw table array into structured salary data

        Expected format:
        [
            ['', 'BA', 'BA+15', 'MA', 'MA+15', ...],
            ['Step 1', '$49,189', '$50,476', ...],
            ['Step 2', '$50,135', '$51,457', ...],
            ...
        ]

        Args:
            raw_table: 2D array of table cells
            district_name: District name
            school_year: School year (e.g. "2022-2023")
            page_number: Page number for reference

        Returns:
            SalaryTable object or None if parsing fails
        """
        if not raw_table or len(raw_table) < 2:
            logger.warning(
                f"Table too small (need header + data rows): {len(raw_table)} rows"
            )
            return None

        try:
            # Parse header row (education columns)
            header = raw_table[0]
            education_columns = self._parse_education_columns(header)

            if not education_columns:
                logger.warning("No education columns found in header")
                return None

            logger.debug(f"Education columns: {education_columns}")

            # Parse data rows
            salary_data = {}
            steps = []

            for row_idx, row in enumerate(raw_table[1:], start=1):
                if not row or len(row) < 2:
                    continue

                # Extract step number from first column
                step = self._extract_step_number(row[0])
                if step is None:
                    logger.debug(f"Skipping row {row_idx}: no step number in '{row[0]}'")
                    continue

                steps.append(step)

                # Extract salaries for each education level
                for col_idx, edu_col in enumerate(education_columns):
                    # Column index is offset by 1 (first column is step)
                    if col_idx + 1 < len(row):
                        salary = self._parse_salary(row[col_idx + 1])
                        if salary is not None:
                            salary_data[(step, edu_col)] = salary

            if not salary_data:
                logger.warning("No salary data extracted from table")
                return None

            logger.info(
                f"Parsed table: {len(steps)} steps, "
                f"{len(education_columns)} columns, "
                f"{len(salary_data)} cells"
            )

            return SalaryTable(
                district_name=district_name,
                school_year=school_year or 'unknown',
                effective_date='',
                steps=sorted(steps),
                education_columns=education_columns,
                data=salary_data,
                metadata={'total_cells': len(salary_data)},
                page_number=page_number
            )

        except Exception as e:
            logger.error(f"Error parsing table: {e}")
            return None

    def _parse_education_columns(self, header: List[str]) -> List[str]:
        """
        Extract education column names from header

        Args:
            header: First row of table

        Returns:
            List of normalized education column names
        """
        columns = []

        for cell in header:
            if not cell:
                continue

            # Clean up the cell text
            cleaned = cell.strip().upper()
            cleaned = cleaned.replace(' ', '')
            cleaned = cleaned.replace('/', '/')  # Keep slashes

            # Skip common non-education headers
            if cleaned in ['', 'STEPS', 'STEP']:
                continue

            # Check if this looks like an education column
            if any(edu_key in cleaned for edu_key in ['BA', 'MA', 'DOC', 'CAGS', 'B+', 'M+']):
                columns.append(cleaned)

        return columns

    def _extract_step_number(self, cell: str) -> Optional[int]:
        """
        Extract step number from cell like 'Step 1', 'Step 2', or just '1'

        Args:
            cell: Table cell content

        Returns:
            Step number or None
        """
        if not cell:
            return None

        # Look for any number in the cell
        match = re.search(r'\b(\d+)\b', str(cell))
        if match:
            step = int(match.group(1))
            # Validate step is in reasonable range
            if 1 <= step <= 20:
                return step

        return None

    def _parse_salary(self, cell: str) -> Optional[Decimal]:
        """
        Parse salary from cell like '$49,189' or '49189'

        Args:
            cell: Table cell content

        Returns:
            Decimal salary value or None
        """
        if not cell or not str(cell).strip():
            return None

        # Remove currency symbols, commas, whitespace, dollar signs
        cleaned = re.sub(r'[$,\s]', '', str(cell))

        # Try to convert to decimal
        try:
            value = Decimal(cleaned)
            # Validate salary is in reasonable range (e.g., $20k - $200k)
            if 20000 <= value <= 200000:
                return value
            else:
                logger.debug(f"Salary out of range: {value}")
                return None
        except:
            logger.debug(f"Could not parse salary: '{cell}'")
            return None

    def normalize_to_json_format(self, table: SalaryTable) -> List[Dict]:
        """
        Convert SalaryTable to the JSON format used by your system

        Format:
        {
            "district_id": "bedford",
            "district_name": "Bedford",
            "school_year": "2022-2023",
            "period": "full-year",
            "education": "B",
            "credits": 0,
            "step": 1,
            "salary": 47796.0
        }

        Args:
            table: SalaryTable object

        Returns:
            List of salary records in JSON format
        """
        records = []
        unmapped_columns = set()

        for (step, edu_col), salary in table.data.items():
            # Map education column to (education, credits) tuple
            if edu_col in self.EDUCATION_MAPPINGS:
                education, credits = self.EDUCATION_MAPPINGS[edu_col]

                records.append({
                    'district_id': table.district_name.lower(),
                    'district_name': table.district_name,
                    'school_year': table.school_year,
                    'period': 'full-year',
                    'education': education,
                    'credits': credits,
                    'step': step,
                    'salary': float(salary)
                })
            else:
                # Track unmapped columns for debugging
                unmapped_columns.add(edu_col)

        # Log warnings for unmapped columns
        if unmapped_columns:
            logger.warning(
                f"Unmapped education columns in {table.district_name}: "
                f"{', '.join(unmapped_columns)}"
            )

        logger.info(
            f"Normalized {len(records)} records for {table.district_name} "
            f"{table.school_year}"
        )

        return records
