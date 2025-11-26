"""
Lambda function to normalize salary data across all districts
Runs the normalization logic from scripts/normalize_salaries.py
"""
import json
import os
import sys
import logging
import boto3
from datetime import datetime, UTC
from decimal import Decimal
from collections import defaultdict

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.normalization import generate_calculated_entries

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Get environment variables
TABLE_NAME = os.environ['DYNAMODB_TABLE_NAME']
AWS_REGION = os.environ.get('AWS_REGION', 'us-east-1')

# Initialize AWS clients with explicit region
dynamodb = boto3.resource('dynamodb', region_name=AWS_REGION)

# Initialize table
table = dynamodb.Table(TABLE_NAME)


def handler(event, context):
    """
    Lambda handler for global salary normalization

    Event format:
    {
        "job_id": "normalization-job-uuid"
    }
    """
    logger.info(f"Starting normalization: {json.dumps(event)}")

    job_id = event.get('job_id', 'unknown')

    try:
        # Get max values
        max_step, edu_credit_combos = get_max_values()
        logger.info(f"Max values: max_step={max_step}, combos={len(edu_credit_combos)}")

        # Get all year/periods
        year_periods = get_all_year_periods()
        logger.info(f"Found {len(year_periods)} year/period combinations")

        # Process each year/period
        total_calculated = 0
        all_combos_set = set(edu_credit_combos)

        for year, period in year_periods:
            logger.info(f"Processing {year}/{period}...")

            # Get district data
            district_data = get_district_data_for_year_period(year, period)
            logger.info(f"  Found {len(district_data)} districts with real data")

            # Generate calculated entries
            edu_order = {'B': 1, 'M': 2, 'D': 3}
            all_calculated = []
            for district_id, real_entries in district_data.items():
                district_name = real_entries[0]['district_name'] if real_entries else district_id
                calculated = generate_calculated_entries(
                    district_id, district_name, year, period, real_entries, max_step, edu_credit_combos, edu_order
                )
                all_calculated.extend(calculated)

                # Track combos created
                for entry in calculated:
                    combo = f"{entry['education']}+{entry['credits']}"
                    all_combos_set.add(combo)

            logger.info(f"  Generated {len(all_calculated)} calculated entries")

            # Write calculated entries
            if all_calculated:
                batch_write_items(all_calculated, f"{year}/{period}")
                total_calculated += len(all_calculated)

        logger.info(f"Normalization complete: {total_calculated} calculated entries created")

        # Update METADATA#MAXVALUES with all combos
        update_global_metadata(max_step, list(all_combos_set))

        # Update normalization status
        update_normalization_status(job_id)

        # Invalidate all caches after normalization
        try:
            # Import at function level to avoid circular dependencies
            sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            from services.salary_service_optimized import invalidate_salary_cache, invalidate_comparison_cache
            invalidate_salary_cache()  # Invalidate all district caches
            invalidate_comparison_cache()  # Invalidate all comparison query caches
            logger.info("Invalidated all caches after normalization")
        except Exception as e:
            logger.warning(f"Error invalidating caches: {e}")

        # Mark job as complete
        complete_normalization_job(job_id, total_calculated)

        return {
            'statusCode': 200,
            'body': json.dumps({
                'message': 'Normalization complete',
                'records_created': total_calculated
            })
        }

    except Exception as e:
        logger.error(f"Normalization failed: {str(e)}")

        # Mark job as failed
        fail_normalization_job(job_id, str(e))

        return {
            'statusCode': 500,
            'body': json.dumps({
                'message': 'Normalization failed',
                'error': str(e)
            })
        }


def get_max_values():
    """Get global max values from metadata"""
    response = table.get_item(
        Key={'PK': 'METADATA#MAXVALUES', 'SK': 'GLOBAL'}
    )

    if 'Item' not in response:
        raise Exception("METADATA#MAXVALUES not found")

    item = response['Item']
    max_step = int(item.get('max_step', 15))
    edu_credit_combos = item.get('edu_credit_combos', [])

    return max_step, edu_credit_combos


