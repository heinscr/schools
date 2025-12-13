#!/usr/bin/env python3
"""
Diagnose 2025-2026 data issue
"""

import os
import sys
from pathlib import Path
import boto3
from dotenv import load_dotenv
from boto3.dynamodb.conditions import Key, Attr

# Load environment variables
backend_dir = Path(__file__).parent.parent
env_path = backend_dir / '.env'
load_dotenv(dotenv_path=env_path)

table_name = os.environ.get('DYNAMODB_TABLE_NAME')
aws_region = os.environ.get('AWS_REGION', 'us-east-1')

if not table_name:
    print("ERROR: DYNAMODB_TABLE_NAME not set")
    sys.exit(1)

dynamodb = boto3.resource('dynamodb', region_name=aws_region)
table = dynamodb.Table(table_name)

print(f"Diagnosing 2025-2026 Full Year data in {table_name}...\n")

# Get availability metadata
response = table.get_item(
    Key={
        'PK': 'METADATA#AVAILABILITY',
        'SK': 'YEAR#2025-2026#PERIOD#Full Year'
    }
)

if 'Item' not in response:
    print("❌ No METADATA#AVAILABILITY found for 2025-2026 Full Year")
    print("This means no salary data has been uploaded for this year/period")
    sys.exit(1)

availability = response['Item']
districts_with_data = availability.get('districts', {})
district_ids = list(districts_with_data.keys())

print(f"✓ Found {len(district_ids)} districts with salary data for 2025-2026\n")
print(f"District IDs: {district_ids[:10]}{'...' if len(district_ids) > 10 else ''}\n")

# Get district details
print("Fetching district details...\n")

district_types = {}
for district_id in district_ids:
    response = table.get_item(
        Key={
            'PK': f'DISTRICT#{district_id}',
            'SK': 'METADATA'
        }
    )

    if 'Item' in response:
        district = response['Item']
        dtype = district.get('district_type', 'unknown')
        name = district.get('name', district_id)
        district_types[dtype] = district_types.get(dtype, 0) + 1

        # Show first few
        if len([d for d in district_types.values()]) <= 15:
            print(f"  - {name}: {dtype}")

print(f"\n{'='*60}")
print("SUMMARY:")
print(f"{'='*60}")
print(f"Total districts with 2025-2026 data: {len(district_ids)}")
print(f"\nBreakdown by type:")
for dtype, count in sorted(district_types.items()):
    print(f"  - {dtype}: {count}")

print(f"\n{'='*60}")
print("Expected vs Actual:")
print(f"{'='*60}")

# Get all regional/municipal districts
all_response = table.scan(
    FilterExpression=Attr('entity_type').eq('district')
)

all_districts = all_response['Items']
while 'LastEvaluatedKey' in all_response:
    all_response = table.scan(
        FilterExpression=Attr('entity_type').eq('district'),
        ExclusiveStartKey=all_response['LastEvaluatedKey']
    )
    all_districts.extend(all_response['Items'])

regional_municipal = [
    d for d in all_districts
    if d.get('district_type', '').lower() in ['regional_academic', 'municipal']
]

print(f"Total Regional/Municipal districts in system: {len(regional_municipal)}")
print(f"Regional/Municipal with 2025-2026 data: {district_types.get('regional_academic', 0) + district_types.get('municipal', 0)}")
print(f"Missing: {len(regional_municipal) - (district_types.get('regional_academic', 0) + district_types.get('municipal', 0))}")

print(f"\n{'='*60}")
if len(district_ids) == 156:
    print("✓ All 156 districts have data uploaded")
    print("⚠️  But only a few are Regional/Municipal type")
    print("\nAction needed: Check if district types are set correctly")
elif len(district_ids) < 156:
    print(f"⚠️  Only {len(district_ids)} districts have data")
    print(f"Missing: {156 - len(district_ids)} districts")
    print("\nAction needed: Re-upload missing district data")
