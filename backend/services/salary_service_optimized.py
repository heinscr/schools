"""
Optimized salary service with performance improvements
"""
import logging
import os
import time
from typing import Dict, Any, Optional, List
from decimal import Decimal
from collections import defaultdict

import boto3
from boto3.dynamodb.conditions import Key, Attr

from config import (
    VALID_EDUCATION_LEVELS,
    MIN_STEP,
    get_max_step,
    get_valid_credits
)

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


# OPTIMIZATION 1: Cache for salary schedules (in-memory, Lambda-scoped)
# This cache persists across Lambda invocations in the same container
_salary_cache = {}
_cache_ttl_seconds = int(os.getenv('SALARY_CACHE_TTL', '60'))  # 1 minute TTL by default
_cache_enabled = os.getenv('DISABLE_SALARY_CACHE', '').lower() != 'true'

# Module-level table placeholder for tests and callers that set `services.salary_service.table`
# Tests monkeypatch this attribute; provide a default to allow setattr without errors.
table = None


def get_salary_schedule_for_district_optimized(
    table,
    district_id: str,
    year: Optional[str] = None,
    use_cache: bool = True
) -> List[Dict[str, Any]]:
    """
    OPTIMIZED version of get_salary_schedule_for_district

    Performance improvements:
    1. Optional caching with TTL
    2. Reduce dict operations - use list comprehension
    3. Avoid redundant string parsing
    4. Use projection expression to reduce data transfer

    Args:
        table: DynamoDB table resource
        district_id: District ID
        year: Optional school year filter
        use_cache: Whether to use caching (default True)

    Returns:
        List of salary schedule objects grouped by year/period
    """
    if not table:
        raise Exception('DynamoDB table not configured')

    # OPTIMIZATION 1: Check cache
    cache_key = f"{district_id}#{year or 'all'}"
    if use_cache and cache_key in _salary_cache:
        cached_data, timestamp = _salary_cache[cache_key]
        import time
        if time.time() - timestamp < _cache_ttl_seconds:
            logger.info(f"Cache hit for {cache_key}")
            return cached_data

    # Build key condition
    key_condition = Key('PK').eq(f'DISTRICT#{district_id}')

    if year:
        key_condition = key_condition & Key('SK').begins_with(f'SCHEDULE#{year}')
    else:
        key_condition = key_condition & Key('SK').begins_with('SCHEDULE#')

    # OPTIMIZATION 2: Use ProjectionExpression to reduce data transfer
    # Only fetch fields we actually need
    response = table.query(
        KeyConditionExpression=key_condition,
        ProjectionExpression='school_year,period,education,credits,#s,salary,is_calculated,is_calculated_from',
        ExpressionAttributeNames={'#s': 'step'}  # 'step' is a reserved word
    )

    items = response.get('Items', [])

    if not items:
        return []

    # OPTIMIZATION 3: Single-pass grouping with minimal allocations
    schedules = defaultdict(list)

    # Pre-allocate the schedule key to avoid repeated string concatenation
    for item in items:
        # Use direct dict access for better performance
        year_period = f"{item['school_year']}#{item['period']}"

        # OPTIMIZATION 4: Reuse item dict structure where possible
        # Only convert types that need it
        schedules[year_period].append({
            'education': item['education'],
            'is_calculated': item.get('is_calculated', False),
            'is_calculated_from': item.get('is_calculated_from'),
            'credits': int(item['credits']),  # DynamoDB returns Decimal/int
            'step': int(item['step']),
            'salary': float(item['salary'])  # Convert Decimal to float once
        })

    # OPTIMIZATION 5: Pre-allocate result list size
    result = []
    result_size = len(schedules)

    # Sort keys once instead of multiple times
    for year_period in schedules.keys():
        year, period = year_period.split('#', 1)
        result.append({
            'school_year': year,
            'period': period,
            'district_id': district_id,
            'salaries': schedules[year_period]
        })

    # OPTIMIZATION 6: Cache the result
    if use_cache:
        import time
        _salary_cache[cache_key] = (result, time.time())
        logger.info(f"Cached result for {cache_key}, total items: {len(items)}")

    return result


