#!/usr/bin/env python3
"""
Load salary data from JSON into DynamoDB
New single-table design with metadata tracking and efficient GSIs
"""

import json
import boto3
from pathlib import Path
from collections import defaultdict
from decimal import Decimal
from boto3.dynamodb.conditions import Attr
from datetime import datetime

# Initialize DynamoDB
dynamodb = boto3.resource('dynamodb')

def get_districts_table_name():
    """Get districts table name from environment or use default"""
    import os
    return os.getenv('DISTRICTS_TABLE_NAME', 'crackpow-schools-districts')

def build_district_name_to_id_map(districts_table_name):
    """
    Query the districts table and build a mapping of district names to UUIDs
    Returns dict: {district_name_lower: district_id}
    """
    print(f"\nQuerying districts table: {districts_table_name}...")
    table = dynamodb.Table(districts_table_name)

    district_map = {}

    try:
        # Scan the table for all district metadata items
        response = table.scan(
            FilterExpression=Attr('entity_type').eq('district')
        )

        for item in response.get('Items', []):
            district_id = item.get('district_id')
            district_name = item.get('name', '')
            if district_id and district_name:
                # Store with lowercase name for matching
                district_map[district_name.lower()] = district_id

        # Handle pagination if needed
        while 'LastEvaluatedKey' in response:
            response = table.scan(
                FilterExpression=Attr('entity_type').eq('district'),
                ExclusiveStartKey=response['LastEvaluatedKey']
            )
            for item in response.get('Items', []):
                district_id = item.get('district_id')
                district_name = item.get('name', '')
                if district_id and district_name:
                    district_map[district_name.lower()] = district_id

        print(f"✓ Found {len(district_map)} districts in table")

    except Exception as e:
        print(f"✗ Error querying districts table: {e}")
        print("  Continuing with name-based fallback...")

    return district_map

def load_salary_json():
    """Load salary data from JSON file"""
    json_path = Path(__file__).parent.parent.parent / 'data' / 'salary_data.json'

    # Try example file if main file doesn't exist
    if not json_path.exists():
        json_path = Path(__file__).parent.parent.parent / 'data' / 'salary_data.example.json'
        print(f"Using example data file: {json_path}")

    with open(json_path, 'r') as f:
        return json.load(f)

def match_district_name_to_id(district_name, district_map):
    """
    Match a district name from salary data to a UUID from the districts table
    Returns: (district_id, matched) where matched is True if found in map
    """
    # Normalize the name for matching
    normalized_name = district_name.lower().strip()

    # Direct match
    if normalized_name in district_map:
        return district_map[normalized_name], True

    # Try fuzzy matching - check if any district name contains this or vice versa
    for db_name, district_id in district_map.items():
        if normalized_name in db_name or db_name in normalized_name:
            return district_id, True

    # No match - use the original district_name as fallback
    print(f"  ⚠️  No UUID match for '{district_name}', using name as ID")
    return district_name, False

def pad_number(num, width):
    """Pad a number with leading zeros"""
    return str(num).zfill(width)

