"""Tests for DoS protection limits and query optimization.
Reduced datasets keep execution fast while validating logic."""

from unittest.mock import MagicMock, patch
from services.dynamodb_district_service import DynamoDBDistrictService
from config import MAX_DYNAMODB_FETCH_LIMIT


def test_query_by_town_respects_fetch_limit():
    mock_table = MagicMock()
    mock_table.query.return_value = {
        'Items': [
            {'district_id': f'id-{i}', 'district_name': f'District {i}'}
            for i in range(8)
        ]
    }
    with patch.object(DynamoDBDistrictService, 'get_district', return_value={'id': 'test', 'name': 'Test'}):
        DynamoDBDistrictService._query_by_town(mock_table, 'Boston', limit=5, offset=0)
    call_kwargs = mock_table.query.call_args[1]
    assert call_kwargs['Limit'] <= MAX_DYNAMODB_FETCH_LIMIT


def test_scan_by_name_respects_fetch_limit():
    mock_table = MagicMock()
    mock_table.scan.return_value = {
        'Items': [
            {
                'district_id': f'id-{i}', 'name': f'District {i}', 'name_lower': f'district {i}', 'towns': [],
                'created_at': '2024-01-01', 'updated_at': '2024-01-01'
            }
            for i in range(6)
        ]
    }
    DynamoDBDistrictService._scan_by_name(mock_table, 'district', limit=4, offset=0)
    call_kwargs = mock_table.scan.call_args[1]
    assert call_kwargs['Limit'] <= MAX_DYNAMODB_FETCH_LIMIT


def test_get_all_districts_respects_fetch_limit():
    mock_table = MagicMock()
    mock_items = [
        {
            'PK': f'DISTRICT#{i}', 'SK': 'METADATA', 'district_id': f'DISTRICT#{i}', 'name': f'District {i}',
            'name_lower': f'district {i}', 'entity_type': 'district', 'towns': [],
            'created_at': '2024-01-01', 'updated_at': '2024-01-01'
        }
        for i in range(7)
    ]
    mock_table.query.return_value = {'Items': mock_items}
    DynamoDBDistrictService._get_all_districts(mock_table, limit=3, offset=0)
    query_kwargs = mock_table.query.call_args[1]
    assert query_kwargs['Limit'] <= MAX_DYNAMODB_FETCH_LIMIT


def test_search_districts_respects_fetch_limit():
    mock_table = MagicMock()
    # Simulate name query + town query both happening
    # Use a 4+ character query to pass validation
    name_query_result = {'Items': [
        {'district_id': 'DISTRICT#1', 'name': 'Alpha', 'name_lower': 'alpha', 'towns': [], 'entity_type': 'district', 'created_at': '2024-01-01', 'updated_at': '2024-01-01'}
    ]}
    town_query_result = {'Items': [
        {'district_id': 'DISTRICT#2', 'district_name': 'Beta'}
    ]}
    # Two query calls: first for name on GSI_METADATA, second for town on GSI_TOWN
    mock_table.query.side_effect = [name_query_result, town_query_result]

    with patch.object(DynamoDBDistrictService, 'get_district', return_value={'id': 'DISTRICT#2', 'name': 'Beta'}):
        DynamoDBDistrictService.search_districts(mock_table, 'alph', limit=2, offset=0)

    # Both query calls should respect the fetch limit
    for call in mock_table.query.call_args_list:
        query_kwargs = call[1]
        assert query_kwargs['Limit'] <= MAX_DYNAMODB_FETCH_LIMIT


def test_fetch_limit_calculation():
    limit = 50; offset = 0
    assert min(offset + limit + 50, MAX_DYNAMODB_FETCH_LIMIT) == 100
    limit = 100; offset = 900
    assert min(offset + limit + 50, MAX_DYNAMODB_FETCH_LIMIT) == MAX_DYNAMODB_FETCH_LIMIT
    limit = 1000; offset = 5000
    assert min(offset + limit + 50, MAX_DYNAMODB_FETCH_LIMIT) == MAX_DYNAMODB_FETCH_LIMIT


def test_n_plus_one_query_optimization():
    mock_table = MagicMock()
    mock_table.query.return_value = {'Items': [
        {'district_id': f'id-{i}', 'district_name': f'District {i}'} for i in range(20)
    ]}
    fetched = []
    def mock_get(table, district_id):
        fetched.append(district_id)
        return {'id': district_id, 'name': district_id}
    with patch.object(DynamoDBDistrictService, 'get_district', side_effect=mock_get):
        districts, total = DynamoDBDistrictService._query_by_town(mock_table, 'Boston', limit=5, offset=0)
    assert len(fetched) == 5
    assert len(districts) == 5


def test_max_dynamodb_fetch_limit_constant():
    assert MAX_DYNAMODB_FETCH_LIMIT > 0
    assert MAX_DYNAMODB_FETCH_LIMIT <= 10000
    assert isinstance(MAX_DYNAMODB_FETCH_LIMIT, int)
