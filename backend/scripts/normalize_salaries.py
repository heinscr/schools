#!/usr/bin/env python3
"""
Normalize salary data by filling in missing entries with calculated values.

This script:
1. Reads METADATA#MAXVALUES to get global max step and edu+credit combos
2. For each district/year/period, fills in missing steps using fallback logic
3. Optionally fills in missing edu+credit combos using cross-education fallback
4. Marks all generated entries with is_calculated=True

Usage:
    python normalize_salaries.py [table_name] [--with-cross-edu-fallback]
"""

import sys
import boto3
from decimal import Decimal
from datetime import datetime
from collections import defaultdict
from pathlib import Path

dynamodb = boto3.resource('dynamodb')

def pad_number(num, width):
    """Pad a number with leading zeros"""
    return str(num).zfill(width)

def get_max_values(table):
    """Get global max values from metadata"""
    print("Reading max values metadata...")

    response = table.get_item(
        Key={'PK': 'METADATA#MAXVALUES', 'SK': 'GLOBAL'}
    )

    if 'Item' not in response:
        raise Exception("METADATA#MAXVALUES not found. Run load_salary_data.py first.")

    item = response['Item']
    max_step_raw = item.get('max_step', 15)
    # DynamoDB may return numbers as Decimal; ensure we have a plain int
    try:
        if isinstance(max_step_raw, Decimal):
            max_step = int(max_step_raw)
        else:
            max_step = int(max_step_raw)
    except Exception:
        max_step = 15

    edu_credit_combos = item.get('edu_credit_combos', [])

    print(f"  max_step: {max_step}")
    print(f"  edu_credit_combos: {len(edu_credit_combos)} combinations (only what exists in data)")

    return max_step, edu_credit_combos

def get_all_year_periods(table):
    """Get all year/period combinations from metadata"""
    print("Reading year/period metadata...")

    response = table.query(
        KeyConditionExpression=boto3.dynamodb.conditions.Key('PK').eq('METADATA#SCHEDULES')
    )

    year_periods = [
        (item['school_year'], item['period'])
        for item in response.get('Items', [])
    ]

    print(f"  Found {len(year_periods)} year/period combinations")
    return year_periods

def get_district_data_for_year_period(table, year, period):
    """
    Get all real salary entries for a specific year/period.
    Returns: dict of district_id -> list of salary entries
    """
    print(f"  Querying salaries for {year}/{period}...")

    # Query using GSI2 is too slow, instead scan the main table filtered
    # Actually, we can use the availability index more efficiently
    response = table.get_item(
        Key={'PK': 'METADATA#AVAILABILITY', 'SK': f'YEAR#{year}#PERIOD#{period}'}
    )

    if 'Item' not in response:
        return {}

    districts_availability = response['Item'].get('districts', {})

    # For each district, query their real entries
    district_data = {}

    for district_id in districts_availability.keys():
        # Query all entries for this district/year/period
        entries_response = table.query(
            IndexName='FallbackQueryIndex',
            KeyConditionExpression=boto3.dynamodb.conditions.Key('GSI2PK').eq(
                f'YEAR#{year}#PERIOD#{period}#DISTRICT#{district_id}'
            )
        )

        # Filter to only real entries (not calculated)
        real_entries = [
            item for item in entries_response.get('Items', [])
            if not item.get('is_calculated', False)
        ]

        if real_entries:
            district_data[district_id] = real_entries

    print(f"    Found {len(district_data)} districts with real data")
    return district_data

