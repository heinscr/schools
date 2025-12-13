"""
Utility functions for normalizing period values to the standard format.

All period values should be normalized to "Full Year" (with capital F and Y)
for consistency across the system.
"""

from typing import Optional


def normalize_period(period: Optional[str]) -> str:
    """
    Normalize a period value to the standard format.

    The standard format is "Full Year" (with capital F and Y, space separated).

    This function converts common variations:
    - "full year", "full-year", "FULL YEAR", "FULL_YEAR" -> "Full Year"
    - "FY", "fy" -> "Full Year"
    - Other periods (spring, fall, 10-month, etc.) are preserved as-is

    Args:
        period: The period value to normalize

    Returns:
        Normalized period value

    Examples:
        >>> normalize_period("full-year")
        "Full Year"
        >>> normalize_period("FY")
        "Full Year"
        >>> normalize_period("spring")
        "spring"
    """
    if not period or not period.strip():
        return "Full Year"

    # Already correct
    if period == "Full Year":
        return period

    # Normalize the input for comparison
    normalized = period.lower().replace('-', ' ').replace('_', ' ').strip()

    # Check if it's a variation of "full year"
    if normalized == "full year":
        return "Full Year"

    # Check for common full-year abbreviations
    if period.upper() in ['FY', 'FULL_YEAR', 'FULLYEAR']:
        return "Full Year"

    # For other period types (spring, fall, 10-month, etc.), return as-is
    return period


def normalize_period_in_record(record: dict) -> dict:
    """
    Normalize the period field in a salary record.

    Args:
        record: Dictionary containing salary record data with 'period' field

    Returns:
        Modified record with normalized period

    Examples:
        >>> record = {'school_year': '2024-2025', 'period': 'full-year', 'salary': 50000}
        >>> normalize_period_in_record(record)
        {'school_year': '2024-2025', 'period': 'Full Year', 'salary': 50000}
    """
    if 'period' in record:
        record['period'] = normalize_period(record['period'])
    return record


def normalize_periods_in_records(records: list) -> list:
    """
    Normalize period fields in a list of salary records.

    Args:
        records: List of salary record dictionaries

    Returns:
        List with normalized periods

    Examples:
        >>> records = [
        ...     {'period': 'full-year', 'salary': 50000},
        ...     {'period': 'FY', 'salary': 55000}
        ... ]
        >>> normalize_periods_in_records(records)
        [{'period': 'Full Year', 'salary': 50000}, {'period': 'Full Year', 'salary': 55000}]
    """
    return [normalize_period_in_record(record) for record in records]
