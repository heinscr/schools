#!/usr/bin/env python3
"""
Sync script to list contract PDFs in S3 and update DynamoDB.

This script:
1. Lists all PDFs in the contracts/district_pdfs/ folder in S3
2. For each PDF, extracts the district name from the filename
3. Looks up the district by name using GSI_METADATA
4. Updates the district's METADATA record with the contract_pdf S3 key

Usage:
    python scripts/sync_contract_pdfs.py
"""
import os
import sys
import json
import subprocess
import boto3
from botocore.exceptions import ClientError
from dotenv import load_dotenv

# Add parent directory to path so we can import from backend
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from database import get_table

# Load environment variables
load_dotenv()


def get_terraform_output(output_name):
    """Get a Terraform output value"""
    try:
        terraform_dir = os.path.join(
            os.path.dirname(__file__),
            '..',
            '..',
            'infrastructure',
            'terraform'
        )

        result = subprocess.run(
            ['terraform', 'output', '-json', output_name],
            cwd=terraform_dir,
            capture_output=True,
            text=True,
            check=True
        )

        # Terraform output -json returns the value directly
        return json.loads(result.stdout)
    except (subprocess.CalledProcessError, FileNotFoundError, json.JSONDecodeError) as e:
        print(f"Warning: Could not retrieve Terraform output '{output_name}': {e}")
        return None


# Configuration
S3_BUCKET = os.getenv('S3_BUCKET_NAME')

# If S3_BUCKET_NAME not in env, try to get from Terraform
if not S3_BUCKET:
    print("S3_BUCKET_NAME not set in environment, attempting to retrieve from Terraform outputs...")
    S3_BUCKET = get_terraform_output('s3_bucket')
    if S3_BUCKET:
        print(f"Retrieved S3 bucket from Terraform: {S3_BUCKET}")

CONTRACT_PDF_PREFIX = 'contracts/district_pdfs/'

s3_client = boto3.client('s3')


def list_contract_pdfs():
    """List all contract PDFs in S3"""
    try:
        paginator = s3_client.get_paginator('list_objects_v2')
        pages = paginator.paginate(Bucket=S3_BUCKET, Prefix=CONTRACT_PDF_PREFIX)

        pdf_files = []
        for page in pages:
            if 'Contents' not in page:
                continue

            for obj in page['Contents']:
                key = obj['Key']
                # Skip the prefix itself (directory marker)
                if key == CONTRACT_PDF_PREFIX:
                    continue

                # Only process .pdf files
                if key.lower().endswith('.pdf'):
                    pdf_files.append(key)

        return pdf_files

    except ClientError as e:
        print(f"Error listing S3 objects: {e}")
        return []


def extract_district_name_from_key(s3_key):
    """Extract district name from S3 key"""
    # Remove prefix and .pdf extension
    # e.g., "contracts/district_pdfs/Springfield.pdf" -> "Springfield"
    filename = s3_key.replace(CONTRACT_PDF_PREFIX, '')
    district_name = filename.replace('.pdf', '')
    return district_name


def lookup_district_by_name(table, district_name):
    """Look up district by name using GSI_METADATA"""
    try:
        response = table.query(
            IndexName='GSI_METADATA',
            KeyConditionExpression='SK = :sk AND name_lower = :name_lower',
            ExpressionAttributeValues={
                ':sk': 'METADATA',
                ':name_lower': district_name.lower()
            },
            Limit=1
        )

        if response.get('Items'):
            return response['Items'][0]
        return None

    except ClientError as e:
        print(f"Error querying DynamoDB for district '{district_name}': {e}")
        return None


def update_district_contract_pdf(table, district_id, s3_key):
    """Update district metadata with contract_pdf field"""
    try:
        pk = f"DISTRICT#{district_id}"
        sk = "METADATA"

        table.update_item(
            Key={'PK': pk, 'SK': sk},
            UpdateExpression='SET contract_pdf = :contract_pdf',
            ExpressionAttributeValues={
                ':contract_pdf': s3_key
            }
        )
        return True

    except ClientError as e:
        print(f"Error updating DynamoDB for district '{district_id}': {e}")
        return False


def main():
    """Main sync logic"""
    if not S3_BUCKET:
        print("Error: S3_BUCKET_NAME environment variable not set")
        sys.exit(1)

    print(f"Syncing contract PDFs from s3://{S3_BUCKET}/{CONTRACT_PDF_PREFIX}")
    print("-" * 80)

    # Get DynamoDB table
    table = get_table()

    # List all contract PDFs in S3
    pdf_files = list_contract_pdfs()

    if not pdf_files:
        print("No contract PDFs found in S3")
        return

    print(f"Found {len(pdf_files)} contract PDF(s) in S3\n")

    # Process each PDF
    updated_count = 0
    not_found_count = 0
    error_count = 0

    for s3_key in pdf_files:
        district_name = extract_district_name_from_key(s3_key)
        print(f"Processing: {district_name}")
        print(f"  S3 Key: {s3_key}")
        print(f"  Searching for name_lower: '{district_name.lower()}'")

        # Look up district by name
        district = lookup_district_by_name(table, district_name)

        if not district:
            print(f"  ❌ District not found in database")
            print(f"     (Searched for name_lower='{district_name.lower()}')")
            not_found_count += 1
            print()
            continue

        district_id = district['PK'].replace('DISTRICT#', '')
        print(f"  District ID: {district_id}")

        # Update district metadata
        success = update_district_contract_pdf(table, district_id, s3_key)

        if success:
            print(f"  ✅ Updated contract_pdf in DynamoDB")
            updated_count += 1
        else:
            print(f"  ❌ Failed to update DynamoDB")
            error_count += 1

        print()

    # Summary
    print("-" * 80)
    print("Sync Summary:")
    print(f"  Total PDFs found: {len(pdf_files)}")
    print(f"  Successfully updated: {updated_count}")
    print(f"  Districts not found: {not_found_count}")
    print(f"  Errors: {error_count}")


if __name__ == '__main__':
    main()
