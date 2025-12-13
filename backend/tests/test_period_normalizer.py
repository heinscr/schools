"""
Tests for period normalization utilities
"""
import pytest
from utils.period_normalizer import normalize_period, normalize_period_in_record, normalize_periods_in_records


class TestNormalizePeriod:
    """Test the normalize_period function"""

    def test_already_normalized(self):
        """Test that 'Full Year' is returned unchanged"""
        assert normalize_period("Full Year") == "Full Year"

    def test_lowercase_with_hyphen(self):
        """Test 'full-year' is normalized to 'Full Year'"""
        assert normalize_period("full-year") == "Full Year"

    def test_lowercase_with_space(self):
        """Test 'full year' is normalized to 'Full Year'"""
        assert normalize_period("full year") == "Full Year"

    def test_uppercase_with_hyphen(self):
        """Test 'FULL-YEAR' is normalized to 'Full Year'"""
        assert normalize_period("FULL-YEAR") == "Full Year"

    def test_uppercase_with_space(self):
        """Test 'FULL YEAR' is normalized to 'Full Year'"""
        assert normalize_period("FULL YEAR") == "Full Year"

    def test_uppercase_with_underscore(self):
        """Test 'FULL_YEAR' is normalized to 'Full Year'"""
        assert normalize_period("FULL_YEAR") == "Full Year"

    def test_fy_abbreviation(self):
        """Test 'FY' is normalized to 'Full Year'"""
        assert normalize_period("FY") == "Full Year"
        assert normalize_period("fy") == "Full Year"

    def test_fullyear_no_separator(self):
        """Test 'FULLYEAR' is normalized to 'Full Year'"""
        assert normalize_period("FULLYEAR") == "Full Year"

    def test_mixed_case(self):
        """Test 'Full-Year' is normalized to 'Full Year'"""
        assert normalize_period("Full-Year") == "Full Year"

    def test_none_value(self):
        """Test None is normalized to 'Full Year'"""
        assert normalize_period(None) == "Full Year"

    def test_empty_string(self):
        """Test empty string is normalized to 'Full Year'"""
        assert normalize_period("") == "Full Year"

    def test_whitespace_only(self):
        """Test whitespace-only string is normalized to 'Full Year'"""
        assert normalize_period("   ") == "Full Year"

    def test_other_periods_preserved(self):
        """Test that non-full-year periods are preserved"""
        assert normalize_period("spring") == "spring"
        assert normalize_period("fall") == "fall"
        assert normalize_period("10-month") == "10-month"
        assert normalize_period("Spring") == "Spring"
        assert normalize_period("semester-1") == "semester-1"


class TestNormalizePeriodInRecord:
    """Test the normalize_period_in_record function"""

    def test_normalizes_period_field(self):
        """Test that period field is normalized in a record"""
        record = {
            'school_year': '2024-2025',
            'period': 'full-year',
            'salary': 50000
        }
        result = normalize_period_in_record(record)
        assert result['period'] == 'Full Year'
        assert result['school_year'] == '2024-2025'
        assert result['salary'] == 50000

    def test_record_without_period(self):
        """Test that records without period field are unchanged"""
        record = {
            'school_year': '2024-2025',
            'salary': 50000
        }
        result = normalize_period_in_record(record)
        assert 'period' not in result
        assert result['school_year'] == '2024-2025'

    def test_modifies_original_record(self):
        """Test that the function modifies the original record"""
        record = {'period': 'FY', 'salary': 50000}
        result = normalize_period_in_record(record)
        # Should be the same object
        assert result is record
        assert record['period'] == 'Full Year'


class TestNormalizePeriodsInRecords:
    """Test the normalize_periods_in_records function"""

    def test_normalizes_multiple_records(self):
        """Test that all records in a list are normalized"""
        records = [
            {'period': 'full-year', 'salary': 50000},
            {'period': 'FY', 'salary': 55000},
            {'period': 'Full Year', 'salary': 60000},
            {'salary': 65000}  # No period field
        ]
        result = normalize_periods_in_records(records)

        assert len(result) == 4
        assert result[0]['period'] == 'Full Year'
        assert result[1]['period'] == 'Full Year'
        assert result[2]['period'] == 'Full Year'
        assert 'period' not in result[3]

    def test_empty_list(self):
        """Test that empty list returns empty list"""
        assert normalize_periods_in_records([]) == []

    def test_mixed_periods(self):
        """Test that non-full-year periods are preserved"""
        records = [
            {'period': 'full-year', 'salary': 50000},
            {'period': 'spring', 'salary': 55000},
            {'period': 'fall', 'salary': 60000}
        ]
        result = normalize_periods_in_records(records)

        assert result[0]['period'] == 'Full Year'
        assert result[1]['period'] == 'spring'
        assert result[2]['period'] == 'fall'
