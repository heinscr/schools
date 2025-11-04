"""
Input validation and sanitization utilities
"""
import re
from typing import Optional
from fastapi import HTTPException


# Maximum lengths for inputs
MAX_SEARCH_QUERY_LENGTH = 100
MAX_NAME_LENGTH = 200
MAX_TOWN_LENGTH = 100
MAX_DISTRICT_ID_LENGTH = 100

# Allowed characters patterns
# Allow alphanumeric, spaces, hyphens, apostrophes, periods, and common punctuation
SAFE_TEXT_PATTERN = re.compile(r'^[a-zA-Z0-9\s\-\'.&,()]+$')

# District ID pattern - allows:
# 1. Plain alphanumeric with hyphens (UUIDs, etc): 0f60fef3-cee7-43da-a8a8-b74826e3dfa0
# 2. Prefixed format: DISTRICT#<uuid> or DISTRICT%23<uuid> (URL-encoded)
# Only allows: letters (a-z, A-Z), numbers (0-9), hyphens (-), hash (#), and URL-encoded hash (%23)
DISTRICT_ID_PATTERN = re.compile(r'^[a-zA-Z0-9\-]+$|^[A-Z]+(%23|#)[a-zA-Z0-9\-]+$')


def validate_search_query(query: Optional[str]) -> Optional[str]:
    """
    Validate and sanitize search query input

    Args:
        query: The search query string

    Returns:
        Sanitized query string or None if input was None

    Raises:
        HTTPException: If query is invalid
    """
    if query is None:
        return None

    # Strip whitespace
    query = query.strip()

    # Empty after stripping
    if not query:
        return None

    # Check length
    if len(query) > MAX_SEARCH_QUERY_LENGTH:
        raise HTTPException(
            status_code=400,
            detail=f"Search query too long (max {MAX_SEARCH_QUERY_LENGTH} characters)"
        )

    # Check for safe characters
    if not SAFE_TEXT_PATTERN.match(query):
        raise HTTPException(
            status_code=400,
            detail="Search query contains invalid characters. Only alphanumeric, spaces, hyphens, apostrophes, periods, and common punctuation are allowed."
        )

    return query


def validate_name_filter(name: Optional[str]) -> Optional[str]:
    """
    Validate and sanitize name filter input

    Args:
        name: The name filter string

    Returns:
        Sanitized name string or None if input was None

    Raises:
        HTTPException: If name is invalid
    """
    if name is None:
        return None

    # Strip whitespace
    name = name.strip()

    # Empty after stripping
    if not name:
        return None

    # Check length
    if len(name) > MAX_NAME_LENGTH:
        raise HTTPException(
            status_code=400,
            detail=f"Name filter too long (max {MAX_NAME_LENGTH} characters)"
        )

    # Check for safe characters
    if not SAFE_TEXT_PATTERN.match(name):
        raise HTTPException(
            status_code=400,
            detail="Name filter contains invalid characters. Only alphanumeric, spaces, hyphens, apostrophes, periods, and common punctuation are allowed."
        )

    return name


def validate_town_filter(town: Optional[str]) -> Optional[str]:
    """
    Validate and sanitize town filter input

    Args:
        town: The town filter string

    Returns:
        Sanitized town string or None if input was None

    Raises:
        HTTPException: If town is invalid
    """
    if town is None:
        return None

    # Strip whitespace
    town = town.strip()

    # Empty after stripping
    if not town:
        return None

    # Check length
    if len(town) > MAX_TOWN_LENGTH:
        raise HTTPException(
            status_code=400,
            detail=f"Town filter too long (max {MAX_TOWN_LENGTH} characters)"
        )

    # Check for safe characters
    if not SAFE_TEXT_PATTERN.match(town):
        raise HTTPException(
            status_code=400,
            detail="Town filter contains invalid characters. Only alphanumeric, spaces, hyphens, apostrophes, periods, and common punctuation are allowed."
        )

    return town


def validate_district_id(district_id: str) -> str:
    """
    Validate district ID format

    Args:
        district_id: The district ID to validate

    Returns:
        Validated district ID

    Raises:
        HTTPException: If district ID is invalid
    """
    if not district_id or not district_id.strip():
        raise HTTPException(
            status_code=400,
            detail="District ID cannot be empty"
        )

    district_id = district_id.strip()

    # Check length
    if len(district_id) > MAX_DISTRICT_ID_LENGTH:
        raise HTTPException(
            status_code=400,
            detail=f"District ID too long (max {MAX_DISTRICT_ID_LENGTH} characters)"
        )

    # Check format - must be like DISTRICT#abc123 or ENTITY#xyz
    if not DISTRICT_ID_PATTERN.match(district_id):
        raise HTTPException(
            status_code=400,
            detail="Invalid district ID format. Must be in format: PREFIX#identifier (e.g., DISTRICT#abc123)"
        )

    return district_id