def generate_calculated_entries(district_id, district_name, year, period, real_entries, max_step, all_edu_credit_combos):
    """
    Generate calculated entries using matrix fill algorithm.

    Phase 1: Fill down each column (existing edu+credit combos)
        - For each edu+credit combo the district has
        - Fill missing steps 1 to max_step from nearest lower step

    Phase 2: Fill right (missing edu+credit combos)
        - For each missing edu+credit combo
        - Copy from highest available combo to the left (fallback hierarchy)
    """
    calculated_items = []

    # Education/credit hierarchy for fallback
    edu_order = {'B': 1, 'M': 2, 'D': 3}

    # PHASE 1: Fill down each column (existing combos)
    # Group real entries by edu+credit
    by_edu_credit = defaultdict(list)
    for entry in real_entries:
        edu = entry['education']
        cred = entry['credits']
        key = f"{edu}+{cred}"
        by_edu_credit[key].append(entry)

    # Build complete matrix for existing columns
    matrix = {}  # edu_cred_key -> {step -> entry}

    for edu_cred_key, entries in by_edu_credit.items():
        # Parse edu+credit
        parts = edu_cred_key.split('+')
        edu = parts[0]
        cred = int(parts[1])
        cred_padded = pad_number(cred, 3)

        # Build lookup by step
        entries_by_step = {int(e['step']): e for e in entries}
        matrix[edu_cred_key] = {}

        # Fill all steps for this column
        for target_step in range(1, max_step + 1):
            if target_step in entries_by_step:
                # Real entry exists - add to matrix
                matrix[edu_cred_key][target_step] = entries_by_step[target_step]
            else:
                # Find source: highest step <= target_step
                lower_steps = [s for s in entries_by_step.keys() if s <= target_step]
                if lower_steps:
                    source_step = max(lower_steps)
                else:
                    # All steps are higher - use lowest
                    source_step = min(entries_by_step.keys())

                source_entry = entries_by_step[source_step]

                # Create calculated entry
                step_padded = pad_number(target_step, 2)
                calculated_item = {
                    'PK': f'DISTRICT#{district_id}',
                    'SK': f'SCHEDULE#{year}#{period}#EDU#{edu}#CR#{cred_padded}#STEP#{step_padded}',
                    'district_id': district_id,
                    'district_name': district_name,
                    'school_year': year,
                    'period': period,
                    'education': edu,
                    'credits': cred,
                    'step': target_step,
                    'salary': source_entry['salary'],
                    'is_calculated': True,
                    'source_step': source_step,
                    'GSI1PK': f'YEAR#{year}#PERIOD#{period}#EDU#{edu}#CR#{cred_padded}',
                    'GSI1SK': f'STEP#{step_padded}#DISTRICT#{district_id}',
                    'GSI2PK': f'YEAR#{year}#PERIOD#{period}#DISTRICT#{district_id}',
                    'GSI2SK': f'EDU#{edu}#CR#{cred_padded}#STEP#{step_padded}',
                }
                calculated_items.append(calculated_item)
                matrix[edu_cred_key][target_step] = calculated_item

    # PHASE 2: Fill right (missing edu+credit combos)
    # Process missing combos in order (by education level, then by credits low to high)
    # This ensures we can use previously created combos as sources
    missing_combos = [c for c in all_edu_credit_combos if c not in matrix]

    # Sort missing combos by education level, then by credits
    def combo_sort_key(combo):
        parts = combo.split('+')
        edu = parts[0]
        cred = int(parts[1])
        return (edu_order.get(edu, 0), cred)

    missing_combos_sorted = sorted(missing_combos, key=combo_sort_key)

    for missing_combo in missing_combos_sorted:
        # Parse edu+credit
        parts = missing_combo.split('+')
        target_edu = parts[0]
        target_cred = int(parts[1])
        target_cred_padded = pad_number(target_cred, 3)

        # Find best source combo (closest lower credit from same or lower education level)
        # Priority: same education level with highest credit < target, then lower education levels
        best_source = None
        best_source_cred = -1

        for source_combo in matrix.keys():
            source_parts = source_combo.split('+')
            source_edu = source_parts[0]
            source_cred = int(source_parts[1])

            # Check if this is a valid fallback
            # Do not allow using a source from a higher education level
            if edu_order.get(source_edu, 0) > edu_order.get(target_edu, 0):
                continue  # Can't fallback from higher edu

            # Priority: same education level first, then lower education level
            if best_source is None:
                best_source = source_combo
                best_source_cred = source_cred
            else:
                best_parts = best_source.split('+')
                best_edu = best_parts[0]
                best_cred = int(best_parts[1])

                # Prefer same education level over lower education level
                if source_edu == target_edu and best_edu != target_edu:
                    # Source is same edu, best is lower edu -> use source
                    best_source = source_combo
                    best_source_cred = source_cred
                elif source_edu == target_edu and best_edu == target_edu:
                    # Both same edu -> prefer highest credit < target
                    if source_cred < target_cred and source_cred > best_cred:
                        best_source = source_combo
                        best_source_cred = source_cred
                elif source_edu != target_edu and best_edu != target_edu:
                    # Both lower edu -> prefer highest credit
                    if source_cred > best_cred:
                        best_source = source_combo
                        best_source_cred = source_cred

        if not best_source:
            # No valid source found - skip this combo
            continue

        # Copy all steps from source combo and add to matrix
        source_entries = matrix[best_source]
        matrix[missing_combo] = {}  # Create entry in matrix for this new combo

        for step, source_entry in source_entries.items():
            step_padded = pad_number(step, 2)

            # Determine if source was real or calculated
            source_was_calculated = source_entry.get('is_calculated', False)

            calculated_item = {
                'PK': f'DISTRICT#{district_id}',
                'SK': f'SCHEDULE#{year}#{period}#EDU#{target_edu}#CR#{target_cred_padded}#STEP#{step_padded}',
                'district_id': district_id,
                'district_name': district_name,
                'school_year': year,
                'period': period,
                'education': target_edu,
                'credits': target_cred,
                'step': step,
                'salary': source_entry['salary'],
                'is_calculated': True,
                'source_edu_credit': best_source,  # Track where it came from
                'source_step': source_entry.get('source_step') if source_was_calculated else step,
                'GSI1PK': f'YEAR#{year}#PERIOD#{period}#EDU#{target_edu}#CR#{target_cred_padded}',
                'GSI1SK': f'STEP#{step_padded}#DISTRICT#{district_id}',
                'GSI2PK': f'YEAR#{year}#PERIOD#{period}#DISTRICT#{district_id}',
                'GSI2SK': f'EDU#{target_edu}#CR#{target_cred_padded}#STEP#{step_padded}',
            }
            calculated_items.append(calculated_item)
            matrix[missing_combo][step] = calculated_item  # Add to matrix so it can be used as source

    return calculated_items


