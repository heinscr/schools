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
