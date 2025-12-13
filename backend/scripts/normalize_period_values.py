"""Normalize period values to 'Full Year' format.

This script scans the DynamoDB table and updates all period values from
variations like 'full year', 'full-year', 'FY', etc. to the standardized
'Full Year' format (with capital F and Y).

It updates:
- The 'period' attribute in salary schedule items
- The SK (Sort Key) values containing PERIOD#
- GSI1PK and GSI2PK values containing PERIOD#
- METADATA#SCHEDULES items

Usage:
  python backend/scripts/normalize_period_values.py [table_name]

  OR set environment variables in backend/.env:
    DYNAMODB_TABLE_NAME=<table>
    AWS_REGION=<region>

Options:
  --dry-run    Show what would be updated without making changes
"""

import os
import sys
import argparse
import logging
from pathlib import Path
from decimal import Decimal

import boto3
from dotenv import load_dotenv

# Configure logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
logging.basicConfig(format='%(levelname)s: %(message)s')


def should_normalize_period(period_value):
    """Check if a period value needs normalization to 'Full Year'"""
    if not period_value:
        return False

    # Already correct
    if period_value == 'Full Year':
        return False

    # Common variations that should be normalized
    normalized = period_value.lower().replace('-', ' ').replace('_', ' ').strip()

    # Check if it's a variation of "full year"
    if normalized == 'full year':
        return True

    # Check for other common full-year abbreviations
    if period_value.upper() in ['FY', 'FULL_YEAR', 'FULLYEAR']:
        return True

    return False


def update_schedule_item_period(table, item, dry_run=False):
    """Update a salary schedule item's period value and all related keys"""
    old_period = item.get('period', '')

    if not should_normalize_period(old_period):
        return False

    new_period = 'Full Year'

    logger.info(f"  Schedule item: {item.get('PK')} / {item.get('SK')}")
    logger.info(f"    Period: '{old_period}' -> '{new_period}'")

    if dry_run:
        return True

    # We need to delete the old item and create a new one with updated keys
    # because SK and GSI keys are immutable

    # Create new item with updated keys
    new_item = item.copy()
    new_item['period'] = new_period

    # Update SK if it contains PERIOD#
    if 'SK' in new_item and 'PERIOD#' in new_item['SK']:
        new_item['SK'] = new_item['SK'].replace(f'PERIOD#{old_period}', f'PERIOD#{new_period}')
        logger.info(f"    Updated SK: {item['SK']} -> {new_item['SK']}")

    # Update GSI1PK if it contains PERIOD#
    if 'GSI1PK' in new_item and 'PERIOD#' in new_item['GSI1PK']:
        new_item['GSI1PK'] = new_item['GSI1PK'].replace(f'PERIOD#{old_period}', f'PERIOD#{new_period}')
        logger.info(f"    Updated GSI1PK")

    # Update GSI2PK if it contains PERIOD#
    if 'GSI2PK' in new_item and 'PERIOD#' in new_item['GSI2PK']:
        new_item['GSI2PK'] = new_item['GSI2PK'].replace(f'PERIOD#{old_period}', f'PERIOD#{new_period}')
        logger.info(f"    Updated GSI2PK")

    # Delete old item
    table.delete_item(Key={'PK': item['PK'], 'SK': item['SK']})

    # Put new item
    table.put_item(Item=new_item)

    return True


def update_metadata_schedules_item(table, item, dry_run=False):
    """Update a METADATA#SCHEDULES item's period value"""
    old_period = item.get('period', '')

    if not should_normalize_period(old_period):
        return False

    new_period = 'Full Year'

    logger.info(f"  Metadata item: {item.get('PK')} / {item.get('SK')}")
    logger.info(f"    Period: '{old_period}' -> '{new_period}'")

    if dry_run:
        return True

    # Create new item with updated keys
    new_item = item.copy()
    new_item['period'] = new_period

    # Update SK if it contains PERIOD#
    if 'SK' in new_item and 'PERIOD#' in new_item['SK']:
        new_item['SK'] = new_item['SK'].replace(f'PERIOD#{old_period}', f'PERIOD#{new_period}')
        logger.info(f"    Updated SK: {item['SK']} -> {new_item['SK']}")

    # Delete old item and create new one
    table.delete_item(Key={'PK': item['PK'], 'SK': item['SK']})
    table.put_item(Item=new_item)

    return True


