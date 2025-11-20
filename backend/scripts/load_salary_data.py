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
from datetime import datetime, UTC

# Initialize DynamoDB
dynamodb = boto3.resource('dynamodb')

def build_district_name_to_id_map(table_name):
    """
    Query the table and build a mapping of district names to UUIDs
    Returns dict: {district_name_lower: district_id}
    """
    print(f"\nQuerying districts from table: {table_name}...")
    table = dynamodb.Table(table_name)

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

def pad_salary(salary):
    """
    Pad salary for lexicographic sorting in DynamoDB GSI
    Converts to integer cents and pads to 10 digits (supports up to $9,999,999.99)
    Inverted for descending sort (higher salaries first)
    """
    # Convert to cents as integer
    if isinstance(salary, Decimal):
        cents = int(salary * 100)
    else:
        cents = int(float(salary) * 100)

    # Invert for descending sort: subtract from max value
    # Max value: 9999999999 (10 digits, ~$100M)
    inverted = 9999999999 - cents

    return str(inverted).zfill(10)

def create_items(salary_records, district_map, table_name):
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

    # Track availability: year_period -> district_id -> edu+credit -> max_step
    availability_tracker = defaultdict(lambda: defaultdict(lambda: defaultdict(lambda: {'max_step': 0})))

    # Track global maximums for normalization
    global_max_step = 0
    global_edu_credit_combos = set()  # Only track combos that actually exist in data

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
        salary_padded = pad_salary(salary)

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

            # GSI1: Education/Credits query with step sorting
            # PK: YEAR#<yyyy>#PERIOD#<period>#EDU#<edu>#CR#<credits>
            # SK: STEP#<step>#DISTRICT#<districtId>
            'GSI1PK': f'YEAR#{school_year}#PERIOD#{period}#EDU#{education}#CR#{credits_padded}',
            'GSI1SK': f'STEP#{step_padded}#DISTRICT#{district_id}',

            # GSI2: Fallback query - get all salaries for a district's specific schedule
            # PK: YEAR#<yyyy>#PERIOD#<period>#DISTRICT#<districtId>
            # SK: EDU#<edu>#CR#<credits>#STEP#<step>
            'GSI2PK': f'YEAR#{school_year}#PERIOD#{period}#DISTRICT#{district_id}',
            'GSI2SK': f'EDU#{education}#CR#{credits_padded}#STEP#{step_padded}',

            # GSI5: Fast comparison queries - single query for all districts (Option 2 optimization)
            # PK: EDU#<edu>#CR#<credits>#STEP#<step>
            # SK: SALARY#<salary_padded>#YEAR#<yyyy>#DISTRICT#<districtId>
            'GSI_COMP_PK': f'EDU#{education}#CR#{credits_padded}#STEP#{step_padded}',
            'GSI_COMP_SK': f'SALARY#{salary_padded}#YEAR#{school_year}#DISTRICT#{district_id}',
        }

        items.append(item)

        # Track availability for this year/period/district/edu+credit combo
        year_period_key = (school_year, period)
        edu_credit_key = f'{education}+{credits}'

        # Update max step for this combo
        current_max = availability_tracker[year_period_key][district_id][edu_credit_key]['max_step']
        availability_tracker[year_period_key][district_id][edu_credit_key]['max_step'] = max(current_max, step)

        # Track global maximums
        global_max_step = max(global_max_step, step)
        global_edu_credit_combos.add(edu_credit_key)

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
            'created_at': datetime.now(UTC).isoformat()
        }
        metadata_items.append(metadata_item)

    print(f"  ✓ Created {len(metadata_items)} metadata items for year/period combinations")
    print(f"  ✓ Created schedules for {len(schedules_created)} districts")

    # Create availability index metadata items
    availability_items = []
    for year_period_key, districts_data in availability_tracker.items():
        school_year, period = year_period_key

        # Convert nested dict to simpler structure for DynamoDB
        districts_availability = {}
        for district_id, edu_credits in districts_data.items():
            districts_availability[district_id] = dict(edu_credits)

        availability_item = {
            'PK': 'METADATA#AVAILABILITY',
            'SK': f'YEAR#{school_year}#PERIOD#{period}',
            'school_year': school_year,
            'period': period,
            'districts': districts_availability,
            'created_at': datetime.now(UTC).isoformat()
        }
        availability_items.append(availability_item)

    print(f"  ✓ Created {len(availability_items)} availability index items")

    # Create max values metadata item for normalization
    max_values_item = {
        'PK': 'METADATA#MAXVALUES',
        'SK': 'GLOBAL',
        'max_step': global_max_step,
        'edu_credit_combos': sorted(list(global_edu_credit_combos)),  # Only combos that exist in data
        'last_updated': datetime.now(UTC).isoformat()
    }

    print(f"  ✓ Created max values metadata:")
    print(f"    max_step: {global_max_step}")
    print(f"    edu_credit_combos: {len(global_edu_credit_combos)} combinations")

    return items + metadata_items + availability_items + [max_values_item]

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
    import os
    from dotenv import load_dotenv

    # Load environment variables from /backend/.env file
    backend_dir = Path(__file__).parent.parent
    env_path = backend_dir / '.env'
    load_dotenv(dotenv_path=env_path)

    # Get table name from command line or environment variable
    if len(sys.argv) > 1:
        table_name = sys.argv[1]
    else:
        # Try to get from environment variable
        table_name = os.environ.get('DYNAMODB_TABLE_NAME')

        if not table_name:
            print("ERROR: Required environment variable not set")
            print("\nUsage:")
            print("  python3 load_salary_data.py <table_name>")
            print("  OR set environment variable in /backend/.env:")
            print("    DYNAMODB_TABLE_NAME=<table_name>")
            sys.exit(1)

        print(f"Using environment variable from .env:")
        print(f"  Table: {table_name}")
        print()

    # Build district name to UUID mapping
    district_map = build_district_name_to_id_map(table_name)

    # Load data
    print("\nLoading salary data from JSON...")
    salary_records = load_salary_json()
    print(f"✓ Loaded {len(salary_records)} salary records")

    # Create items
    print("\nCreating DynamoDB items...")
    items = create_items(salary_records, district_map, table_name)
    print(f"✓ Created {len(items)} total items (salary entries + metadata)")

    # Write to DynamoDB
    print(f"\n{'='*80}")
    print("Writing to DynamoDB...")
    print(f"{'='*80}")

    written, failed = batch_write_items(
        table_name,
        items,
        "Salary data import"
    )

    # Summary
    print(f"\n{'='*80}")
    print("Summary:")
    print(f"{'='*80}")
    print(f"  Table ({table_name}):")
    print(f"    ✓ Written: {written}")
    print(f"    ✗ Failed: {failed}")
    print(f"{'='*80}\n")

    # Run normalization
    if written > 0 and failed == 0:
        print(f"\n{'='*80}")
        print("Running normalization to fill complete salary matrix...")
        print(f"{'='*80}\n")

        import subprocess
        import os

        # Get the directory where this script is located
        script_dir = os.path.dirname(os.path.abspath(__file__))
        normalize_script = os.path.join(script_dir, 'normalize_salaries.py')

        try:
            # Call normalize_salaries.py with the same table name
            result = subprocess.run(
                [sys.executable, normalize_script, table_name],
                check=True,
                capture_output=False
            )
            print(f"\n{'='*80}")
            print("✓ Normalization complete!")
            print(f"{'='*80}\n")
        except subprocess.CalledProcessError as e:
            print(f"\n{'='*80}")
            print(f"✗ Normalization failed with exit code {e.returncode}")
            print(f"{'='*80}\n")
            sys.exit(1)
    else:
        print("\n⚠️  Skipping normalization due to write failures")
        print("    Please fix errors and run normalize_salaries.py manually\n")

if __name__ == '__main__':
    main()