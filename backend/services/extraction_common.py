"""
Common extraction utilities shared across all PDF extractors

This module provides unified implementations of salary/step parsing
and table detection logic to eliminate duplication between extractors.
"""
import re
import logging
from typing import Optional
from decimal import Decimal, InvalidOperation

logger = logging.getLogger(__name__)

# Shared salary table detection patterns
SALARY_TABLE_KEYWORDS = [
    'SALARY',
    'COMPENSATION',
    'TEACHERS',
    'SCHEDULE',
    'APPENDIX A',
    'SCHEDULE A',
    'STEP',
]

# Compile regex pattern for efficient matching
SALARY_TABLE_PATTERN = re.compile(
    r'(SALARY|COMPENSATION|TEACHERS?|SCHEDULE|STEP|APPENDIX\s+A)',
    re.IGNORECASE
)


def parse_salary_value(
    cell: str,
    min_val: int = 20000,
    max_val: int = 200000,
    return_decimal: bool = True
) -> Optional[Decimal]:
    """
    Parse and validate salary from cell content

    Unified implementation used by all extractors to ensure consistent
    salary parsing behavior across the application.

    Args:
        cell: Table cell content (e.g., "$49,189", "49189")
        min_val: Minimum valid salary value (default: $20,000)
        max_val: Maximum valid salary value (default: $200,000)
        return_decimal: If True, return Decimal; if False, return float

    Returns:
        Decimal or float salary value, or None if invalid

    Examples:
        >>> parse_salary_value("$49,189")
        Decimal('49189')
        >>> parse_salary_value("49189")
        Decimal('49189')
        >>> parse_salary_value("not a number")
        None
        >>> parse_salary_value("10000")  # Below min
        None
    """
    if not cell or not str(cell).strip():
        return None

    # Remove currency symbols, commas, whitespace, dollar signs
    cleaned = re.sub(r'[$,\s]', '', str(cell))

    # Remove any non-numeric characters except decimal point
    cleaned = re.sub(r'[^\d.]', '', cleaned)

    if not cleaned:
        return None

    try:
        value = Decimal(cleaned)

        # Validate salary is in reasonable range
        if min_val <= value <= max_val:
            return value if return_decimal else float(value)
        else:
            logger.debug(f"Salary out of range ({min_val}-{max_val}): {value}")
            return None

    except (InvalidOperation, ValueError) as e:
        logger.debug(f"Could not parse salary from '{cell}': {e}")
        return None


def is_salary_value(cell: str) -> bool:
    """
    Check if cell contains a valid salary value (boolean check only)

    Faster version of parse_salary_value for validation without conversion.

    Args:
        cell: Table cell content

    Returns:
        True if cell appears to contain a salary value

    Examples:
        >>> is_salary_value("$49,189")
        True
        >>> is_salary_value("49189")
        True
        >>> is_salary_value("Step 1")
        False
    """
    if not cell or not str(cell).strip():
        return False

    # Remove currency symbols, commas, whitespace, decimal points
    token = str(cell).strip()
    token = token.replace('$', '').replace(',', '').replace(' ', '').replace('.', '')

    return token.isdigit() and len(token) >= 4  # At least 4 digits for realistic salary


def extract_step_number(
    cell: str,
    min_step: int = 1,
    max_step: int = 20
) -> Optional[int]:
    """
    Extract and validate step number from cell content

    Unified implementation used by all extractors to ensure consistent
    step number extraction across the application.

    Args:
        cell: Table cell content (e.g., "Step 1", "1", "Step 10")
        min_step: Minimum valid step number (default: 1)
        max_step: Maximum valid step number (default: 20)

    Returns:
        Step number as integer, or None if invalid

    Examples:
        >>> extract_step_number("Step 1")
        1
        >>> extract_step_number("10")
        10
        >>> extract_step_number("25")  # Above max
        None
        >>> extract_step_number("Step")
        None
    """
    if not cell:
        return None

    # Look for any number in the cell
    match = re.search(r'\b(\d+)\b', str(cell))
    if match:
        step = int(match.group(1))

        # Validate step is in reasonable range
        if min_step <= step <= max_step:
            return step
        else:
            logger.debug(f"Step number out of range ({min_step}-{max_step}): {step}")
            return None

    return None


def is_step_marker(cell: str) -> bool:
    """
    Check if cell contains a step marker (boolean check only)

    Faster version for validation without extraction.

    Args:
        cell: Table cell content

    Returns:
        True if cell appears to be a step marker

    Examples:
        >>> is_step_marker("1")
        True
        >>> is_step_marker("Step 5")
        True
        >>> is_step_marker("5-6")  # Step range
        True
        >>> is_step_marker("BA")
        False
    """
    if not cell:
        return False

    # Normalize dashes
    token = str(cell).strip().replace('–', '-').replace('—', '-')

    # Match single digit, double digit, or range (e.g., "1", "10", "1-2")
    pattern = re.compile(r'^\d{1,2}(?:[-/]\d{1,2})?$')

    return bool(pattern.match(token))


def has_salary_table_signal(text: str) -> bool:
    """
    Check if text contains salary table indicators

    Used for detecting pages or sections that likely contain salary schedules.

    Args:
        text: Text content to check

    Returns:
        True if text contains salary table keywords

    Examples:
        >>> has_salary_table_signal("SALARY SCHEDULE")
        True
        >>> has_salary_table_signal("Teacher Compensation")
        True
        >>> has_salary_table_signal("Random text")
        False
    """
    if not text:
        return False

    # Use compiled regex for efficiency
    if SALARY_TABLE_PATTERN.search(text):
        return True

    # Fallback to keyword search (case-insensitive)
    upper = text.upper()
    return any(keyword in upper for keyword in SALARY_TABLE_KEYWORDS)


def looks_like_step_header(text: str) -> bool:
    """
    Check if text looks like a step column header

    Args:
        text: Header text to check

    Returns:
        True if text appears to be a step column header

    Examples:
        >>> looks_like_step_header("Step")
        True
        >>> looks_like_step_header("STEP")
        True
        >>> looks_like_step_header("Years")
        False
    """
    if not text:
        return False

    normalized = str(text).strip().upper()
    if not normalized:
        return False

    # Check for "STEP" prefix
    if normalized.startswith('STEP'):
        return True

    # Remove non-alphabetic characters and check again
    simplified = re.sub(r'[^A-Z]', '', normalized)
    return simplified == 'STEP' or simplified == 'YEARS'


def normalize_education_label(text: str) -> str:
    """
    Normalize education column labels to standard format

    Args:
        text: Education column header text

    Returns:
        Normalized education label

    Examples:
        >>> normalize_education_label("B.A.")
        "BA"
        >>> normalize_education_label("Master's")
        "MA"
        >>> normalize_education_label("BA+15")
        "BA+15"
    """
    if not text:
        return ''

    normalized = str(text).upper().strip()

    # Normalize common variations
    normalized = normalized.replace('B.A.', 'BA').replace('M.A.', 'MA')
    normalized = normalized.replace('BACHELOR', 'BA').replace('BACCALAUREATE', 'BA')
    normalized = normalized.replace('MASTER', 'MA').replace('MASTERS', 'MA')
    normalized = normalized.replace('DOCTORATE', 'DOC').replace('DOCTORAL', 'DOC')

    # Normalize separators
    normalized = normalized.replace(' ', '').replace('-', '+')

    return normalized
