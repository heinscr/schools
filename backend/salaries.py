"""
Lambda handler for salary API endpoints
Provides salary schedule queries, comparisons, heatmaps, and metadata
"""
import json
import os
from typing import Dict, Any, Optional, List
from decimal import Decimal

import boto3
from boto3.dynamodb.conditions import Key

# Initialize DynamoDB client
dynamodb = boto3.resource('dynamodb')

SALARIES_TABLE_NAME = os.environ.get('SALARIES_TABLE_NAME')
SCHEDULES_TABLE_NAME = os.environ.get('SCHEDULES_TABLE_NAME')

salaries_table = dynamodb.Table(SALARIES_TABLE_NAME) if SALARIES_TABLE_NAME else None
schedules_table = dynamodb.Table(SCHEDULES_TABLE_NAME) if SCHEDULES_TABLE_NAME else None


def decimal_to_float(obj):
    """Convert Decimal objects to float for JSON serialization"""
    if isinstance(obj, Decimal):
        return float(obj)
    raise TypeError


def create_response(status_code: int, body: Any) -> Dict[str, Any]:
    """Create a standardized API response"""
    return {
        'statusCode': status_code,
        'headers': {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Methods': 'GET, OPTIONS',
            'Access-Control-Allow-Headers': 'Content-Type'
        },
        'body': json.dumps(body, default=decimal_to_float)
    }


def handler(event, context):
    """
    Main Lambda handler for salary API routes
    """
    print(f"Event: {json.dumps(event)}")
    
    # Extract path and method (supports both REST and HTTP API formats)
    path = event.get('path') or event.get('rawPath', '')
    method = event.get('httpMethod') or event.get('requestContext', {}).get('http', {}).get('method', '')
    query_params = event.get('queryStringParameters') or {}
    
    try:
        # Route: GET /api/salary-schedule/{districtId}/{year?}
        if method == 'GET' and '/api/salary-schedule/' in path:
            path_parts = path.split('/')
            if len(path_parts) >= 4:
                district_id = path_parts[3]
                year = path_parts[4] if len(path_parts) > 4 else None
                return get_salary_schedule(district_id, year)
        
        # Route: GET /api/salary-compare
        if method == 'GET' and path == '/api/salary-compare':
            return compare_salaries(query_params)
        
        # Route: GET /api/salary-heatmap
        if method == 'GET' and path == '/api/salary-heatmap':
            return get_salary_heatmap(query_params)
        
        # Route: GET /api/districts/{id}/salary-metadata
        if method == 'GET' and '/api/districts/' in path and path.endswith('/salary-metadata'):
            path_parts = path.split('/')
            if len(path_parts) >= 4:
                district_id = path_parts[3]
                return get_salary_metadata(district_id)
        
        return create_response(404, {'error': 'Not found'})
        
    except Exception as e:
        print(f"Error: {str(e)}")
        import traceback
        traceback.print_exc()
        return create_response(500, {'error': str(e)})


def get_salary_schedule(district_id: str, year: Optional[str] = None) -> Dict[str, Any]:
    """
    Get salary schedule(s) for a district
    GET /api/salary-schedule/:districtId/:year?
    """
    if not schedules_table:
        return create_response(503, {'error': 'Schedules table not configured'})
    
    try:
        # Build key condition
        key_condition = Key('district_id').eq(district_id)
        
        # If year specified, filter by year
        if year:
            key_condition = key_condition & Key('schedule_key').begins_with(year)
        
        response = schedules_table.query(
            KeyConditionExpression=key_condition
        )
        
        items = response.get('Items', [])
        
        if not items:
            return create_response(404, {'error': 'Schedule not found'})
        
        return create_response(200, items)
        
    except Exception as e:
        print(f"Error querying schedules: {str(e)}")
        raise


def compare_salaries(params: Dict[str, str]) -> Dict[str, Any]:
    """
    Compare salaries across districts for specific education/credits/step
    GET /api/salary-compare?education=M&credits=30&step=5&districtType=municipal&limit=10&year=2021-2022
    """
    if not salaries_table:
        return create_response(503, {'error': 'Salaries table not configured'})
    
    education = params.get('education')
    credits = params.get('credits')
    step = params.get('step')
    district_type = params.get('districtType')
    limit = int(params.get('limit', 10))
    year = params.get('year', '2021-2022')
    
    if not education or credits is None or not step:
        return create_response(400, {
            'error': 'Missing required parameters: education, credits, step'
        })
    
    try:
        # Query using GSI2 (CompareDistrictsIndex)
        query_params = {
            'IndexName': 'CompareDistrictsIndex',
            'KeyConditionExpression': Key('GSI2PK').eq(f'COMPARE#{education}#{credits}#{step}'),
            'ScanIndexForward': False,  # Descending order by salary
            'Limit': limit
        }
        
        # Build filter expression
        filter_parts = []
        expression_values = {}
        
        if year:
            filter_parts.append('school_year = :year')
            expression_values[':year'] = year
        
        if district_type:
            filter_parts.append('district_type = :dtype')
            expression_values[':dtype'] = district_type
        
        if filter_parts:
            query_params['FilterExpression'] = ' AND '.join(filter_parts)
            query_params['ExpressionAttributeValues'] = expression_values
        
        response = salaries_table.query(**query_params)
        items = response.get('Items', [])
        
        # Deduplicate districts: keep only the most recent data per district
        # (largest school_year, then largest period by ASCII sort)
        district_map = {}
        for item in items:
            district_id = item.get('district_id')
            school_year = item.get('school_year', '')
            period = item.get('period', '')
            
            if district_id not in district_map:
                district_map[district_id] = item
            else:
                existing = district_map[district_id]
                existing_year = existing.get('school_year', '')
                existing_period = existing.get('period', '')
                
                # Compare (year, period) tuples - larger is more recent
                if (school_year, period) > (existing_year, existing_period):
                    district_map[district_id] = item
        
        # Convert to list and sort by salary (descending)
        deduplicated_items = sorted(
            district_map.values(),
            key=lambda x: float(x.get('salary', 0)),
            reverse=True
        )
        
        # Transform results for response
        rankings = [
            {
                'rank': index + 1,
                'district_id': item.get('district_id'),
                'district_name': item.get('district_name'),
                'district_type': item.get('district_type'),
                'school_year': item.get('school_year'),
                'period': item.get('period'),
                'education': item.get('education'),
                'credits': item.get('credits'),
                'step': item.get('step'),
                'salary': item.get('salary')
            }
            for index, item in enumerate(deduplicated_items)
        ]
        
        return create_response(200, {
            'query': {
                'education': education,
                'credits': int(credits),
                'step': int(step),
                'districtType': district_type,
                'year': year
            },
            'results': rankings,
            'total': len(rankings)
        })
        
    except Exception as e:
        print(f"Error comparing salaries: {str(e)}")
        raise


