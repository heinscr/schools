#!/usr/bin/env python3
"""
Import districts from data/districts.json into DynamoDB.

This script reads the districts.json file and imports all districts
(regional academic, regional vocational, county agricultural, and other districts)
into the DynamoDB table using the DynamoDBDistrictService.
"""

import json
import os
import sys
from pathlib import Path

# Add the backend directory to the path so we can import our modules
sys.path.insert(0, str(Path(__file__).parent))

from services.dynamodb_district_service import DynamoDBDistrictService
from schemas import DistrictCreate
from database import districts_table


def load_districts_json(filepath: str) -> dict:
    """Load and parse the districts JSON file."""
    with open(filepath, 'r', encoding='utf-8') as f:
        return json.load(f)


def import_districts(json_filepath: str, dry_run: bool = False):
    """
    Import all districts from the JSON file into DynamoDB.

    Args:
        json_filepath: Path to the districts.json file
        dry_run: If True, only print what would be imported without actually importing
    """
    # Load the JSON data
    print(f"Loading districts from {json_filepath}...")
    data = load_districts_json(json_filepath)

    # Track statistics
    stats = {
        'total': 0,
        'success': 0,
        'failed': 0,
        'skipped': 0
    }

    # Process each category of districts
    categories = [
        ('regional_academic', 'Regional Academic'),
        ('regional_vocational', 'Regional Vocational'),
        ('county_agricultural', 'County Agricultural'),
        ('other_districts', 'Other Districts')
    ]

    for category_key, category_name in categories:
        if category_key not in data:
            continue

        districts = data[category_key]
        print(f"\n{'='*60}")
        print(f"Processing {category_name}: {len(districts)} districts")
        print(f"{'='*60}")

        for district_data in districts:
            stats['total'] += 1

            # Extract fields
            name = district_data.get('district', '').strip()
            address = district_data.get('address', '').strip()
            members = district_data.get('members', [])

            if not name:
                print(f"  ⚠️  Skipping district with no name: {district_data}")
                stats['skipped'] += 1
                continue

            # Create the district object
            district_create = DistrictCreate(
                name=name,
                main_address=address if address else None,
                towns=members if members else []
            )

            if dry_run:
                print(f"  [DRY RUN] Would import/update: {name}")
                print(f"    Address: {address or 'N/A'}")
                print(f"    Towns: {', '.join(members) if members else 'N/A'}")
                stats['success'] += 1
            else:
                try:
                    # Check if district exists by name (case-insensitive)
                    existing, _ = DynamoDBDistrictService.get_districts(
                        districts_table, name=name, limit=1, offset=0
                    )
                    if existing:
                        # Update existing
                        district_id = existing[0]['id']
                        from schemas import DistrictUpdate
                        update_data = DistrictUpdate(
                            name=name,
                            main_address=address if address else None,
                            towns=members if members else []
                        )
                        DynamoDBDistrictService.update_district(districts_table, district_id, update_data)
                        print(f"  ✓ Updated: {name} (ID: {district_id})")
                    else:
                        # Create new
                        result = DynamoDBDistrictService.create_district(districts_table, district_create)
                        print(f"  ✓ Imported: {name} (ID: {result['id']})")
                    stats['success'] += 1
                except Exception as e:
                    print(f"  ✗ Failed to import/update {name}: {str(e)}")
                    stats['failed'] += 1

    # Print summary
    print(f"\n{'='*60}")
    print("Import Summary")
    print(f"{'='*60}")
    print(f"Total districts processed: {stats['total']}")
    print(f"Successfully imported: {stats['success']}")
    print(f"Failed: {stats['failed']}")
    print(f"Skipped: {stats['skipped']}")
    print(f"{'='*60}")

    if dry_run:
        print("\nThis was a DRY RUN. No data was actually imported.")
        print("Run without --dry-run to perform the actual import.")

    return stats


def main():
    """Main entry point for the import script."""
    import argparse

    parser = argparse.ArgumentParser(
        description='Import districts from JSON file into DynamoDB'
    )
    parser.add_argument(
        '--file',
        type=str,
        default='../data/districts.json',
        help='Path to the districts.json file (default: ../data/districts.json)'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Perform a dry run without actually importing data'
    )

    args = parser.parse_args()

    # Resolve the file path
    json_file = Path(__file__).parent / args.file
    if not json_file.exists():
        print(f"Error: File not found: {json_file}")
        sys.exit(1)

    # Run the import
    try:
        stats = import_districts(str(json_file), dry_run=args.dry_run)

        # Exit with error code if there were failures
        if stats['failed'] > 0:
            sys.exit(1)

    except KeyboardInterrupt:
        print("\n\nImport interrupted by user.")
        sys.exit(1)
    except Exception as e:
        print(f"\n\nError during import: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
