"""Local normalization runner.

This script runs salary normalization locally using the same shared utilities
as the Lambda normalizer (backend/utils/normalization.py).

Usage:
  DYNAMODB_TABLE_NAME=<table> AWS_REGION=<region> python backend/scripts/normalize_salaries.py
"""

import os
import sys
import logging
from datetime import datetime
from decimal import Decimal
from pathlib import Path

import boto3
from boto3.dynamodb.conditions import Key

# Make backend importable
backend_path = Path(__file__).parent.parent
sys.path.insert(0, str(backend_path))

from utils.normalization import generate_calculated_entries
from database import table, AWS_REGION, TABLE_NAME

# Configure logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
logging.basicConfig(format='%(levelname)s: %(message)s')


def get_max_values():
    """Get global max values from metadata"""
    resp = table.get_item(Key={'PK': 'METADATA#MAXVALUES', 'SK': 'GLOBAL'})
    if 'Item' not in resp:
        raise RuntimeError('METADATA#MAXVALUES not found')
    item = resp['Item']
    return int(item.get('max_step', 15)), item.get('edu_credit_combos', [])


def get_all_year_periods():
    """Get all year/period combinations from metadata"""
    resp = table.query(KeyConditionExpression=Key('PK').eq('METADATA#SCHEDULES'))
    return [(item['school_year'], item['period']) for item in resp.get('Items', [])]


def get_district_data_for_year_period(year, period):
    """Get all real (non-calculated) salary entries for a specific year/period"""
    # Get availability metadata
    resp = table.get_item(
        Key={'PK': 'METADATA#AVAILABILITY', 'SK': f'YEAR#{year}#PERIOD#{period}'}
    )
    
    if 'Item' not in resp:
        return {}
    
    districts = resp['Item'].get('districts', {})
    district_data = {}
    
    # Query real entries for each district
    for district_id in districts.keys():
        query_resp = table.query(
            IndexName='FallbackQueryIndex',
            KeyConditionExpression=Key('GSI2PK').eq(
                f'YEAR#{year}#PERIOD#{period}#DISTRICT#{district_id}'
            )
        )
        
        # Filter to only real entries (not calculated)
        real_entries = [
            item for item in query_resp.get('Items', [])
            if not item.get('is_calculated', False)
        ]
        
        if real_entries:
            district_data[district_id] = real_entries
    
    return district_data


def ensure_decimal_salary(item):
    """Convert salary to Decimal for DynamoDB compatibility"""
    if 'salary' in item and item['salary'] is not None:
        if not isinstance(item['salary'], Decimal):
            item['salary'] = Decimal(str(item['salary']))


def batch_write_items(items, description):
    """Write items to DynamoDB in batches of 25"""
    if not items:
        return
    
    logger.info(f'Writing {len(items)} items for {description}...')
    
    batch_size = 25
    for i in range(0, len(items), batch_size):
        batch = items[i:i + batch_size]
        with table.batch_writer() as writer:
            for item in batch:
                ensure_decimal_salary(item)
                writer.put_item(Item=item)


def update_global_metadata(max_step, combos):
    """Update METADATA#MAXVALUES with all combos"""
    table.put_item(Item={
        'PK': 'METADATA#MAXVALUES',
        'SK': 'GLOBAL',
        'max_step': max_step,
        'edu_credit_combos': sorted(combos),
        'last_updated': datetime.utcnow().isoformat()
    })


def update_normalization_status(job_id):
    """Update normalization status metadata"""
    table.put_item(Item={
        'PK': 'METADATA#NORMALIZATION',
        'SK': 'STATUS',
        'needs_normalization': False,
        'last_normalized_at': datetime.utcnow().isoformat(),
        'last_normalization_job_id': job_id
    })


def main(job_id='local-run'):
    """Main normalization logic"""
    logger.info('Starting normalization...')
    
    # Get metadata
    max_step, combos = get_max_values()
    logger.info(f'Max step: {max_step}, Combos: {len(combos)}')
    
    year_periods = get_all_year_periods()
    logger.info(f'Found {len(year_periods)} year/period combinations')
    
    # Education level ordering for fallback logic
    edu_order = {'B': 1, 'M': 2, 'D': 3}
    
    total = 0
    combos_set = set(combos)
    
    # Process each year/period
    for year, period in year_periods:
        logger.info(f'Processing {year}/{period}...')
        
        district_data = get_district_data_for_year_period(year, period)
        logger.info(f'  Found {len(district_data)} districts with real data')
        
        all_calculated = []
        
        # Generate calculated entries for each district
        for district_id, real_entries in district_data.items():
            district_name = real_entries[0].get('district_name', district_id)
            
            # Use shared utility function (same as Lambda)
            calculated = generate_calculated_entries(
                district_id=district_id,
                district_name=district_name,
                year=year,
                period=period,
                real_entries=real_entries,
                max_step=max_step,
                all_edu_credit_combos=combos,
                edu_order=edu_order
            )
            
            all_calculated.extend(calculated)
            
            # Track new combos
            for entry in calculated:
                combos_set.add(f"{entry['education']}+{entry['credits']}")
        
        logger.info(f'  Generated {len(all_calculated)} calculated entries')
        
        # Write to DynamoDB
        if all_calculated:
            batch_write_items(all_calculated, f'{year}/{period}')
            total += len(all_calculated)
    
    # Update metadata
    update_global_metadata(max_step, list(combos_set))
    update_normalization_status(job_id)
    
    logger.info(f'Normalization complete: {total} records created')


if __name__ == '__main__':
    main()
