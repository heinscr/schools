"""
Lambda handler for salary API endpoints
Provides salary schedule queries, comparisons, heatmaps, and metadata
"""
import json
import os
import logging
from typing import Dict, Any, Optional, List

import boto3
from boto3.dynamodb.conditions import Key

# Import shared utilities
from utils.responses import create_response
from utils.dynamodb import get_district_towns as get_district_towns_util
from config import (
    COMPARE_INDEX_NAME,
    VALID_EDUCATION_LEVELS,
    VALID_CREDITS,
    MIN_STEP,
    MAX_STEP
)

# Configure logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Initialize DynamoDB client
dynamodb = boto3.resource('dynamodb')

SALARIES_TABLE_NAME = os.environ.get('SALARIES_TABLE_NAME')
SCHEDULES_TABLE_NAME = os.environ.get('SCHEDULES_TABLE_NAME')
DISTRICTS_TABLE_NAME = os.environ.get('DISTRICTS_TABLE_NAME')

salaries_table = dynamodb.Table(SALARIES_TABLE_NAME) if SALARIES_TABLE_NAME else None
schedules_table = dynamodb.Table(SCHEDULES_TABLE_NAME) if SCHEDULES_TABLE_NAME else None


def validate_education_level(education: Optional[str]) -> str:
    """Validate and normalize education level"""
    if not education:
        raise ValueError("Education level is required")
    
    education = education.upper().strip()
    if education not in VALID_EDUCATION_LEVELS:
        raise ValueError(f"Invalid education level '{education}'. Must be one of: {', '.join(sorted(VALID_EDUCATION_LEVELS))}")
    return education


def validate_credits(credits: Optional[str]) -> int:
    """Validate credits parameter"""
    if credits is None:
        raise ValueError("Credits parameter is required")
    
    try:
        credits_int = int(credits)
    except (ValueError, TypeError):
        raise ValueError(f"Invalid credits '{credits}'. Must be an integer")
    
    if credits_int not in VALID_CREDITS:
        raise ValueError(f"Invalid credits {credits_int}. Must be one of: {', '.join(map(str, sorted(VALID_CREDITS)))}")
    return credits_int


def validate_step(step: Optional[str]) -> int:
    """Validate step parameter"""
    if not step:
        raise ValueError("Step parameter is required")
    
    try:
        step_int = int(step)
    except (ValueError, TypeError):
        raise ValueError(f"Invalid step '{step}'. Must be an integer")
    
    if not (MIN_STEP <= step_int <= MAX_STEP):
        raise ValueError(f"Invalid step {step_int}. Must be between {MIN_STEP} and {MAX_STEP}")
    return step_int


def handler(event, context):
    """
    Main Lambda handler for salary API routes
    """
    logger.info("Processing Lambda request", extra={"path": event.get('path'), "method": event.get('httpMethod')})
    
    # Extract path and method (supports both REST and HTTP API formats)
    path = event.get('path') or event.get('rawPath', '')
    method = event.get('httpMethod') or event.get('requestContext', {}).get('http', {}).get('method', '')
    query_params = event.get('queryStringParameters') or {}
    
    # Handle OPTIONS preflight requests
    if method == 'OPTIONS':
        return create_response(200, {})
    
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
        
    except ValueError as e:
        logger.warning(f"Validation error: {str(e)}")
        return create_response(400, {'error': str(e)})
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}", exc_info=True)
        return create_response(500, {'error': 'Internal server error'})


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
        logger.error(f"Error querying schedules: {str(e)}", exc_info=True)
        raise


def compare_salaries(params: Dict[str, str]) -> Dict[str, Any]:
    """
    Compare salaries across districts for specific education/credits/step
    GET /api/salary-compare?education=M&credits=30&step=5&districtType=municipal&year=2021-2022
    """
    if not salaries_table:
        return create_response(503, {'error': 'Salaries table not configured'})
    
    # Validate required parameters
    education = validate_education_level(params.get('education'))
    credits = validate_credits(params.get('credits'))
    step = validate_step(params.get('step'))
    
    district_type = params.get('districtType')
    year = params.get('year')  # No default - show all years unless specified
    
    try:
        # Query using GSI2 (CompareDistrictsIndex)
        query_params = {
            'IndexName': COMPARE_INDEX_NAME,
            'KeyConditionExpression': Key('GSI2PK').eq(f'COMPARE#{education}#{credits}#{step}'),
            'ScanIndexForward': False  # Descending order by salary
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
        
        # Batch fetch towns for all districts
        district_ids = [item.get('district_id') for item in deduplicated_items]
        district_towns_map = get_district_towns_util(district_ids, DISTRICTS_TABLE_NAME)
        
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
                'salary': item.get('salary'),
                'towns': district_towns_map.get(item.get('district_id'), [])
            }
            for index, item in enumerate(deduplicated_items)
        ]
        
        return create_response(200, {
            'query': {
                'education': education,
                'credits': credits,
                'step': step,
                'districtType': district_type,
                'year': year
            },
            'results': rankings,
            'total': len(rankings)
        })
        
    except ValueError:
        # Re-raise validation errors to be caught by handler
        raise
    except Exception as e:
        logger.error(f"Error comparing salaries: {str(e)}", exc_info=True)
        raise


def get_salary_heatmap(params: Dict[str, str]) -> Dict[str, Any]:
    """
    Get all districts' salaries for a specific education/credits/step (for heatmap)
    GET /api/salary-heatmap?education=M&credits=30&step=5&year=2021-2022
    """
    if not salaries_table:
        return create_response(503, {'error': 'Salaries table not configured'})
    
    # Validate required parameters
    education = validate_education_level(params.get('education'))
    credits = validate_credits(params.get('credits'))
    step = validate_step(params.get('step'))
    year = params.get('year', '2021-2022')
    
    try:
        # Query using GSI2 to get all districts
        query_params = {
            'IndexName': COMPARE_INDEX_NAME,
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
                'credits': credits,
                'step': step,
                'year': year
            },
            'statistics': stats,
            'data': heatmap_data
        })
        
    except ValueError:
        # Re-raise validation errors to be caught by handler
        raise
    except Exception as e:
        logger.error(f"Error getting salary heatmap: {str(e)}", exc_info=True)
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
