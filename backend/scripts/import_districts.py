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
import subprocess
from pathlib import Path

# Add the backend directory to the path so we can import our modules
backend_path = Path(__file__).parent.parent
sys.path.insert(0, str(backend_path))

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
        ('regional_academic', 'Regional Academic', 'regional_academic'),
        ('regional_vocational', 'Regional Vocational', 'regional_vocational'),
        ('county_agricultural', 'County Agricultural', 'county_agricultural'),
        ('other_districts', 'Other Districts', None),
        ('charter', 'Charter', "charter")
    ]

    for category_key, category_name, type_value in categories:
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

            # Determine district_type
            if type_value:
                district_type = type_value
            else:
                # For other_districts, use the 'type' field in the data, default to 'municipal'
                district_type = district_data.get('type', 'municipal')

            if not name:
                print(f"  ⚠️  Skipping district with no name: {district_data}")
                stats['skipped'] += 1
                continue

            # Create the district object
            district_create = DistrictCreate(
                name=name,
                main_address=address if address else None,
                towns=members if members else [],
                district_type=district_type
            )

            if dry_run:
                print(f"  [DRY RUN] Would import/update: {name}")
                print(f"    Address: {address or 'N/A'}")
                print(f"    Towns: {', '.join(members) if members else 'N/A'}")
                print(f"    Type: {district_type}")
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
                            towns=members if members else [],
                            district_type=district_type
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
        default='../../data/districts.json',
        help='Path to the districts.json file (default: ../../data/districts.json)'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Perform a dry run without actually importing data'
    )
    parser.add_argument(
        '--no-prompt',
        action='store_true',
        help='Skip the prompt to load salary data after import'
    )

    args = parser.parse_args()

    # Resolve the file path
    script_dir = Path(__file__).parent
    json_file = script_dir / args.file
    if not json_file.exists():
        print(f"Error: File not found: {json_file}")
        sys.exit(1)

    # Run the import
    try:
        stats = import_districts(str(json_file), dry_run=args.dry_run)

        # Exit with error code if there were failures
        if stats['failed'] > 0:
            sys.exit(1)
        
        # If successful and not a dry run, prompt to load salary data
        if not args.dry_run and not args.no_prompt and stats['success'] > 0:
            print(f"\n{'='*60}")
            print("Districts import completed successfully!")
            print(f"{'='*60}")
            
            # Check if load_salary_data.py exists
            salary_script = script_dir / 'load_salary_data.py'
            if salary_script.exists():
                response = input("\nWould you like to load salary data now? (y/n): ").strip().lower()
                
                if response == 'y':
                    print(f"\n{'='*60}")
                    print("Running load_salary_data.py...")
                    print(f"{'='*60}\n")
                    
                    try:
                        # Run the salary data loading script
                        result = subprocess.run(
                            [sys.executable, str(salary_script)],
                            cwd=str(script_dir),
                            check=False
                        )
                        
                        if result.returncode == 0:
                            print(f"\n{'='*60}")
                            print("✓ Salary data loaded successfully!")
                            print(f"{'='*60}\n")
                        else:
                            print(f"\n{'='*60}")
                            print("✗ Salary data loading encountered errors.")
                            print(f"{'='*60}\n")
                            sys.exit(1)
                            
                    except Exception as e:
                        print(f"\n✗ Error running load_salary_data.py: {e}")
                        sys.exit(1)
                else:
                    print("\nSkipping salary data loading.")
                    print("You can load salary data later by running:")
                    print(f"  python3 {salary_script}\n")

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