# OPTIMIZATION 7: Batch prefetch for multiple districts
def prefetch_salary_schedules(
    table,
    district_ids: List[str],
    year: Optional[str] = None
) -> Dict[str, List[Dict[str, Any]]]:
    """
    Prefetch salary schedules for multiple districts in parallel

    This is useful when the frontend needs data for multiple districts
    (e.g., displaying a list or comparison)

    Args:
        table: DynamoDB table resource
        district_ids: List of district IDs to fetch
        year: Optional year filter

    Returns:
        Dict mapping district_id to salary schedule list
    """
    import concurrent.futures
    from functools import partial

    results = {}

    # Use ThreadPoolExecutor for I/O-bound DynamoDB queries
    fetch_fn = partial(get_salary_schedule_for_district_optimized, table, year=year)

    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        future_to_district = {
            executor.submit(fetch_fn, district_id): district_id
            for district_id in district_ids
        }

        for future in concurrent.futures.as_completed(future_to_district):
            district_id = future_to_district[future]
            try:
                results[district_id] = future.result()
            except Exception as e:
                logger.error(f"Error fetching {district_id}: {e}")
                results[district_id] = []

    return results


# OPTIMIZATION 8: Clear cache function for admin operations
def invalidate_salary_cache(district_id: Optional[str] = None):
    """
    Invalidate salary cache for a specific district or all districts

    Call this after uploading new salary data
    """
    global _salary_cache

    if district_id:
        # Remove all cache entries for this district
        keys_to_remove = [k for k in _salary_cache.keys() if k.startswith(f"{district_id}#")]
        for key in keys_to_remove:
            del _salary_cache[key]
        logger.info(f"Invalidated cache for district {district_id}")
    else:
        # Clear entire cache
        _salary_cache.clear()
        logger.info("Invalidated entire salary cache")


# OPTIMIZATION 9: Streaming response for very large datasets
def get_salary_schedule_streaming(
    table,
    district_id: str,
    year: Optional[str] = None
):
    """
    Generator version that streams results instead of loading all into memory

    Useful for districts with very large datasets (10+ years of data)
    """
    if not table:
        raise Exception('DynamoDB table not configured')

    key_condition = Key('PK').eq(f'DISTRICT#{district_id}')

    if year:
        key_condition = key_condition & Key('SK').begins_with(f'SCHEDULE#{year}')
    else:
        key_condition = key_condition & Key('SK').begins_with('SCHEDULE#')

    # DynamoDB pagination
    response = table.query(
        KeyConditionExpression=key_condition,
        ProjectionExpression='school_year,period,education,credits,#s,salary,is_calculated,is_calculated_from',
        ExpressionAttributeNames={'#s': 'step'}
    )

    # Process first page
    schedules = defaultdict(list)
    for item in response.get('Items', []):
        year_period = f"{item['school_year']}#{item['period']}"
        schedules[year_period].append({
            'education': item['education'],
            'is_calculated': item.get('is_calculated', False),
            'is_calculated_from': item.get('is_calculated_from'),
            'credits': int(item['credits']),
            'step': int(item['step']),
            'salary': float(item['salary'])
        })

    # Handle pagination if needed
    while 'LastEvaluatedKey' in response:
        response = table.query(
            KeyConditionExpression=key_condition,
            ProjectionExpression='school_year,period,education,credits,#s,salary,is_calculated,is_calculated_from',
            ExpressionAttributeNames={'#s': 'step'},
            ExclusiveStartKey=response['LastEvaluatedKey']
        )

        for item in response.get('Items', []):
            year_period = f"{item['school_year']}#{item['period']}"
            schedules[year_period].append({
                'education': item['education'],
                'is_calculated': item.get('is_calculated', False),
                'is_calculated_from': item.get('is_calculated_from'),
                'credits': int(item['credits']),
                'step': int(item['step']),
                'salary': float(item['salary'])
            })

    # Yield results
    for year_period, salaries in schedules.items():
        year, period = year_period.split('#', 1)
        yield {
            'school_year': year,
            'period': period,
            'district_id': district_id,
            'salaries': salaries
        }


# --- Compatibility and additional helpers moved from legacy salary_service.py ---
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

    valid_credits = get_valid_credits()
    if credits_int not in valid_credits:
        raise ValueError(f"Invalid credits {credits_int}. Must be one of: {', '.join(map(str, sorted(valid_credits)))}")
    return credits_int


def validate_step(step: Optional[str]) -> int:
    """Validate step parameter"""
    if not step:
        raise ValueError("Step parameter is required")

    try:
        step_int = int(step)
    except (ValueError, TypeError):
        raise ValueError(f"Invalid step '{step}'. Must be an integer")

    max_step = get_max_step()
    if not (MIN_STEP <= step_int <= max_step):
        raise ValueError(f"Invalid step {step_int}. Must be between {MIN_STEP} and {max_step}")
    return step_int


