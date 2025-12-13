#!/usr/bin/env python3
"""
Check how many backup files exist in S3
"""

import os
import sys
from pathlib import Path
import boto3
from dotenv import load_dotenv

# Load environment variables from backend/.env
backend_dir = Path(__file__).parent.parent
env_path = backend_dir / '.env'
load_dotenv(dotenv_path=env_path)

# Get configuration
bucket_name = os.environ.get('S3_BUCKET_NAME')
aws_region = os.environ.get('AWS_REGION', 'us-east-1')

if not bucket_name:
    print("ERROR: S3_BUCKET_NAME not set in backend/.env")
    sys.exit(1)

# Initialize S3
s3_client = boto3.client('s3', region_name=aws_region)

print(f"Checking backup files in s3://{bucket_name}/contracts/applied_data/...\n")

try:
    # List all backup files
    response = s3_client.list_objects_v2(
        Bucket=bucket_name,
        Prefix='contracts/applied_data/'
    )

    if 'Contents' not in response:
        print("❌ No backup files found!")
        sys.exit(0)

    files = [obj['Key'] for obj in response['Contents'] if obj['Key'].endswith('.json')]

    print(f"✓ Found {len(files)} backup JSON files\n")

    if len(files) > 0:
        print("First 10 files:")
        for f in sorted(files[:10]):
            filename = f.split('/')[-1]
            print(f"  - {filename}")

        if len(files) > 10:
            print(f"  ... and {len(files) - 10} more")

    print(f"\nTotal backup files: {len(files)}")
    print(f"Expected: 156 (one per district)")

    if len(files) < 156:
        print(f"\n⚠️  Missing {156 - len(files)} backup files!")
        print("This means not all districts have backups.")
    elif len(files) == 156:
        print("\n✓ All 156 districts have backup files")

except Exception as e:
    print(f"Error accessing S3: {e}")
    sys.exit(1)