def get_all_year_periods():
    """Get all year/period combinations from metadata"""
    response = table.query(
        KeyConditionExpression=boto3.dynamodb.conditions.Key('PK').eq('METADATA#SCHEDULES')
    )

    year_periods = [
        (item['school_year'], item['period'])
        for item in response.get('Items', [])
    ]

    return year_periods


def get_district_data_for_year_period(year, period):
    """Get all real salary entries for a specific year/period"""
    # Get availability index
    response = table.get_item(
        Key={'PK': 'METADATA#AVAILABILITY', 'SK': f'YEAR#{year}#PERIOD#{period}'}
    )

    if 'Item' not in response:
        return {}

    districts_availability = response['Item'].get('districts', {})

    # For each district, query their real entries
    district_data = {}

    for district_id in districts_availability.keys():
        # Query all entries for this district/year/period
        entries_response = table.query(
            IndexName='FallbackQueryIndex',
            KeyConditionExpression=boto3.dynamodb.conditions.Key('GSI2PK').eq(
                f'YEAR#{year}#PERIOD#{period}#DISTRICT#{district_id}'
            )
        )

        # Filter to only real entries (not calculated)
        real_entries = [
            item for item in entries_response.get('Items', [])
            if not item.get('is_calculated', False)
        ]

        if real_entries:
            district_data[district_id] = real_entries

    return district_data


def batch_write_items(items, description):
    """Write items to DynamoDB in batches"""
    if not items:
        return

    logger.info(f"Writing {len(items)} items for {description}...")

    batch_size = 25
    written = 0

    for i in range(0, len(items), batch_size):
        batch = items[i:i + batch_size]

        try:
            with table.batch_writer() as writer:
                for item in batch:
                    writer.put_item(Item=item)

            written += len(batch)
            if written % 500 == 0:
                logger.info(f"  Progress: {written}/{len(items)} items written")

        except Exception as e:
            logger.error(f"Error writing batch: {e}")

    logger.info(f"  Completed: {written} written")


def update_global_metadata(max_step, edu_credit_combos):
    """Update global metadata with all combos"""
    table.put_item(Item={
        'PK': 'METADATA#MAXVALUES',
        'SK': 'GLOBAL',
        'max_step': max_step,
        'edu_credit_combos': sorted(edu_credit_combos),
        'last_updated': datetime.now(UTC).isoformat()
    })
    logger.info(f"Updated global metadata: max_step={max_step}, combos={len(edu_credit_combos)}")


def update_normalization_status(job_id):
    """Update normalization status to not needed"""
    table.put_item(Item={
        'PK': 'METADATA#NORMALIZATION',
        'SK': 'STATUS',
        'needs_normalization': False,
        'last_normalized_at': datetime.now(UTC).isoformat(),
        'last_normalization_job_id': job_id
    })
    logger.info("Updated normalization status to not needed")


def complete_normalization_job(job_id, records_created):
    """Mark normalization job as complete"""
    # Delete the running job marker
    table.delete_item(Key={'PK': 'NORMALIZATION_JOB#RUNNING', 'SK': 'METADATA'})

    # Create completed job record
    table.put_item(Item={
        'PK': f'NORMALIZATION_JOB#{job_id}',
        'SK': 'METADATA',
        'job_id': job_id,
        'status': 'completed',
        'completed_at': datetime.now(UTC).isoformat(),
        'records_created': records_created
    })

    logger.info(f"Normalization job {job_id} marked as complete")


def fail_normalization_job(job_id, error_message):
    """Mark normalization job as failed"""
    # Delete the running job marker
    try:
        table.delete_item(Key={'PK': 'NORMALIZATION_JOB#RUNNING', 'SK': 'METADATA'})
    except Exception:
        pass

    # Create failed job record
    table.put_item(Item={
        'PK': f'NORMALIZATION_JOB#{job_id}',
        'SK': 'METADATA',
        'job_id': job_id,
        'status': 'failed',
        'failed_at': datetime.now(UTC).isoformat(),
        'error_message': error_message
    })

    logger.error(f"Normalization job {job_id} marked as failed: {error_message}")