def create_items(salary_records, district_map, districts_table_name):
    """
    Create DynamoDB items for the new single-table design

    Structure:
    - Main items: district + schedule + salary entry
    - Metadata items: track available year/period combinations
    """
    items = []
    match_stats = {'matched': 0, 'unmatched': 0}

    # Track all year/period combinations
    year_periods = set()

    # Group by district + year + period to track what we're creating
    schedules_created = defaultdict(set)

    for record in salary_records:
        district_name = record['district_name']
        district_id, matched = match_district_name_to_id(district_name, district_map)

        if matched:
            match_stats['matched'] += 1
        else:
            match_stats['unmatched'] += 1

        school_year = record['school_year']
        period = record['period']
        education = record['education']
        credits = int(record['credits'])
        step = int(record['step'])
        salary = Decimal(str(record['salary']))

        # Pad numbers for proper sorting
        credits_padded = pad_number(credits, 3)
        step_padded = pad_number(step, 2)

        # Track this year/period combination
        year_periods.add((school_year, period))

        # Track schedule created for this district
        schedules_created[district_id].add((school_year, period))

        # Create main item
        # PK: DISTRICT#<districtId>
        # SK: SCHEDULE#<yyyy>#<period>#EDU#<edu>#CR#<credits>#STEP#<step>
        item = {
            'PK': f'DISTRICT#{district_id}',
            'SK': f'SCHEDULE#{school_year}#{period}#EDU#{education}#CR#{credits_padded}#STEP#{step_padded}',

            # Attributes
            'district_id': district_id,
            'district_name': district_name,
            'school_year': school_year,
            'period': period,
            'education': education,
            'credits': credits,
            'step': step,
            'salary': salary,

            # GSI1: Exact match query - find all districts at this edu/credits/step
            # PK: YEAR#<yyyy>#PERIOD#<period>#EDU#<edu>#CR#<credits>#STEP#<step>
            # SK: DISTRICT#<districtId>
            'GSI1PK': f'YEAR#{school_year}#PERIOD#{period}#EDU#{education}#CR#{credits_padded}#STEP#{step_padded}',
            'GSI1SK': f'DISTRICT#{district_id}',

            # GSI2: Fallback query - get all salaries for a district's specific schedule
            # PK: YEAR#<yyyy>#PERIOD#<period>#DISTRICT#<districtId>
            # SK: EDU#<edu>#CR#<credits>#STEP#<step>
            'GSI2PK': f'YEAR#{school_year}#PERIOD#{period}#DISTRICT#{district_id}',
            'GSI2SK': f'EDU#{education}#CR#{credits_padded}#STEP#{step_padded}',
        }

        items.append(item)

    print(f"  ✓ Matched {match_stats['matched']} salary records to district UUIDs")
    if match_stats['unmatched'] > 0:
        print(f"  ⚠️  {match_stats['unmatched']} records not matched (using name as ID)")

    # Create metadata items for year/period tracking
    metadata_items = []
    for school_year, period in sorted(year_periods):
        metadata_item = {
            'PK': 'METADATA#SCHEDULES',
            'SK': f'YEAR#{school_year}#PERIOD#{period}',
            'school_year': school_year,
            'period': period,
            'created_at': datetime.utcnow().isoformat()
        }
        metadata_items.append(metadata_item)

    print(f"  ✓ Created {len(metadata_items)} metadata items for year/period combinations")
    print(f"  ✓ Created schedules for {len(schedules_created)} districts")

    return items + metadata_items

def batch_write_items(table_name, items, description):
    """Write items to DynamoDB in batches"""
    table = dynamodb.Table(table_name)

    print(f"\nWriting {len(items)} items to {table_name}...")

    batch_size = 25
    written = 0
    failed = 0

    for i in range(0, len(items), batch_size):
        batch = items[i:i + batch_size]

        try:
            with table.batch_writer() as writer:
                for item in batch:
                    writer.put_item(Item=item)

            written += len(batch)
            print(f"  Progress: {written}/{len(items)} items written")

        except Exception as e:
            print(f"  ✗ Error writing batch: {e}")
            failed += len(batch)

    print(f"\n✓ {description} complete:")
    print(f"    Written: {written}")
    print(f"    Failed: {failed}")

    return written, failed

def main():
    import sys

    # Get table names from command line or use defaults
    if len(sys.argv) > 1:
        salaries_table = sys.argv[1]
        districts_table = sys.argv[2] if len(sys.argv) > 2 else get_districts_table_name()
    else:
        salaries_table = 'crackpow-schools-teacher-salaries'
        districts_table = get_districts_table_name()
        print(f"Using default table names:")
        print(f"  Salaries: {salaries_table}")
        print(f"  Districts: {districts_table}")
        print(f"\nTo use different tables: python3 load_salary_data.py <salaries_table> <districts_table>\n")

    # Build district name to UUID mapping
    district_map = build_district_name_to_id_map(districts_table)

    # Load data
    print("\nLoading salary data from JSON...")
    salary_records = load_salary_json()
    print(f"✓ Loaded {len(salary_records)} salary records")

    # Create items
    print("\nCreating DynamoDB items...")
    items = create_items(salary_records, district_map, districts_table)
    print(f"✓ Created {len(items)} total items (salary entries + metadata)")

    # Write to DynamoDB
    print(f"\n{'='*80}")
    print("Writing to DynamoDB...")
    print(f"{'='*80}")

    written, failed = batch_write_items(
        salaries_table,
        items,
        "Salary data import"
    )

    # Summary
    print(f"\n{'='*80}")
    print("Summary:")
    print(f"{'='*80}")
    print(f"  Salaries table ({salaries_table}):")
    print(f"    ✓ Written: {written}")
    print(f"    ✗ Failed: {failed}")
    print(f"{'='*80}\n")

if __name__ == '__main__':
    main()