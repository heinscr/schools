"""
Tests for application configuration constants
"""
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import config


class TestQueryConfiguration:
    """Tests for query configuration constants"""

    def test_query_limits(self):
        """Test query limit constants are set correctly"""
        assert config.MAX_QUERY_LIMIT == 100
        assert config.DEFAULT_QUERY_LIMIT == 50
        assert config.MIN_QUERY_LIMIT == 1

    def test_query_limits_relationship(self):
        """Test query limits have correct relationships"""
        assert config.MIN_QUERY_LIMIT < config.DEFAULT_QUERY_LIMIT
        assert config.DEFAULT_QUERY_LIMIT < config.MAX_QUERY_LIMIT


class TestDynamoDBConfiguration:
    """Tests for DynamoDB configuration constants"""

    def test_index_names(self):
        """Test DynamoDB index names are defined"""
        assert config.COMPARE_INDEX_NAME == "CompareDistrictsIndex"
        assert config.GSI_TOWN_INDEX_NAME == "GSI_TOWN"

    def test_fetch_limit(self):
        """Test DynamoDB fetch limit is set"""
        assert config.MAX_DYNAMODB_FETCH_LIMIT == 1000
        assert config.MAX_DYNAMODB_FETCH_LIMIT > 0


class TestSalaryConfiguration:
    """Tests for salary-related configuration constants"""

    def test_default_school_year(self):
        """Test default school year is defined"""
        assert config.DEFAULT_SCHOOL_YEAR == "2021-2022"
        assert "-" in config.DEFAULT_SCHOOL_YEAR

    def test_education_levels(self):
        """Test valid education levels"""
        assert config.VALID_EDUCATION_LEVELS == {'B', 'M', 'D'}
        assert 'B' in config.VALID_EDUCATION_LEVELS  # Bachelor's
        assert 'M' in config.VALID_EDUCATION_LEVELS  # Master's
        assert 'D' in config.VALID_EDUCATION_LEVELS  # Doctorate

    def test_valid_credits(self):
        """Test valid credit amounts"""
        assert config.VALID_CREDITS == {0, 15, 30, 45, 60}
        assert 0 in config.VALID_CREDITS
        assert 60 in config.VALID_CREDITS

    def test_step_range(self):
        """Test min and max step values"""
        assert config.MIN_STEP == 1
        assert config.MAX_STEP == 15
        assert config.MIN_STEP < config.MAX_STEP


class TestDistrictTypeConfiguration:
    """Tests for district type configuration"""

    def test_valid_district_types(self):
        """Test valid district types are defined"""
        expected_types = {
            'municipal',
            'regional_academic',
            'regional_vocational',
            'county_agricultural',
            'charter'
        }
        assert config.VALID_DISTRICT_TYPES == expected_types

    def test_district_types_count(self):
        """Test we have the expected number of district types"""
        assert len(config.VALID_DISTRICT_TYPES) == 5


class TestPaginationConfiguration:
    """Tests for pagination configuration"""

    def test_default_offset(self):
        """Test default offset is zero"""
        assert config.DEFAULT_OFFSET == 0


class TestJobAndTTLConfiguration:
    """Tests for job and TTL configuration"""

    def test_job_ttl_days(self):
        """Test job TTL is set to 30 days"""
        assert config.JOB_TTL_DAYS == 30

    def test_job_ttl_seconds(self):
        """Test job TTL in seconds is calculated correctly"""
        expected_seconds = 30 * 24 * 60 * 60  # 30 days in seconds
        assert config.JOB_TTL_SECONDS == expected_seconds
        assert config.JOB_TTL_SECONDS == 2592000


class TestRateLimitingDelays:
    """Tests for rate limiting delay configuration"""

    def test_backup_processing_delay(self):
        """Test backup processing delay"""
        assert config.BACKUP_PROCESSING_DELAY == 0.5
        assert config.BACKUP_PROCESSING_DELAY > 0

    def test_textract_retry_delay(self):
        """Test Textract retry delay"""
        assert config.TEXTRACT_RETRY_DELAY == 2.0
        assert config.TEXTRACT_RETRY_DELAY > 0

    def test_delays_relationship(self):
        """Test that Textract delay is longer than backup delay"""
        assert config.TEXTRACT_RETRY_DELAY > config.BACKUP_PROCESSING_DELAY