def get_salary_heatmap(params: Dict[str, str]) -> Dict[str, Any]:
    """
    Get all districts' salaries for a specific education/credits/step (for heatmap)
    GET /api/salary-heatmap?education=M&credits=30&step=5&year=2021-2022
    """
    if not salaries_table:
        return create_response(503, {'error': 'Salaries table not configured'})
    
    education = params.get('education')
    credits = params.get('credits')
    step = params.get('step')
    year = params.get('year', '2021-2022')
    
    if not education or credits is None or not step:
        return create_response(400, {
            'error': 'Missing required parameters: education, credits, step'
        })
    
    try:
        # Query using GSI2 to get all districts
        query_params = {
            'IndexName': 'CompareDistrictsIndex',
            'KeyConditionExpression': Key('GSI2PK').eq(f'COMPARE#{education}#{credits}#{step}')
        }
        
        # Filter by year if specified
        if year:
            query_params['FilterExpression'] = Key('school_year').eq(year)
        
        response = salaries_table.query(**query_params)
        items = response.get('Items', [])
        
        # Transform for heatmap display
        heatmap_data = [
            {
                'district_id': item.get('district_id'),
                'district_name': item.get('district_name'),
                'district_type': item.get('district_type'),
                'salary': float(item.get('salary', 0))
            }
            for item in items
        ]
        
        # Calculate statistics
        if heatmap_data:
            salaries = [d['salary'] for d in heatmap_data]
            salaries_sorted = sorted(salaries)
            
            stats = {
                'min': min(salaries),
                'max': max(salaries),
                'avg': sum(salaries) / len(salaries),
                'median': salaries_sorted[len(salaries_sorted) // 2]
            }
        else:
            stats = {
                'min': None,
                'max': None,
                'avg': None,
                'median': None
            }
        
        return create_response(200, {
            'query': {
                'education': education,
                'credits': int(credits),
                'step': int(step),
                'year': year
            },
            'statistics': stats,
            'data': heatmap_data
        })
        
    except Exception as e:
        print(f"Error getting salary heatmap: {str(e)}")
        raise


def get_salary_metadata(district_id: str) -> Dict[str, Any]:
    """
    Get salary metadata for a district (available years, salary range)
    GET /api/districts/:id/salary-metadata
    """
    if not schedules_table:
        return create_response(503, {'error': 'Schedules table not configured'})
    
    try:
        # Query schedules table to get all available schedules
        response = schedules_table.query(
            KeyConditionExpression=Key('district_id').eq(district_id)
        )
        
        items = response.get('Items', [])
        
        if not items:
            return create_response(404, {
                'error': 'No salary data found for district'
            })
        
        # Extract available years and calculate ranges
        years = sorted(list(set(item.get('school_year') for item in items)))
        latest_schedule = max(items, key=lambda x: x.get('school_year', ''))
        
        # Calculate salary range from latest schedule
        min_salary = float('inf')
        max_salary = float('-inf')
        
        if 'salaries' in latest_schedule:
            for salary_entry in latest_schedule['salaries']:
                salary = float(salary_entry.get('salary', 0))
                min_salary = min(min_salary, salary)
                max_salary = max(max_salary, salary)
        
        return create_response(200, {
            'district_id': district_id,
            'district_name': latest_schedule.get('district_name'),
            'available_years': years,
            'latest_year': years[-1] if years else None,
            'salary_range': {
                'min': min_salary if min_salary != float('inf') else None,
                'max': max_salary if max_salary != float('-inf') else None
            },
            'schedules': [
                {
                    'school_year': item.get('school_year'),
                    'period': item.get('period'),
                    'contract_term': item.get('contract_term'),
                    'contract_expiration': item.get('contract_expiration')
                }
                for item in items
            ]
        })
        
    except Exception as e:
        print(f"Error getting salary metadata: {str(e)}")
        raise
