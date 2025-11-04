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

# Allowed characters patterns
# Allow alphanumeric, spaces, hyphens, apostrophes, periods, and common punctuation
SAFE_TEXT_PATTERN = re.compile(r'^[a-zA-Z0-9\s\-\'.&,()]+$')


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
