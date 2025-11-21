"""
Application configuration constants
Centralized configuration for magic numbers, strings, and settings
"""
import os
import boto3
from functools import lru_cache

# Query Configuration
MAX_QUERY_LIMIT = 100
DEFAULT_QUERY_LIMIT = 50
MIN_QUERY_LIMIT = 1

# DynamoDB Configuration
COMPARE_INDEX_NAME = "CompareDistrictsIndex"
GSI_TOWN_INDEX_NAME = "GSI_TOWN"

# DoS Protection - Maximum items to fetch from DynamoDB in a single operation
# This prevents expensive queries that could exhaust resources
MAX_DYNAMODB_FETCH_LIMIT = 1000

# Salary Configuration
DEFAULT_SCHOOL_YEAR = "2021-2022"
VALID_EDUCATION_LEVELS = {'B', 'M', 'D'}
MIN_STEP = 1

# MAX_STEP and VALID_CREDITS are loaded dynamically from DynamoDB metadata
# Use get_max_step() and get_valid_credits() functions to retrieve them
_MAX_STEP_FALLBACK = 15  # Fallback value if metadata is not available
_VALID_CREDITS_FALLBACK = {0, 15, 30, 45, 60}  # Fallback values if metadata is not available

@lru_cache(maxsize=1)
def _get_metadata():
    """
    Get metadata from DynamoDB. Internal function that caches the full metadata response.
    This is called by get_max_step() and get_valid_credits() to avoid duplicate queries.

    Returns:
        dict: Metadata item or None if not available
    """
    try:
        table_name = os.environ.get('DYNAMODB_TABLE_NAME')
        if not table_name:
            return None

        dynamodb = boto3.resource('dynamodb')
        table = dynamodb.Table(table_name)

        response = table.get_item(
            Key={'PK': 'METADATA#MAXVALUES', 'SK': 'GLOBAL'}
        )

        if 'Item' in response:
            return response['Item']

        return None
    except Exception:
        # If there's any error (network, permissions, etc.), return None
        return None

def get_max_step() -> int:
    """
    Get the maximum step value from DynamoDB metadata.
    This is cached for the lifetime of the process.

    Returns:
        int: Maximum step value from METADATA#MAXVALUES or fallback value
    """
    metadata = _get_metadata()
    if metadata:
        return int(metadata.get('max_step', _MAX_STEP_FALLBACK))
    return _MAX_STEP_FALLBACK

def get_valid_credits() -> set:
    """
    Get valid credit values from DynamoDB metadata's edu_credit_combos array.
    This extracts unique credit values from combos like 'B', 'M+30', 'M+45', etc.
    This is cached for the lifetime of the process.

    Returns:
        set: Set of valid credit values extracted from edu_credit_combos or fallback set
    """
    metadata = _get_metadata()
    if metadata and 'edu_credit_combos' in metadata:
        combos = metadata['edu_credit_combos']
        credits = set()

        for combo in combos:
            # Parse combos like "B", "M+30", "D" to extract credit amounts
            if '+' in combo:
                # Extract the credit number after the '+'
                parts = combo.split('+')
                if len(parts) == 2:
                    try:
                        credit = int(parts[1])
                        credits.add(credit)
                    except (ValueError, IndexError):
                        pass
            else:
                # No credit modifier means 0 credits
                credits.add(0)

        # Return the extracted credits, or fallback if empty
        return credits if credits else _VALID_CREDITS_FALLBACK

    return _VALID_CREDITS_FALLBACK

# For backward compatibility, keep these as constants but mark them as deprecated
MAX_STEP = _MAX_STEP_FALLBACK  # Deprecated: Use get_max_step() instead
VALID_CREDITS = _VALID_CREDITS_FALLBACK  # Deprecated: Use get_valid_credits() instead

# District Type Configuration
VALID_DISTRICT_TYPES = {
    'municipal',
    'regional_academic',
    'regional_vocational',
    'county_agricultural',
    'charter'
}

# Pagination
DEFAULT_OFFSET = 0

# Job and Record TTL Configuration (in seconds)
JOB_TTL_DAYS = 30  # Jobs expire after 30 days
JOB_TTL_SECONDS = JOB_TTL_DAYS * 24 * 60 * 60

# Rate Limiting Delays (in seconds)
BACKUP_PROCESSING_DELAY = 0.5  # Delay between processing backup files
TEXTRACT_RETRY_DELAY = 2.0  # Delay before retrying Textract operations
