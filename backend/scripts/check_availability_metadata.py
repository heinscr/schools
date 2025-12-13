#!/usr/bin/env python3
"""
Quick diagnostic script to check METADATA#AVAILABILITY entries
"""

import os
import sys
from pathlib import Path
import boto3
from dotenv import load_dotenv
from boto3.dynamodb.conditions import Key

# Load environment variables from backend/.env
backend_dir = Path(__file__).parent.parent
env_path = backend_dir / '.env'
load_dotenv(dotenv_path=env_path)

# Get configuration
table_name = os.environ.get('DYNAMODB_TABLE_NAME')
aws_region = os.environ.get('AWS_REGION', 'us-east-1')

if not table_name:
    print("ERROR: DYNAMODB_TABLE_NAME not set in backend/.env")
    sys.exit(1)

# Initialize DynamoDB
dynamodb = boto3.resource('dynamodb', region_name=aws_region)
table = dynamodb.Table(table_name)

print(f"Checking METADATA#AVAILABILITY entries in {table_name}...\n")

# Query all METADATA#AVAILABILITY items
response = table.query(
    KeyConditionExpression=Key('PK').eq('METADATA#AVAILABILITY')
)

items = response.get('Items', [])

if not items:
    print("❌ No METADATA#AVAILABILITY entries found!")
    print("\nThis means the availability metadata hasn't been created.")
    print("You may need to re-run the salary data upload or normalization.")
else:
    print(f"✓ Found {len(items)} METADATA#AVAILABILITY entries:\n")

    for item in sorted(items, key=lambda x: x.get('SK', '')):
        sk = item.get('SK', '')
        year = item.get('school_year', 'N/A')
        period = item.get('period', 'N/A')
        districts = item.get('districts', {})
        num_districts = len(districts)

        print(f"  SK: {sk}")
        print(f"    Year: {year}")
        print(f"    Period: {period}")
        print(f"    Districts with data: {num_districts}")

        # Check if this is 2025-2026
        if '2025-2026' in sk:
            print(f"    ⭐ This is the 2025-2026 entry")
            if 'Full Year' in sk:
                print(f"    ✓ Period is 'Full Year' (correct)")
            else:
                print(f"    ⚠️  Period is not 'Full Year' in SK")

        print()

print("\nTo check if districts are Regional/Municipal:")
print("  Use the Districts admin page to see district types")
print("\nIf the METADATA#AVAILABILITY for 2025-2026 Full Year is missing or has wrong period:")
print("  1. Check if salary data was uploaded with 'Full Year' period")
print("  2. Re-run the normalization script if needed")
