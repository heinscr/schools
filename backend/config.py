"""
Application configuration constants
Centralized configuration for magic numbers, strings, and settings
"""

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
VALID_CREDITS = {0, 15, 30, 45, 60}
MIN_STEP = 1
MAX_STEP = 15

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
