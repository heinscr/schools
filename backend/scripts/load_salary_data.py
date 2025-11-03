#!/usr/bin/env python3
"""
Load salary data from JSON into DynamoDB tables
Creates both normalized (main) and aggregated (cache) tables
"""

import json
import boto3
from pathlib import Path
from collections import defaultdict
from decimal import Decimal
from boto3.dynamodb.conditions import Attr

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
    with open(json_path, 'r') as f:
        return json.load(f)

def get_district_type_from_table(district_id, districts_table_name):
    """
    Get district type from DynamoDB districts table using the UUID
    """
    try:
        table = dynamodb.Table(districts_table_name)
        response = table.get_item(
            Key={
                'PK': f'DISTRICT#{district_id}',
                'SK': 'METADATA'
            }
        )
        
        if 'Item' in response:
            return response['Item'].get('district_type', 'unknown')
        
        return 'unknown'
    except Exception as e:
        print(f"  ⚠️  Error looking up district type for {district_id}: {e}")
        return 'unknown'


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

def create_normalized_items(salary_records, district_map, districts_table_name):
    """
    Create normalized DynamoDB items (one per salary cell)
    Structure: district_id + composite_key
    """
    items = []
    match_stats = {'matched': 0, 'unmatched': 0}

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
        credits = record['credits']
        step = record['step']
        salary = Decimal(str(record['salary']))

        # Create composite key
        composite_key = f"{school_year}#{period}#{education}#{credits}#{step}"

        # Get district type from DynamoDB
        district_type = get_district_type_from_table(district_id, districts_table_name)

        # Create item - use the UUID as district_id
        item = {
            'district_id': district_id,  # This is now the UUID
            'composite_key': composite_key,
            'school_year': school_year,
            'period': period,
            'education': education,
            'credits': credits,
            'step': step,
            'salary': salary,
            'district_name': district_name,
            'district_type': district_type,

            # GSI1: For querying by type/year
            'GSI1PK': f"SALARY#{school_year}#{district_type}",
            'GSI1SK': f"{education}#{credits}#{step}#{salary}",

            # GSI2: For comparing all districts at specific education/credits/step
            'GSI2PK': f"COMPARE#{education}#{credits}#{step}",
            'GSI2SK': f"{salary}#{district_id}"
        }

        items.append(item)
    
    print(f"  ✓ Matched {match_stats['matched']} districts to UUIDs")
    if match_stats['unmatched'] > 0:
        print(f"  ⚠️  {match_stats['unmatched']} districts not matched (using name as ID)")

    return items

def create_aggregated_items(salary_records, district_map, districts_table_name):
    """
    Create aggregated DynamoDB items (one per schedule)
    Groups salaries by district + year + period
    New structure: each salary is a flat record with step, education, credits, salary
    """
    # Group by district + year + period
    schedules = defaultdict(lambda: {
        'district_id': None,
        'district_name': None,
        'district_type': None,
        'school_year': None,
        'period': None,
        'salaries': []  # List of salary records
    })

    for record in salary_records:
        district_name = record['district_name']
        district_id, matched = match_district_name_to_id(district_name, district_map)
        
        key = f"{district_id}#{record['school_year']}#{record['period']}"

        schedule = schedules[key]
        schedule['district_id'] = district_id  # Use UUID
        schedule['district_name'] = district_name
        schedule['school_year'] = record['school_year']
        schedule['period'] = record['period']
        schedule['district_type'] = get_district_type_from_table(district_id, districts_table_name)

        # Add salary record with all info
        schedule['salaries'].append({
            'step': record['step'],
            'education': record['education'],
            'credits': record['credits'],
            'salary': Decimal(str(record['salary']))
        })

    # Convert to list of items
    items = []
    for key, schedule in schedules.items():
        # Sort salaries: by step first, then education (B->M->D), then credits
        edu_order = {'B': 1, 'M': 2, 'D': 3}
        sorted_salaries = sorted(
            schedule['salaries'],
            key=lambda x: (x['step'], edu_order.get(x['education'], 99), x['credits'])
        )

        item = {
            'district_id': schedule['district_id'],
            'schedule_key': f"{schedule['school_year']}#{schedule['period']}",
            'district_name': schedule['district_name'],
            'district_type': schedule['district_type'],
            'school_year': schedule['school_year'],
            'period': schedule['period'],
            'salaries': sorted_salaries,
            'contract_term': None,  # To be filled in later
            'contract_expiration': None,  # To be filled in later
            'notes': None  # To be filled in later
        }

        items.append(item)

    return items

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
    if len(sys.argv) > 2:
        salaries_table = sys.argv[1]
        schedules_table = sys.argv[2]
        districts_table = sys.argv[3] if len(sys.argv) > 3 else get_districts_table_name()
    else:
        salaries_table = 'crackpow-schools-teacher-salaries'
        schedules_table = 'crackpow-schools-teacher-salary-schedules'
        districts_table = get_districts_table_name()
        print(f"Using default table names:")
        print(f"  Salaries: {salaries_table}")
        print(f"  Schedules: {schedules_table}")
        print(f"  Districts: {districts_table}")
        print(f"\nTo use different tables: python3 load_salary_data.py <salaries_table> <schedules_table> <districts_table>\n")

    # Build district name to UUID mapping
    district_map = build_district_name_to_id_map(districts_table)

    # Load data
    print("\nLoading salary data from JSON...")
    salary_records = load_salary_json()
    print(f"✓ Loaded {len(salary_records)} salary records")

    # Create normalized items
    print("\nCreating normalized items...")
    normalized_items = create_normalized_items(salary_records, district_map, districts_table)
    print(f"✓ Created {len(normalized_items)} normalized items")

    # Create aggregated items
    print("\nCreating aggregated schedule items...")
    aggregated_items = create_aggregated_items(salary_records, district_map, districts_table)
    print(f"✓ Created {len(aggregated_items)} schedule items")

    # Write to DynamoDB
    print(f"\n{'='*80}")
    print("Writing to DynamoDB...")
    print(f"{'='*80}")

    # Write normalized items
    written1, failed1 = batch_write_items(
        salaries_table,
        normalized_items,
        "Normalized items"
    )

    # Write aggregated items
    written2, failed2 = batch_write_items(
        schedules_table,
        aggregated_items,
        "Schedule items"
    )

    # Summary
    print(f"\n{'='*80}")
    print("Summary:")
    print(f"{'='*80}")
    print(f"  Normalized table ({salaries_table}):")
    print(f"    ✓ Written: {written1}")
    print(f"    ✗ Failed: {failed1}")
    print(f"\n  Schedule table ({schedules_table}):")
    print(f"    ✓ Written: {written2}")
    print(f"    ✗ Failed: {failed2}")
    print(f"{'='*80}\n")

if __name__ == '__main__':
    main()
