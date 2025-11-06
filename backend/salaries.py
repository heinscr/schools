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


def find_best_salary_match(schedule: Dict, target_edu: str, target_credits: int, target_step: int) -> Optional[Dict]:
    """
    Fallback matching using per-credit max step tracking.

    Structure:
    max_by_education = {
        "M": {
            "0": 9,   // M+0 has max step 9
            "30": 10, // M+30 has max step 10
            "60": 5   // M+60 has max step 5
        }
    }

    Algorithm:
    1. Find highest available education <= target (can step down: B < M < D)
    2. Get credit map for that education
    3. Find highest credit <= target_credits
    4. Get max step for that education+credit combination
    5. Use actual_step = min(max_step, target_step)
    6. Return the salary at that education/credit/step

    Example: Query M+45@step12, schedule has M+0@step15, M+30@step10, M+60@step5
    -> Use M (exact match)
    -> Highest credit <= 45 is 30
    -> Max step at M+30 is 10
    -> Use min(10, 12) = 10
    -> Return salary at M+30@step10
    """
    edu_order = {'B': 1, 'M': 2, 'D': 3}
    max_by_education = schedule.get('max_by_education', {})

    if not max_by_education:
        return None

    # Find highest available education <= target
    available_educations = sorted(
        max_by_education.keys(),
        key=lambda e: edu_order.get(e, 0),
        reverse=True  # Sort descending (D, M, B)
    )

    actual_education = None
    for edu in available_educations:
        if edu_order.get(edu, 0) <= edu_order.get(target_edu, 999):
            actual_education = edu
            break

    if not actual_education:
        return None

    # Get credit map for this education level
    credit_map = max_by_education[actual_education]

    # Find highest credit <= target_credits
    # Credits are stored as strings in the map
    available_credits = sorted(
        [int(c) for c in credit_map.keys()],
        reverse=True
    )

    actual_credit = None
    for credit in available_credits:
        if credit <= target_credits:
            actual_credit = credit
            break

    if actual_credit is None:
        return None

    # Get max step for this education+credit
    max_step_at_credit = credit_map[str(actual_credit)]
    actual_step = min(max_step_at_credit, target_step)

    # Find the matching salary entry
    for salary_entry in schedule.get('salaries', []):
        if (salary_entry['education'] == actual_education and
            salary_entry['credits'] == actual_credit and
            salary_entry['step'] == actual_step):
            return salary_entry

    return None


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

    Returns all districts with either exact matches OR fallback matches (highest available salary
    where education/credits/step are all <= queried values).
    """
    if not salaries_table:
        return create_response(503, {'error': 'Salaries table not configured'})

    if not schedules_table:
        return create_response(503, {'error': 'Schedules table not configured'})

    # Validate required parameters
    education = validate_education_level(params.get('education'))
    credits = validate_credits(params.get('credits'))
    step = validate_step(params.get('step'))

    district_type = params.get('districtType')
    year = params.get('year')  # No default - show all years unless specified

    try:
        # STEP 1: Query using GSI2 to get exact matches
        query_params = {
            'IndexName': COMPARE_INDEX_NAME,
            'KeyConditionExpression': Key('GSI2PK').eq(f'COMPARE#{education}#{credits}#{step}'),
            'ScanIndexForward': False  # Descending order by salary
        }

        # Build filter expression for exact matches
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
        exact_match_items = response.get('Items', [])

        # Deduplicate exact matches: keep only the most recent data per district
        exact_district_map = {}
        for item in exact_match_items:
            district_id = item.get('district_id')
            school_year = item.get('school_year', '')
            period = item.get('period', '')

            if district_id not in exact_district_map:
                exact_district_map[district_id] = item
            else:
                existing = exact_district_map[district_id]
                existing_year = existing.get('school_year', '')
                existing_period = existing.get('period', '')

                # Compare (year, period) tuples - larger is more recent
                if (school_year, period) > (existing_year, existing_period):
                    exact_district_map[district_id] = item

        exact_district_ids = set(exact_district_map.keys())
        logger.info(f"Found {len(exact_district_ids)} districts with exact matches")

        # STEP 2: Query schedules table to find districts that need fallback
        # Build query for schedules table
        schedules_query_params = {}

        if district_type and year:
            # Use GSI to filter by type and year
            schedules_query_params = {
                'IndexName': 'ByDistrictTypeIndex',
                'KeyConditionExpression': Key('district_type').eq(district_type) & Key('school_year').eq(year)
            }
            schedules_response = schedules_table.query(**schedules_query_params)
        elif district_type:
            # Filter by type only (scan with filter)
            schedules_response = schedules_table.scan(
                FilterExpression=Key('district_type').eq(district_type)
            )
        elif year:
            # Filter by year only (scan with filter)
            schedules_response = schedules_table.scan(
                FilterExpression=Key('school_year').eq(year)
            )
        else:
            # Get all schedules
            schedules_response = schedules_table.scan()

        all_schedules = schedules_response.get('Items', [])
        logger.info(f"Found {len(all_schedules)} total schedules")

        # Deduplicate schedules: keep only the most recent per district
        schedule_map = {}
        for schedule in all_schedules:
            district_id = schedule.get('district_id')
            school_year = schedule.get('school_year', '')
            period = schedule.get('period', '')

            if district_id not in schedule_map:
                schedule_map[district_id] = schedule
            else:
                existing = schedule_map[district_id]
                existing_year = existing.get('school_year', '')
                existing_period = existing.get('period', '')

                if (school_year, period) > (existing_year, existing_period):
                    schedule_map[district_id] = schedule

        # STEP 3: Process fallback matches for districts without exact matches
        fallback_items = []
        for district_id, schedule in schedule_map.items():
            if district_id in exact_district_ids:
                continue  # Already have exact match

            # Find best matching salary using simplified metadata
            best_match = find_best_salary_match(schedule, education, credits, step)

            if best_match:
                fallback_items.append({
                    'district_id': district_id,
                    'district_name': schedule.get('district_name'),
                    'district_type': schedule.get('district_type'),
                    'school_year': schedule.get('school_year'),
                    'period': schedule.get('period'),
                    'education': best_match.get('education'),
                    'credits': best_match.get('credits'),
                    'step': best_match.get('step'),
                    'salary': best_match.get('salary'),
                    'is_exact_match': False
                })

        logger.info(f"Found {len(fallback_items)} districts with fallback matches")

        # STEP 4: Combine exact and fallback results
        # Mark exact matches
        for item in exact_district_map.values():
            item['is_exact_match'] = True

        all_results = list(exact_district_map.values()) + fallback_items

        # Sort by salary (descending)
        all_results.sort(key=lambda x: float(x.get('salary', 0)), reverse=True)

        # STEP 5: Batch fetch towns for all districts
        all_district_ids = [item.get('district_id') for item in all_results]
        district_towns_map = get_district_towns_util(all_district_ids, DISTRICTS_TABLE_NAME)

        # Transform results for response
        rankings = []
        for index, item in enumerate(all_results):
            result = {
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
                'is_exact_match': item.get('is_exact_match', True),
                'towns': district_towns_map.get(item.get('district_id'), [])
            }

            # Add queried_for field for fallback matches
            if not item.get('is_exact_match', True):
                result['queried_for'] = {
                    'education': education,
                    'credits': credits,
                    'step': step
                }

            rankings.append(result)

        return create_response(200, {
            'query': {
                'education': education,
                'credits': credits,
                'step': step,
                'districtType': district_type,
                'year': year
            },
            'results': rankings,
            'total': len(rankings),
            'summary': {
                'exact_matches': len(exact_district_ids),
                'fallback_matches': len(fallback_items)
            }
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
        logging.error(f"Error getting salary metadata: {str(e)}", exc_info=True)
        raise