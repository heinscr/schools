"""
Lambda handler for salary API endpoints
New single-table design with intelligent fallback matching
"""
import json
import os
import logging
from typing import Dict, Any, Optional, List, Tuple
from decimal import Decimal

import boto3
from boto3.dynamodb.conditions import Key, Attr

# Import shared utilities
from utils.responses import create_response
from utils.dynamodb import get_district_towns as get_district_towns_util
from config import (
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
DISTRICTS_TABLE_NAME = os.environ.get('DISTRICTS_TABLE_NAME')

salaries_table = dynamodb.Table(SALARIES_TABLE_NAME) if SALARIES_TABLE_NAME else None


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


def pad_number(num: int, width: int) -> str:
    """Pad a number with leading zeros"""
    return str(num).zfill(width)


def determine_current_year_period(metadata_items: List[Dict]) -> Tuple[str, str]:
    """
    Determine the most current year/period from metadata

    Logic:
    - Pick the latest year (lexicographically, since format is YYYY-YYYY)
    - Within that year, pick the period that sorts last alphabetically

    Returns: (year, period)
    """
    if not metadata_items:
        # Default to a reasonable fallback
        return "2023-2024", "full-year"

    # Group by year
    from collections import defaultdict
    years_periods = defaultdict(list)

    for item in metadata_items:
        year = item.get('school_year')
        period = item.get('period')
        if year and period:
            years_periods[year].append(period)

    # Get latest year
    latest_year = max(years_periods.keys())

    # Get period that sorts last alphabetically for that year
    periods = years_periods[latest_year]
    latest_period = max(periods)  # Alphabetically last

    return latest_year, latest_period


def get_all_districts() -> Dict[str, str]:
    """
    Get dictionary of all district IDs mapped to their district types
    Returns: Dict[district_id, district_type]
    """
    if not DISTRICTS_TABLE_NAME:
        raise Exception("DISTRICTS_TABLE_NAME not configured")

    districts_table = dynamodb.Table(DISTRICTS_TABLE_NAME)
    district_types_map = {}

    try:
        response = districts_table.scan(
            FilterExpression=Attr('entity_type').eq('district'),
            ProjectionExpression='district_id, district_type'
        )

        for item in response.get('Items', []):
            district_id = item.get('district_id')
            district_type = item.get('district_type', 'unknown')
            district_types_map[district_id] = district_type

        # Handle pagination
        while 'LastEvaluatedKey' in response:
            response = districts_table.scan(
                FilterExpression=Attr('entity_type').eq('district'),
                ProjectionExpression='district_id, district_type',
                ExclusiveStartKey=response['LastEvaluatedKey']
            )
            for item in response.get('Items', []):
                district_id = item.get('district_id')
                district_type = item.get('district_type', 'unknown')
                district_types_map[district_id] = district_type

        return district_types_map

    except Exception as e:
        logger.error(f"Error fetching districts: {str(e)}")
        raise


def find_fallback_salary(district_id: str, year: str, period: str,
                         target_edu: str, target_credits: int, target_step: int) -> Optional[Dict]:
    """
    Find the best matching salary for a district using fallback logic

    Algorithm:
    1. Get all salary entries for district's specific year/period using GSI2
    2. Try to find exact education+credit, use highest step <= target_step
    3. If not found, step down to next lower education+credit combination
    4. Repeat until match found

    Ordering:
    - Education: B < M < D
    - Credits: numerical order (0, 15, 30, 45, 60, ...)
    """
    if not salaries_table:
        return None

    edu_order = {'B': 1, 'M': 2, 'D': 3}

    try:
        # Query GSI2 to get ALL salary entries for this district's year/period
        response = salaries_table.query(
            IndexName='FallbackQueryIndex',
            KeyConditionExpression=Key('GSI2PK').eq(f'YEAR#{year}#PERIOD#{period}#DISTRICT#{district_id}')
        )

        entries = response.get('Items', [])

        if not entries:
            return None

        # Parse and organize entries by education and credits
        from collections import defaultdict
        by_edu_credits = defaultdict(list)

        for entry in entries:
            edu = entry.get('education')
            credits = int(entry.get('credits', 0))
            step = int(entry.get('step', 0))

            by_edu_credits[(edu, credits)].append(entry)

        # Sort steps within each edu+credit combination
        for key in by_edu_credits:
            by_edu_credits[key].sort(key=lambda x: int(x.get('step', 0)), reverse=True)

        # Try exact education first, with decreasing credits
        available_credits = sorted(VALID_CREDITS, reverse=True)

        # Start with target education, then step down
        target_edu_level = edu_order.get(target_edu, 999)
        education_levels = sorted(
            [e for e in ['B', 'M', 'D'] if edu_order.get(e, 0) <= target_edu_level],
            key=lambda e: edu_order.get(e, 0),
            reverse=True
        )

        for edu in education_levels:
            # Try credits from highest to lowest, but only <= target
            for credits in available_credits:
                if credits > target_credits:
                    continue

                if (edu, credits) in by_edu_credits:
                    entries_for_lane = by_edu_credits[(edu, credits)]

                    # Find highest step <= target_step
                    for entry in entries_for_lane:
                        entry_step = int(entry.get('step', 0))
                        if entry_step <= target_step:
                            return entry

                    # If no step <= target, use the highest step available
                    if entries_for_lane:
                        return entries_for_lane[0]

        return None

    except Exception as e:
        logger.error(f"Error in fallback query for district {district_id}: {str(e)}")
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
    if not salaries_table:
        return create_response(503, {'error': 'Salaries table not configured'})

    try:
        # Build key condition
        key_condition = Key('PK').eq(f'DISTRICT#{district_id}')

        # If year specified, filter by year
        if year:
            key_condition = key_condition & Key('SK').begins_with(f'SCHEDULE#{year}')
        else:
            key_condition = key_condition & Key('SK').begins_with('SCHEDULE#')

        response = salaries_table.query(
            KeyConditionExpression=key_condition
        )

        items = response.get('Items', [])

        if not items:
            return create_response(404, {'error': 'Schedule not found'})

        # Group by year/period for cleaner response
        from collections import defaultdict
        schedules = defaultdict(list)

        for item in items:
            year_period = f"{item['school_year']}#{item['period']}"
            schedules[year_period].append({
                'education': item.get('education'),
                'credits': int(item.get('credits', 0)),
                'step': int(item.get('step', 0)),
                'salary': float(item.get('salary', 0))
            })

        # Format response
        result = []
        for year_period, salaries in schedules.items():
            year, period = year_period.split('#', 1)
            result.append({
                'school_year': year,
                'period': period,
                'district_id': district_id,
                'salaries': salaries
            })

        return create_response(200, result)

    except Exception as e:
        logger.error(f"Error querying schedules: {str(e)}", exc_info=True)
        raise


def compare_salaries(params: Dict[str, str]) -> Dict[str, Any]:
    """
    Compare salaries across districts for specific education/credits/step
    GET /api/salary-compare?education=M&credits=30&step=5&districtType=municipal&year=2021-2022&include_fallback=false

    New implementation using single table design with intelligent fallback

    Note: Fallback matching is disabled by default for performance.
    Use include_fallback=true to enable (may be slow with many districts).
    """
    if not salaries_table:
        return create_response(503, {'error': 'Salaries table not configured'})

    # Validate required parameters
    education = validate_education_level(params.get('education'))
    credits = validate_credits(params.get('credits'))
    step = validate_step(params.get('step'))

    district_type = params.get('districtType')
    year_param = params.get('year')  # Optional - if not provided, use current
    include_fallback = params.get('include_fallback', '').lower() == 'true'  # Default: false

    try:
        # STEP 1: Get metadata to get all available year/period combinations
        metadata_response = salaries_table.query(
            KeyConditionExpression=Key('PK').eq('METADATA#SCHEDULES')
        )
        metadata_items = metadata_response.get('Items', [])

        # Get all year/period combinations
        if year_param:
            # Filter to only the specified year
            year_periods = [
                (item.get('school_year'), item.get('period'))
                for item in metadata_items
                if item.get('school_year') == year_param
            ]
            if not year_periods:
                return create_response(404, {'error': f'No data found for year {year_param}'})
        else:
            # Get all year/period combinations
            year_periods = [
                (item.get('school_year'), item.get('period'))
                for item in metadata_items
                if item.get('school_year') and item.get('period')
            ]

        logger.info(f"Querying across {len(year_periods)} year/period combinations")

        # STEP 2: Query GSI1 for exact matches across all year/period combinations
        credits_padded = pad_number(credits, 3)
        step_padded = pad_number(step, 2)

        all_exact_matches = []
        for year, period in year_periods:
            exact_match_response = salaries_table.query(
                IndexName='ExactMatchIndex',
                KeyConditionExpression=Key('GSI1PK').eq(
                    f'YEAR#{year}#PERIOD#{period}#EDU#{education}#CR#{credits_padded}#STEP#{step_padded}'
                )
            )
            all_exact_matches.extend(exact_match_response.get('Items', []))

        # STEP 3: Deduplicate by district - keep only the most recent year/period per district
        district_best_match = {}
        for item in all_exact_matches:
            district_id = item.get('district_id')
            year = item.get('school_year')
            period = item.get('period')

            if district_id not in district_best_match:
                district_best_match[district_id] = item
            else:
                existing = district_best_match[district_id]
                existing_year = existing.get('school_year')
                existing_period = existing.get('period')

                # Keep the more recent: compare (year, period) tuples
                if (year, period) > (existing_year, existing_period):
                    district_best_match[district_id] = item

        exact_matches = list(district_best_match.values())
        exact_district_ids = set(district_best_match.keys())

        logger.info(f"Found {len(exact_district_ids)} districts with exact matches")

        # STEP 4: Get all districts with their types (used for fallback and for adding type to results)
        all_districts_with_types = {}
        district_types_map = {}

        if include_fallback:
            # Get all districts when fallback is enabled
            all_districts_with_types = get_all_districts()
            district_types_map = all_districts_with_types

        # STEP 5: Optionally perform fallback queries (disabled by default for performance)
        fallback_results = []

        if include_fallback:
            missing_district_ids = set(all_districts_with_types.keys()) - exact_district_ids

            logger.info(f"Performing fallback queries for {len(missing_district_ids)} districts")

            # For each missing district, find their most recent year/period and try fallback
            # We need to query each district's data to find their latest year/period
            for district_id in missing_district_ids:
                # Try each year/period in reverse chronological order until we find a match
                best_fallback = None
                for year, period in sorted(year_periods, reverse=True):
                    fallback_entry = find_fallback_salary(
                        district_id, year, period,
                        education, credits, step
                    )
                    if fallback_entry:
                        best_fallback = fallback_entry
                        break  # Use the first (most recent) match found

                if best_fallback:
                    fallback_results.append(best_fallback)

        logger.info(f"Found {len(fallback_results)} districts with fallback matches")

        # STEP 6: Mark exact vs fallback and combine results
        for item in exact_matches:
            item['is_exact_match'] = True

        for item in fallback_results:
            item['is_exact_match'] = False

        all_results = exact_matches + fallback_results

        # Filter by district type if specified
        if district_type:
            # Need to get district types - they're stored in districts table
            # For now, skip this filter or implement it
            pass

        # Sort by salary (descending)
        all_results.sort(key=lambda x: float(x.get('salary', 0)), reverse=True)

        # STEP 7: Fetch towns and district types for all result districts
        result_district_ids = [item.get('district_id') for item in all_results]
        district_towns_map = get_district_towns_util(result_district_ids, DISTRICTS_TABLE_NAME)

        # Fetch district types if not already fetched (when fallback is disabled)
        if not district_types_map and result_district_ids:
            try:
                # Use batch_get_item for efficient bulk retrieval (max 100 items per request)
                # Process in batches of 100
                for i in range(0, len(result_district_ids), 100):
                    batch_ids = result_district_ids[i:i+100]
                    keys = [{'PK': f'DISTRICT#{did}', 'SK': 'METADATA'} for did in batch_ids]

                    response = dynamodb.batch_get_item(
                        RequestItems={
                            DISTRICTS_TABLE_NAME: {
                                'Keys': keys
                            }
                        }
                    )

                    # Process returned items
                    for item in response.get('Responses', {}).get(DISTRICTS_TABLE_NAME, []):
                        district_id = item['PK'].replace('DISTRICT#', '')
                        district_types_map[district_id] = item.get('district_type', 'unknown')

                    # Set unknown for any districts not found in batch
                    for district_id in batch_ids:
                        if district_id not in district_types_map:
                            district_types_map[district_id] = 'unknown'

            except Exception as e:
                logger.error(f"Error fetching district types: {str(e)}")
                # Set unknown for all districts on error
                for district_id in result_district_ids:
                    district_types_map[district_id] = 'unknown'

        # Transform results for response
        rankings = []
        for index, item in enumerate(all_results):
            district_id = item.get('district_id')
            result = {
                'rank': index + 1,
                'district_id': district_id,
                'district_name': item.get('district_name'),
                'district_type': district_types_map.get(district_id, 'unknown'),
                'school_year': item.get('school_year'),
                'period': item.get('period'),
                'education': item.get('education'),
                'credits': int(item.get('credits', 0)),
                'step': int(item.get('step', 0)),
                'salary': float(item.get('salary', 0)),
                'is_exact_match': item.get('is_exact_match', True),
                'towns': district_towns_map.get(district_id, [])
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
                'year': year_param if year_param else 'latest',
                'include_fallback': include_fallback,
                'note': 'Each district uses its own most recent year/period'
            },
            'results': rankings,
            'total': len(rankings),
            'summary': {
                'exact_matches': len(exact_district_ids),
                'fallback_matches': len(fallback_results),
                'fallback_enabled': include_fallback,
                'year_periods_queried': len(year_periods)
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
    # For now, delegate to compare_salaries since it returns similar data
    return compare_salaries(params)


def get_salary_metadata(district_id: str) -> Dict[str, Any]:
    """
    Get salary metadata for a district (available years, salary range)
    GET /api/districts/:id/salary-metadata
    """
    if not salaries_table:
        return create_response(503, {'error': 'Salaries table not configured'})

    try:
        # Query for all schedules for this district
        response = salaries_table.query(
            KeyConditionExpression=Key('PK').eq(f'DISTRICT#{district_id}') & Key('SK').begins_with('SCHEDULE#')
        )

        items = response.get('Items', [])

        if not items:
            return create_response(404, {
                'error': 'No salary data found for district'
            })

        # Extract available years/periods
        from collections import defaultdict
        years_periods = defaultdict(set)
        min_salary = float('inf')
        max_salary = float('-inf')

        for item in items:
            year = item.get('school_year')
            period = item.get('period')
            salary = float(item.get('salary', 0))

            years_periods[year].add(period)
            min_salary = min(min_salary, salary)
            max_salary = max(max_salary, salary)

        # Get district name from first item
        district_name = items[0].get('district_name', district_id)

        # Format schedules list
        schedules = []
        for year in sorted(years_periods.keys()):
            for period in sorted(years_periods[year]):
                schedules.append({
                    'school_year': year,
                    'period': period
                })

        return create_response(200, {
            'district_id': district_id,
            'district_name': district_name,
            'available_years': sorted(list(years_periods.keys())),
            'latest_year': max(years_periods.keys()) if years_periods else None,
            'salary_range': {
                'min': min_salary if min_salary != float('inf') else None,
                'max': max_salary if max_salary != float('-inf') else None
            },
            'schedules': schedules
        })

    except Exception as e:
        logger.error(f"Error getting salary metadata: {str(e)}", exc_info=True)
        raise