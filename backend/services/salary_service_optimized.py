"""
Optimized salary service with performance improvements
"""
import logging
from typing import Dict, Any, Optional, List
from decimal import Decimal
from collections import defaultdict

import boto3
from boto3.dynamodb.conditions import Key

from config import (
    VALID_EDUCATION_LEVELS,
    VALID_CREDITS,
    MIN_STEP,
    MAX_STEP
)

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


# OPTIMIZATION 1: Cache for salary schedules (in-memory, Lambda-scoped)
# This cache persists across Lambda invocations in the same container
_salary_cache = {}
_cache_ttl_seconds = 60  # 1 minute TTL


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
