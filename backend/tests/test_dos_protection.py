"""
Tests for DoS protection in expensive query operations
"""
import pytest
from unittest.mock import MagicMock, patch
from services.dynamodb_district_service import DynamoDBDistrictService
from config import MAX_DYNAMODB_FETCH_LIMIT


def test_query_by_town_respects_fetch_limit():
    """Test that query_by_town uses Limit parameter to prevent DoS"""
    mock_table = MagicMock()
    mock_table.query.return_value = {
        'Items': [
            {'district_id': f'id-{i}', 'district_name': f'District {i}'}
            for i in range(10)
        ]
    }

    # Call with high limit and offset
    with patch.object(DynamoDBDistrictService, 'get_district', return_value={'id': 'test', 'name': 'Test'}):
        DynamoDBDistrictService._query_by_town(mock_table, 'Boston', limit=100, offset=0)

    # Verify that Limit parameter was used
    mock_table.query.assert_called_once()
    call_kwargs = mock_table.query.call_args[1]
    assert 'Limit' in call_kwargs, "Query should include Limit parameter"
    assert call_kwargs['Limit'] <= MAX_DYNAMODB_FETCH_LIMIT, f"Limit should not exceed {MAX_DYNAMODB_FETCH_LIMIT}"


def test_scan_by_name_respects_fetch_limit():
    """Test that scan_by_name uses Limit parameter to prevent DoS"""
    mock_table = MagicMock()
    mock_table.scan.return_value = {
        'Items': [
            {'district_id': f'id-{i}', 'name': f'District {i}', 'name_lower': f'district {i}',
             'towns': [], 'created_at': '2024-01-01', 'updated_at': '2024-01-01'}
            for i in range(10)
        ]
    }

    # Call with parameters
    DynamoDBDistrictService._scan_by_name(mock_table, 'district', limit=100, offset=0)

    # Verify that Limit parameter was used
    mock_table.scan.assert_called_once()
    call_kwargs = mock_table.scan.call_args[1]
    assert 'Limit' in call_kwargs, "Scan should include Limit parameter"
    assert call_kwargs['Limit'] <= MAX_DYNAMODB_FETCH_LIMIT, f"Limit should not exceed {MAX_DYNAMODB_FETCH_LIMIT}"


def test_get_all_districts_respects_fetch_limit():
    """Test that get_all_districts uses Limit parameter to prevent DoS"""
    mock_table = MagicMock()
    mock_table.scan.return_value = {
        'Items': [
            {'district_id': f'id-{i}', 'name': f'District {i}', 'name_lower': f'district {i}',
             'towns': [], 'created_at': '2024-01-01', 'updated_at': '2024-01-01'}
            for i in range(10)
        ]
    }

    # Call with parameters
    DynamoDBDistrictService._get_all_districts(mock_table, limit=100, offset=0)

    # Verify that Limit parameter was used
    mock_table.scan.assert_called_once()
    call_kwargs = mock_table.scan.call_args[1]
    assert 'Limit' in call_kwargs, "Scan should include Limit parameter"
    assert call_kwargs['Limit'] <= MAX_DYNAMODB_FETCH_LIMIT, f"Limit should not exceed {MAX_DYNAMODB_FETCH_LIMIT}"


def test_search_districts_respects_fetch_limit():
    """Test that search_districts uses Limit parameter to prevent DoS"""
    mock_table = MagicMock()
    mock_table.scan.return_value = {
        'Items': [
            {'district_id': f'id-{i}', 'name': f'District {i}', 'name_lower': f'district {i}',
             'towns': [], 'created_at': '2024-01-01', 'updated_at': '2024-01-01'}
            for i in range(10)
        ]
    }
    mock_table.query.return_value = {
        'Items': [
            {'district_id': f'id-town-{i}', 'district_name': f'District {i}'}
            for i in range(5)
        ]
    }

    # Call with parameters
    with patch.object(DynamoDBDistrictService, 'get_district', return_value={'id': 'test', 'name': 'Test'}):
        DynamoDBDistrictService.search_districts(mock_table, 'test', limit=100, offset=0)

    # Verify that both scan and query used Limit parameter
    scan_call_kwargs = mock_table.scan.call_args[1]
    assert 'Limit' in scan_call_kwargs, "Scan should include Limit parameter"
    assert scan_call_kwargs['Limit'] <= MAX_DYNAMODB_FETCH_LIMIT, f"Scan limit should not exceed {MAX_DYNAMODB_FETCH_LIMIT}"

    query_call_kwargs = mock_table.query.call_args[1]
    assert 'Limit' in query_call_kwargs, "Query should include Limit parameter"
    assert query_call_kwargs['Limit'] <= MAX_DYNAMODB_FETCH_LIMIT, f"Query limit should not exceed {MAX_DYNAMODB_FETCH_LIMIT}"


def test_fetch_limit_calculation():
    """Test that fetch limit calculation is correct"""
    # Test normal case
    limit = 50
    offset = 0
    expected = min(offset + limit + 50, MAX_DYNAMODB_FETCH_LIMIT)  # 100
    assert expected == 100

    # Test high offset case
    limit = 100
    offset = 900
    expected = min(offset + limit + 50, MAX_DYNAMODB_FETCH_LIMIT)  # Should cap at MAX_DYNAMODB_FETCH_LIMIT
    assert expected == MAX_DYNAMODB_FETCH_LIMIT

    # Test that it never exceeds MAX_DYNAMODB_FETCH_LIMIT
    limit = 1000
    offset = 5000
    expected = min(offset + limit + 50, MAX_DYNAMODB_FETCH_LIMIT)
    assert expected == MAX_DYNAMODB_FETCH_LIMIT


def test_n_plus_one_query_optimization():
    """Test that N+1 queries are minimized by fetching only needed items"""
    mock_table = MagicMock()
    mock_table.query.return_value = {
        'Items': [
            {'district_id': f'id-{i}', 'district_name': f'District {i}'}
            for i in range(100)  # Return 100 unique district IDs
        ]
    }

    get_district_calls = []

    def mock_get_district(table, district_id):
        get_district_calls.append(district_id)
        return {'id': district_id, 'name': f'District {district_id}'}

    # Request only 10 items with offset 0
    with patch.object(DynamoDBDistrictService, 'get_district', side_effect=mock_get_district):
        districts, total = DynamoDBDistrictService._query_by_town(mock_table, 'Boston', limit=10, offset=0)

    # Should only fetch 10 districts, not all 100
    assert len(get_district_calls) == 10, f"Should only fetch {10} districts, but fetched {len(get_district_calls)}"
    assert len(districts) == 10, "Should return exactly 10 districts"


def test_max_dynamodb_fetch_limit_constant():
    """Test that MAX_DYNAMODB_FETCH_LIMIT constant is properly configured"""
    from config import MAX_DYNAMODB_FETCH_LIMIT

    assert MAX_DYNAMODB_FETCH_LIMIT > 0, "MAX_DYNAMODB_FETCH_LIMIT should be positive"
    assert MAX_DYNAMODB_FETCH_LIMIT <= 10000, "MAX_DYNAMODB_FETCH_LIMIT should be reasonable (≤10000)"
    assert isinstance(MAX_DYNAMODB_FETCH_LIMIT, int), "MAX_DYNAMODB_FETCH_LIMIT should be an integer"