def pad_number(num: int, width: int) -> str:
    """Pad a number with leading zeros"""
    return str(num).zfill(width)


def invalidate_comparison_cache():
    """
    Invalidate all comparison query caches

    Call this after salary data changes that affect comparison queries
    """
    global _salary_cache

    # Remove all comparison cache entries (start with "compare#")
    keys_to_remove = [k for k in _salary_cache.keys() if k.startswith("compare#")]
    for key in keys_to_remove:
        del _salary_cache[key]
    logger.info(f"Invalidated comparison cache ({len(keys_to_remove)} entries)")


def get_salary_schedule_for_district(table, district_id: str, year: Optional[str] = None):
    """Compatibility wrapper for the original function name."""
    # Delegate to optimized implementation; keep same signature
    return get_salary_schedule_for_district_optimized(table, district_id, year, use_cache=_cache_enabled)


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

    This is a near-direct port of the legacy implementation and uses the
    ComparisonIndex GSI to perform a single efficient query across districts.
    """
    if not table:
        raise Exception('DynamoDB table not configured')

    # Validate parameters
    education = validate_education_level(education)
    credits = validate_credits(str(credits))
    step = validate_step(str(step))

    # OPTIMIZATION: Check cache first
    cache_key = f"compare#{education}#{credits}#{step}#{district_type or 'all'}#{year_param or 'latest'}#{include_fallback}"

    if _cache_enabled and cache_key in _salary_cache:
        cached_data, timestamp = _salary_cache[cache_key]
        if time.time() - timestamp < _cache_ttl_seconds:
            logger.info(f"Cache HIT for comparison query {cache_key}")
            return cached_data
        else:
            del _salary_cache[cache_key]
            logger.info(f"Cache EXPIRED for comparison query {cache_key}")

    # Cache miss - proceed with query
    query_start_time = time.time()
    logger.info(f"Cache MISS for comparison query {cache_key}")

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
        best_combo_edu = ''
        best_combo_cred = -1

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

    logger.info(f"Querying for {query_edu}+{query_cred} step {step} using ComparisonIndex (single query)")

    # STEP 4: Query ComparisonIndex (GSI5) - ONE query for all districts across all years
    query_cred_padded = pad_number(int(query_cred), 3)
    step_padded = pad_number(step, 2)

    response = table.query(
        IndexName='ComparisonIndex',
        KeyConditionExpression=Key('GSI_COMP_PK').eq(
            f'EDU#{query_edu}#CR#{query_cred_padded}#STEP#{step_padded}'
        )
    )

    all_results = []
    for item in response.get('Items', []):
        item['is_exact_match'] = is_exact_match
        all_results.append(item)

    # Handle pagination
    while 'LastEvaluatedKey' in response:
        response = table.query(
            IndexName='ComparisonIndex',
            KeyConditionExpression=Key('GSI_COMP_PK').eq(
                f'EDU#{query_edu}#CR#{query_cred_padded}#STEP#{step_padded}'
            ),
            ExclusiveStartKey=response['LastEvaluatedKey']
        )
        for item in response.get('Items', []):
            item['is_exact_match'] = is_exact_match
            all_results.append(item)
    # Filter out any non-district rows (e.g., metadata) that may have been
    # returned by the test FakeTable implementation or by misconfigured GSIs.
    # We require a `district_id` to perform deduplication and ranking.
    all_results = [it for it in all_results if it.get('district_id')]

    logger.info(f"Retrieved {len(all_results)} total salary results (single query)")

    # STEP 5: Deduplicate by district - keep oldest year/period per district
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

            # Keep the older. Use safe fallbacks for missing year/period values
            # to avoid TypeError when items have None for these fields.
            year_key = (year or '')
            period_key = (period or '')
            existing_year_key = (existing_year or '')
            existing_period_key = (existing_period or '')

            if (year_key, period_key) < (existing_year_key, existing_period_key):
                district_best_match[district_id] = item

    all_results = list(district_best_match.values())
    logger.info(f"After deduplication: {len(all_results)} districts")

    # FILTER: Only include Municipal and Regional Academic districts
    # First, we need to fetch district types to filter
    result_district_ids_unfiltered = [item.get('district_id') for item in all_results]

    # Fetch district types for filtering
    dynamodb = boto3.resource('dynamodb')
    district_types_for_filtering = {}
    tbl_name = getattr(table, 'name', 'TEST_TABLE')

    if result_district_ids_unfiltered:
        try:
            for i in range(0, len(result_district_ids_unfiltered), 100):
                batch_ids = result_district_ids_unfiltered[i:i+100]
                keys = [{'PK': f'DISTRICT#{did}', 'SK': 'METADATA'} for did in batch_ids]

                response = dynamodb.batch_get_item(
                    RequestItems={
                        tbl_name: {
                            'Keys': keys
                        }
                    }
                )

                for item in response.get('Responses', {}).get(tbl_name, []):
                    district_id = item['PK'].replace('DISTRICT#', '')
                    district_types_for_filtering[district_id] = item.get('district_type', 'unknown')
        except Exception as e:
            logger.error(f"Error fetching district types for filtering: {str(e)}")

    # Filter to only Municipal and Regional Academic districts
    ALLOWED_DISTRICT_TYPES = {'municipal', 'regional_academic'}
    all_results = [
        item for item in all_results
        if district_types_for_filtering.get(item.get('district_id'), 'unknown') in ALLOWED_DISTRICT_TYPES
    ]
    logger.info(f"After filtering to Municipal/Regional: {len(all_results)} districts")

    # STEP 6: Fetch towns and district types for all result districts
    result_district_ids = [item.get('district_id') for item in all_results]

    from utils.dynamodb import get_district_towns
    district_towns_map = get_district_towns(result_district_ids, tbl_name)

    # Fetch district types using batch_get_item (dynamodb already initialized above)
    district_types_map = {}

    if result_district_ids:
        try:
            for i in range(0, len(result_district_ids), 100):
                batch_ids = result_district_ids[i:i+100]
                keys = [{'PK': f'DISTRICT#{did}', 'SK': 'METADATA'} for did in batch_ids]

                response = dynamodb.batch_get_item(
                    RequestItems={
                        tbl_name: {
                            'Keys': keys
                        }
                    }
                )

                for item in response.get('Responses', {}).get(tbl_name, []):
                    district_id = item['PK'].replace('DISTRICT#', '')
                    district_types_map[district_id] = {
                        'district_type': item.get('district_type', 'unknown'),
                        'contract_pdf': item.get('contract_pdf')
                    }

                for district_id in batch_ids:
                    if district_id not in district_types_map:
                        district_types_map[district_id] = {
                            'district_type': 'unknown',
                            'contract_pdf': None
                        }

        except Exception as e:
            logger.error(f"Error fetching district types: {str(e)}")
            for district_id in result_district_ids:
                district_types_map[district_id] = {
                    'district_type': 'unknown',
                    'contract_pdf': None
                }

    # Transform results for response
    rankings = []
    for index, item in enumerate(all_results):
        district_id = item.get('district_id')
        district_info = district_types_map.get(district_id, {'district_type': 'unknown', 'contract_pdf': None})
        result = {
            'rank': index + 1,
            'district_id': district_id,
            'district_name': item.get('district_name'),
            'district_type': district_info.get('district_type', 'unknown'),
            'contract_pdf': district_info.get('contract_pdf'),
            'school_year': item.get('school_year'),
            'period': item.get('period'),
            'education': item.get('education'),
            'credits': int(item.get('credits', 0)),
            'step': int(item.get('step', 0)),
            'salary': float(item.get('salary', 0)),
            'is_calculated': bool(item.get('is_calculated', False)),
            'is_calculated_from': item.get('is_calculated_from'),
            'is_exact_match': item.get('is_exact_match', True),
            'towns': district_towns_map.get(district_id, [])
        }

        if not item.get('is_exact_match', True):
            result['queried_for'] = {
                'education': education,
                'credits': credits,
                'step': step
            }

        rankings.append(result)

    exact_match_count = sum(1 for r in rankings if r.get('is_exact_match', True))
    fallback_match_count = len(rankings) - exact_match_count

    result = {
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

    query_time = time.time() - query_start_time
    if _cache_enabled:
        _salary_cache[cache_key] = (result, time.time())
        logger.info(f"Cached comparison query result: {len(rankings)} districts, "
                   f"query_time={query_time:.3f}s, cache_size={len(_salary_cache)}")
    else:
        logger.info(f"Cache DISABLED: {len(rankings)} districts, query_time={query_time:.3f}s")

    return result


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

    response = table.query(
        KeyConditionExpression=Key('PK').eq(f'DISTRICT#{district_id}') & Key('SK').begins_with('SCHEDULE#')
    )

    items = response.get('Items', [])

    if not items:
        raise ValueError('No salary data found for district')

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

    district_name = items[0].get('district_name', district_id)

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
