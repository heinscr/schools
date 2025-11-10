"""
Salary service - Business logic for salary operations
Single-table DynamoDB design with intelligent fallback matching
"""
import logging
from typing import Dict, Any, Optional, List, Tuple
from decimal import Decimal

import boto3
from boto3.dynamodb.conditions import Key, Attr

from config import (
    VALID_EDUCATION_LEVELS,
    VALID_CREDITS,
    MIN_STEP,
    MAX_STEP
)

# Configure logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


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


def get_salary_schedule_for_district(
    table,
    district_id: str,
    year: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Get salary schedule(s) for a district

    Args:
        table: DynamoDB table resource
        district_id: District ID
        year: Optional school year filter (e.g. "2023-2024")

    Returns:
        List of salary schedule objects grouped by year/period
    """
    if not table:
        raise Exception('DynamoDB table not configured')

    # Build key condition
    key_condition = Key('PK').eq(f'DISTRICT#{district_id}')

    # If year specified, filter by year
    if year:
        key_condition = key_condition & Key('SK').begins_with(f'SCHEDULE#{year}')
    else:
        key_condition = key_condition & Key('SK').begins_with('SCHEDULE#')

    response = table.query(KeyConditionExpression=key_condition)
    items = response.get('Items', [])

    if not items:
        return []

    # Group by year/period for cleaner response
    from collections import defaultdict
    schedules = defaultdict(list)

    for item in items:
        year_period = f"{item['school_year']}#{item['period']}"
        schedules[year_period].append({
            'education': item.get('education'),
            'is_calculated': item.get('is_calculated', False),
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

    return result


def get_global_salary_metadata(table) -> Dict[str, Any]:
    """
    Return global salary metadata stored at PK=METADATA#MAXVALUES SK=GLOBAL
    Returns dict with keys: max_step (int) and edu_credit_combos (list of strings like 'M+30')
    """
    if not table:
        raise Exception('DynamoDB table not configured')

    resp = table.get_item(Key={'PK': 'METADATA#MAXVALUES', 'SK': 'GLOBAL'})
    if 'Item' not in resp:
        raise Exception('METADATA#MAXVALUES not found. Run load_salary_data.py first.')

    item = resp['Item']
    # Defensive conversions
    max_step = int(item.get('max_step', 15))
    edu_credit_combos = item.get('edu_credit_combos', []) or []

    return {
        'max_step': max_step,
        'edu_credit_combos': edu_credit_combos
    }


def compare_salaries_across_districts(
    table,
    education: str,
    credits: int,
    step: int,
    district_type: Optional[str] = None,
    year_param: Optional[str] = None,
    include_fallback: bool = False
) -> Dict[str, Any]:
    """
    Compare salaries across districts for specific education/credits/step

    Args:
        table: DynamoDB table resource
        education: Education level (B, M, D)
        credits: Additional credits (0, 15, 30, 45, 60)
        step: Experience step (1-15)
        district_type: Optional district type filter
        year_param: Optional year filter
        include_fallback: Enable cross-education fallback matching

    Returns:
        Dictionary with query info, results, and summary statistics
    """
    if not table:
        raise Exception('DynamoDB table not configured')

    # Validate parameters
    education = validate_education_level(education)
    credits = validate_credits(str(credits))
    step = validate_step(str(step))

    # STEP 1: Get metadata to get all available year/period combinations
    metadata_response = table.query(
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
            raise ValueError(f'No data found for year {year_param}')
    else:
        # Get all year/period combinations
        year_periods = [
            (item.get('school_year'), item.get('period'))
            for item in metadata_items
            if item.get('school_year') and item.get('period')
        ]

    logger.info(f"Querying across {len(year_periods)} year/period combinations")

    # STEP 2: Get global metadata to determine what edu+credit combos exist after normalization
    max_values_response = table.get_item(
        Key={'PK': 'METADATA#MAXVALUES', 'SK': 'GLOBAL'}
    )

    if 'Item' not in max_values_response:
        raise Exception('METADATA#MAXVALUES not found. Run load_salary_data.py first.')

    max_values = max_values_response['Item']
    max_step_global = int(max_values.get('max_step', 15))
    edu_credit_combos = max_values.get('edu_credit_combos', [])

    logger.info(f"Global max_step: {max_step_global}, edu_credit_combos: {edu_credit_combos}")

    # STEP 3: Determine best fallback combo from global list
    edu_order = {'D': 3, 'M': 2, 'B': 1}
    target_edu_level = edu_order.get(education, 0)
    target_key = f'{education}+{credits}'

    # Find best combo to query
    query_edu = education
    query_cred = credits
    is_exact_match = False

    logger.info(f"Looking for {target_key} in global combos")

    # Check if exact combo exists globally
    if target_key in edu_credit_combos:
        is_exact_match = True
        logger.info(f"Exact match found: {target_key}")
    elif include_fallback:
        logger.info(f"Exact match not found, finding fallback for {target_key}")
        # Find best fallback from global combos
        best_combo = None
        best_combo_edu = None
        best_combo_cred = None

        for combo in edu_credit_combos:
            parts = combo.split('+')
            if len(parts) != 2:
                continue
            combo_edu = parts[0]
            combo_cred = int(parts[1])
            combo_edu_level = edu_order.get(combo_edu, 0)

            # Skip if education is higher than target
            if combo_edu_level > target_edu_level:
                continue

            # For same education level, only use credits <= target
            # For lower education level, allow any credits
            if combo_edu == education and combo_cred > credits:
                continue

            # Check if this is better than current best
            if best_combo is None:
                best_combo = combo
                best_combo_edu = combo_edu
                best_combo_cred = combo_cred
            else:
                # Compare: prefer higher edu, then higher credit
                if combo_edu_level > edu_order.get(best_combo_edu, 0):
                    best_combo = combo
                    best_combo_edu = combo_edu
                    best_combo_cred = combo_cred
                elif combo_edu == best_combo_edu and combo_cred > best_combo_cred:
                    best_combo = combo
                    best_combo_edu = combo_edu
                    best_combo_cred = combo_cred

        if best_combo:
            query_edu = best_combo_edu
            query_cred = best_combo_cred
            logger.info(f"Fallback found: {best_combo} (will query for {query_edu}+{query_cred})")
        else:
            # No valid fallback found
            logger.error(f"No valid fallback found for {target_key}")
            raise ValueError(f'No data available for {education}+{credits} and no valid fallback found')
    else:
        # Exact match required but not found
        logger.error(f"Exact match required but {target_key} not in global combos")
        raise ValueError(f'No data available for {education}+{credits} (fallback disabled)')

    logger.info(f"Querying for {query_edu}+{query_cred} step {step} across {len(year_periods)} year/periods")

    # STEP 4: Query GSI1 for each year/period combination
    all_results = []
    query_cred_padded = pad_number(query_cred, 3)
    step_padded = pad_number(step, 2)

    for year, period in year_periods:
        # Query GSI1 for this specific combination
        response = table.query(
            IndexName='ExactMatchIndex',
            KeyConditionExpression=Key('GSI1PK').eq(
                f'YEAR#{year}#PERIOD#{period}#EDU#{query_edu}#CR#{query_cred_padded}'
            ) & Key('GSI1SK').begins_with(f'STEP#{step_padded}#')
        )

        # Add all results, marking if exact match
        for item in response.get('Items', []):
            item['is_exact_match'] = is_exact_match
            all_results.append(item)

    logger.info(f"Retrieved {len(all_results)} total salary results")

    # STEP 5: Deduplicate by district - keep most recent year/period per district
    district_best_match = {}
    for item in all_results:
        district_id = item.get('district_id')
        year = item.get('school_year')
        period = item.get('period')

        if district_id not in district_best_match:
            district_best_match[district_id] = item
        else:
            existing = district_best_match[district_id]
            existing_year = existing.get('school_year')
            existing_period = existing.get('period')

            # Keep the more recent
            if (year, period) > (existing_year, existing_period):
                district_best_match[district_id] = item

    all_results = list(district_best_match.values())
    logger.info(f"After deduplication: {len(all_results)} districts")

    # Sort by salary (descending)
    all_results.sort(key=lambda x: float(x.get('salary', 0)), reverse=True)

    # STEP 6: Fetch towns and district types for all result districts
    result_district_ids = [item.get('district_id') for item in all_results]

    # Import utilities
    from utils.dynamodb import get_district_towns
    district_towns_map = get_district_towns(result_district_ids, table.name)

    # Fetch district types using batch_get_item
    dynamodb = boto3.resource('dynamodb')
    district_types_map = {}

    if result_district_ids:
        try:
            # Use batch_get_item for efficient bulk retrieval (max 100 items per request)
            for i in range(0, len(result_district_ids), 100):
                batch_ids = result_district_ids[i:i+100]
                keys = [{'PK': f'DISTRICT#{did}', 'SK': 'METADATA'} for did in batch_ids]

                response = dynamodb.batch_get_item(
                    RequestItems={
                        table.name: {
                            'Keys': keys
                        }
                    }
                )

                # Process returned items
                for item in response.get('Responses', {}).get(table.name, []):
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
            'is_calculated': bool(item.get('is_calculated', False)),
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

    # Calculate exact vs fallback match counts
    exact_match_count = sum(1 for r in rankings if r.get('is_exact_match', True))
    fallback_match_count = len(rankings) - exact_match_count

    return {
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
            'exact_matches': exact_match_count,
            'fallback_matches': fallback_match_count,
            'fallback_enabled': include_fallback,
            'year_periods_queried': len(year_periods)
        }
    }


def get_district_salary_metadata(table, district_id: str) -> Dict[str, Any]:
    """
    Get salary metadata for a district (available years, salary range)

    Args:
        table: DynamoDB table resource
        district_id: District ID

    Returns:
        Dictionary with district salary metadata
    """
    if not table:
        raise Exception('DynamoDB table not configured')

    # Query for all schedules for this district
    response = table.query(
        KeyConditionExpression=Key('PK').eq(f'DISTRICT#{district_id}') & Key('SK').begins_with('SCHEDULE#')
    )

    items = response.get('Items', [])

    if not items:
        raise ValueError('No salary data found for district')

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

    return {
        'district_id': district_id,
        'district_name': district_name,
        'available_years': sorted(list(years_periods.keys())),
        'latest_year': max(years_periods.keys()) if years_periods else None,
        'salary_range': {
            'min': min_salary if min_salary != float('inf') else None,
            'max': max_salary if max_salary != float('-inf') else None
        },
        'schedules': schedules
    }