def batch_write_items(table, items, description):
    """Write items to DynamoDB in batches"""
    if not items:
        print(f"  No items to write for {description}")
        return

    print(f"  Writing {len(items)} items for {description}...")

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
            if written % 500 == 0:
                print(f"    Progress: {written}/{len(items)} items written")

        except Exception as e:
            print(f"    ✗ Error writing batch: {e}")
            failed += len(batch)

    print(f"  ✓ {description} complete: {written} written, {failed} failed")
    return written, failed

def main():
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
        table_name = os.environ.get('DYNAMODB_TABLE_NAME')
        if not table_name:
            print("ERROR: DYNAMODB_TABLE_NAME environment variable not set")
            print("\nUsage:")
            print("  python3 normalize_salaries.py <table_name>")
            print("  OR set environment variable in /backend/.env:")
            print("    DYNAMODB_TABLE_NAME=<table_name>")
            sys.exit(1)
        print(f"Using environment variable from .env: {table_name}\n")

    table = dynamodb.Table(table_name)

    print(f"\n{'='*60}")
    print("SALARY DATA NORMALIZATION")
    print(f"{'='*60}\n")

    # STEP 1: Get max values
    max_step, edu_credit_combos = get_max_values(table)

    # STEP 2: Get all year/periods
    year_periods = get_all_year_periods(table)

    # STEP 3: Process each year/period
    total_calculated = 0
    all_combos_set = set(edu_credit_combos)  # Track all combos (real + calculated)

    for year, period in year_periods:
        print(f"\nProcessing {year}/{period}...")

        # Get district data
        district_data = get_district_data_for_year_period(table, year, period)

        # Generate calculated entries
        all_calculated = []
        for district_id, real_entries in district_data.items():
            district_name = real_entries[0]['district_name'] if real_entries else district_id
            calculated = generate_calculated_entries(
                district_id, district_name, year, period, real_entries, max_step, edu_credit_combos
            )
            all_calculated.extend(calculated)

            # Track combos created
            for entry in calculated:
                combo = f"{entry['education']}+{entry['credits']}"
                all_combos_set.add(combo)

        print(f"  Generated {len(all_calculated)} calculated entries")

        # Write calculated entries
        if all_calculated:
            batch_write_items(table, all_calculated, f"{year}/{period}")
            total_calculated += len(all_calculated)

    print(f"\n{'='*60}")
    print(f"NORMALIZATION COMPLETE")
    print(f"Total calculated entries created: {total_calculated}")
    print(f"{'='*60}\n")

    # STEP 4: Update METADATA#MAXVALUES to include all combos (real + calculated)
    print(f"Updating METADATA#MAXVALUES with all combos (including calculated)...")

    try:
        table.put_item(
            Item={
                'PK': 'METADATA#MAXVALUES',
                'SK': 'GLOBAL',
                'max_step': max_step,
                'edu_credit_combos': sorted(list(all_combos_set)),
                'last_updated': datetime.utcnow().isoformat()
            }
        )
        print(f"✓ METADATA#MAXVALUES updated:")
        print(f"  Original combos: {len(edu_credit_combos)}")
        print(f"  Total combos (including calculated): {len(all_combos_set)}")
        print(f"{'='*60}\n")
    except Exception as e:
        print(f"✗ Error updating METADATA#MAXVALUES: {e}")
        print(f"{'='*60}\n")

if __name__ == '__main__':
    main()