def update_availability_metadata_item(table, item, dry_run=False):
    """Update a METADATA#AVAILABILITY item's SK value and period attribute"""
    if 'SK' not in item or 'PERIOD#' not in item['SK']:
        return False

    # Extract period from SK: YEAR#2021-2022#PERIOD#full-year
    parts = item['SK'].split('#')
    if len(parts) < 4 or parts[2] != 'PERIOD':
        return False

    old_period_in_sk = parts[3]
    old_period_attr = item.get('period', '')

    # Check if either the SK period or the period attribute needs normalization
    sk_needs_update = should_normalize_period(old_period_in_sk)
    attr_needs_update = should_normalize_period(old_period_attr)

    if not sk_needs_update and not attr_needs_update:
        return False

    new_period = 'Full Year'

    logger.info(f"  Availability metadata: {item.get('PK')} / {item.get('SK')}")
    if sk_needs_update:
        logger.info(f"    Period in SK: '{old_period_in_sk}' -> '{new_period}'")
    if attr_needs_update:
        logger.info(f"    Period attribute: '{old_period_attr}' -> '{new_period}'")

    if dry_run:
        return True

    # Create new item with updated SK and period attribute
    new_item = item.copy()

    # Update SK if needed
    if sk_needs_update:
        new_item['SK'] = item['SK'].replace(f'PERIOD#{old_period_in_sk}', f'PERIOD#{new_period}')
        logger.info(f"    Updated SK: {item['SK']} -> {new_item['SK']}")

    # Always update period attribute to match SK
    new_item['period'] = new_period

    # Delete old item and create new one (or just update if SK didn't change)
    if sk_needs_update:
        # SK changed, so we need to merge with existing item if it exists
        # First check if target already exists
        target_response = table.get_item(
            Key={'PK': new_item['PK'], 'SK': new_item['SK']}
        )

        if 'Item' in target_response:
            # Target exists - merge the districts
            existing_item = target_response['Item']
            existing_districts = existing_item.get('districts', {})
            new_districts = new_item.get('districts', {})

            # Merge districts (new_districts overwrites existing for same district_id)
            merged_districts = {**existing_districts, **new_districts}

            logger.info(f"    Merging {len(new_districts)} districts with {len(existing_districts)} existing districts")

            # Delete old item with wrong SK
            table.delete_item(Key={'PK': item['PK'], 'SK': item['SK']})

            # Update the existing target with merged districts
            existing_item['districts'] = merged_districts
            existing_item['period'] = new_period
            table.put_item(Item=existing_item)
        else:
            # Target doesn't exist - simple delete and recreate
            table.delete_item(Key={'PK': item['PK'], 'SK': item['SK']})
            table.put_item(Item=new_item)
    else:
        # SK stayed the same, just update the item
        table.put_item(Item=new_item)

    return True


def scan_and_update(table, table_name, aws_region, dry_run=False):
    """Scan the entire table and update period values"""
    logger.info(f"{'[DRY RUN] ' if dry_run else ''}Starting period normalization...")
    logger.info(f"Table: {table_name}")
    logger.info(f"Region: {aws_region}")

    total_scanned = 0
    total_updated = 0
    schedule_items_updated = 0
    metadata_items_updated = 0
    availability_items_updated = 0

    # Scan the entire table
    scan_kwargs = {}

    while True:
        response = table.scan(**scan_kwargs)
        items = response.get('Items', [])
        total_scanned += len(items)

        for item in items:
            pk = item.get('PK', '')
            sk = item.get('SK', '')

            # Handle salary schedule items (DISTRICT# / SCHEDULE#...)
            if pk.startswith('DISTRICT#') and sk.startswith('SCHEDULE#'):
                if update_schedule_item_period(table, item, dry_run):
                    total_updated += 1
                    schedule_items_updated += 1

            # Handle METADATA#SCHEDULES items
            elif pk == 'METADATA#SCHEDULES' and sk.startswith('YEAR#'):
                if update_metadata_schedules_item(table, item, dry_run):
                    total_updated += 1
                    metadata_items_updated += 1

            # Handle METADATA#AVAILABILITY items
            elif pk == 'METADATA#AVAILABILITY' and 'PERIOD#' in sk:
                if update_availability_metadata_item(table, item, dry_run):
                    total_updated += 1
                    availability_items_updated += 1

        # Check for pagination
        if 'LastEvaluatedKey' not in response:
            break

        scan_kwargs['ExclusiveStartKey'] = response['LastEvaluatedKey']
        logger.info(f"Scanned {total_scanned} items so far, updated {total_updated}...")

    logger.info(f"\n{'[DRY RUN] ' if dry_run else ''}Scan complete!")
    logger.info(f"Total items scanned: {total_scanned}")
    logger.info(f"Total items updated: {total_updated}")
    logger.info(f"  - Schedule items: {schedule_items_updated}")
    logger.info(f"  - Metadata schedule items: {metadata_items_updated}")
    logger.info(f"  - Availability metadata items: {availability_items_updated}")

    if dry_run:
        logger.info("\nThis was a dry run. No changes were made.")
        logger.info("Run without --dry-run to apply changes.")


def main():
    parser = argparse.ArgumentParser(
        description='Normalize period values to "Full Year" format'
    )
    parser.add_argument(
        'table_name',
        nargs='?',
        help='DynamoDB table name (optional if set in .env)'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Show what would be updated without making changes'
    )

    args = parser.parse_args()

    # Load environment variables from backend/.env
    backend_dir = Path(__file__).parent.parent
    env_path = backend_dir / '.env'
    load_dotenv(dotenv_path=env_path)

    # Get table name from command line argument or environment variable
    if args.table_name:
        table_name = args.table_name
    else:
        table_name = os.environ.get('DYNAMODB_TABLE_NAME')

        if not table_name:
            logger.error("ERROR: Required table name not provided")
            logger.error("\nUsage:")
            logger.error("  python backend/scripts/normalize_period_values.py <table_name>")
            logger.error("  OR set environment variable in backend/.env:")
            logger.error("    DYNAMODB_TABLE_NAME=<table_name>")
            sys.exit(1)

        logger.info(f"Using environment variable from .env:")
        logger.info(f"  Table: {table_name}\n")

    # Get AWS region from environment variable
    aws_region = os.environ.get('AWS_REGION', 'us-east-1')

    # Initialize DynamoDB
    dynamodb = boto3.resource('dynamodb', region_name=aws_region)
    table = dynamodb.Table(table_name)

    # Verify table exists
    try:
        table.load()
    except Exception as e:
        logger.error(f"Failed to connect to table {table_name}: {e}")
        logger.error("Make sure DYNAMODB_TABLE_NAME and AWS_REGION are set correctly")
        sys.exit(1)

    # Confirm if not dry run
    if not args.dry_run:
        logger.warning("This will update period values in the DynamoDB table.")
        response = input("Continue? (yes/no): ")
        if response.lower() != 'yes':
            logger.info("Cancelled")
            sys.exit(0)

    scan_and_update(table, table_name, aws_region, dry_run=args.dry_run)


if __name__ == '__main__':
    main()
