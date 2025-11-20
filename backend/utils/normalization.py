"""
Shared normalization utilities for salary data
Used by both the normalizer Lambda and the salary_jobs service
"""
from decimal import Decimal
from typing import Dict, List
from collections import defaultdict


def pad_number(num: int, width: int) -> str:
    """Pad a number with leading zeros"""
    return str(num).zfill(width)


def pad_salary(salary) -> str:
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


def generate_calculated_entries(
    district_id: str,
    district_name: str,
    year: str,
    period: str,
    real_entries: List[Dict],
    max_step: int,
    all_edu_credit_combos: List[str],
    edu_order: Dict[str, int]
) -> List[Dict]:
    """
    Generate calculated salary entries using matrix fill algorithm

    This function fills in missing salary data points using a two-phase approach:
    - Phase 1: Fill down each column (same edu+credit, different steps)
    - Phase 2: Fill right (missing edu+credit combos)

    Args:
        district_id: District UUID
        district_name: District name
        year: School year (e.g., "2024-2025")
        period: Period (e.g., "full-year", "10-month")
        real_entries: List of actual salary records from the district
        max_step: Maximum step number across all districts
        all_edu_credit_combos: All education+credit combinations (e.g., ["B+0", "M+15"])
        edu_order: Education level ordering (e.g., {'B': 1, 'M': 2, 'D': 3})

    Returns:
        List of calculated salary items ready to be written to DynamoDB
    """
    calculated_items = []

    # PHASE 1: Fill down each column (existing combos)
    by_edu_credit = defaultdict(list)
    for entry in real_entries:
        edu = entry['education']
        cred = entry['credits']
        key = f"{edu}+{cred}"
        by_edu_credit[key].append(entry)

    # Build complete matrix for existing columns
    matrix = {}

    for edu_cred_key, entries in by_edu_credit.items():
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
                matrix[edu_cred_key][target_step] = entries_by_step[target_step]
            else:
                # Find source: highest step <= target_step
                lower_steps = [s for s in entries_by_step.keys() if s <= target_step]
                if lower_steps:
                    source_step = max(lower_steps)
                else:
                    source_step = min(entries_by_step.keys())

                source_entry = entries_by_step[source_step]

                # Track where this calculated value came from
                if 'is_calculated_from' in source_entry:
                    is_calculated_from = source_entry['is_calculated_from']
                else:
                    # Construct from source entry's actual values
                    is_calculated_from = {
                        'education': source_entry['education'],
                        'credits': source_entry['credits'],
                        'step': source_step
                    }

                # Create calculated entry
                step_padded = pad_number(target_step, 2)

                # Ensure salary is Decimal type for DynamoDB
                salary = source_entry['salary']
                if not isinstance(salary, Decimal):
                    salary = Decimal(str(salary))

                # Add GSI5 keys for fast comparison queries
                salary_padded = pad_salary(salary)

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
                    'salary': salary,
                    'is_calculated': True,
                    'is_calculated_from': is_calculated_from,
                    'source_step': source_step,
                    'GSI1PK': f'YEAR#{year}#PERIOD#{period}#EDU#{edu}#CR#{cred_padded}',
                    'GSI1SK': f'STEP#{step_padded}#DISTRICT#{district_id}',
                    'GSI2PK': f'YEAR#{year}#PERIOD#{period}#DISTRICT#{district_id}',
                    'GSI2SK': f'EDU#{edu}#CR#{cred_padded}#STEP#{step_padded}',
                    'GSI_COMP_PK': f'EDU#{edu}#CR#{cred_padded}#STEP#{step_padded}',
                    'GSI_COMP_SK': f'SALARY#{salary_padded}#YEAR#{year}#DISTRICT#{district_id}',
                }
                calculated_items.append(calculated_item)
                matrix[edu_cred_key][target_step] = calculated_item

    # PHASE 2: Fill right (missing edu+credit combos)
    missing_combos = [c for c in all_edu_credit_combos if c not in matrix]

    # Sort missing combos by education level, then by credits
    def combo_sort_key(combo):
        parts = combo.split('+')
        edu = parts[0]
        cred = int(parts[1])
        return (edu_order.get(edu, 0), cred)

    missing_combos_sorted = sorted(missing_combos, key=combo_sort_key)

    for missing_combo in missing_combos_sorted:
        parts = missing_combo.split('+')
        target_edu = parts[0]
        target_cred = int(parts[1])
        target_cred_padded = pad_number(target_cred, 3)

        # Find best source combo
        best_source = None
        best_source_cred = -1

        for source_combo in matrix.keys():
            source_parts = source_combo.split('+')
            source_edu = source_parts[0]
            source_cred = int(source_parts[1])

            # Do not allow using a source from a higher education level
            if edu_order.get(source_edu, 0) > edu_order.get(target_edu, 0):
                continue

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
            continue

        # Copy all steps from source combo and add to matrix
        source_entries = matrix[best_source]
        matrix[missing_combo] = {}  # Create entry in matrix for this new combo

        for step, source_entry in source_entries.items():
            step_padded = pad_number(step, 2)
            source_was_calculated = source_entry.get('is_calculated', False)

            # Track where this calculated value came from
            if 'is_calculated_from' in source_entry:
                is_calculated_from = source_entry['is_calculated_from']
            else:
                # Construct from source entry's actual values
                is_calculated_from = {
                    'education': source_entry['education'],
                    'credits': source_entry['credits'],
                    'step': source_entry['step']
                }

            # Ensure salary is Decimal type for DynamoDB
            salary = source_entry['salary']
            if not isinstance(salary, Decimal):
                salary = Decimal(str(salary))

            # Add GSI5 keys for fast comparison queries
            salary_padded = pad_salary(salary)

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
                'salary': salary,
                'is_calculated': True,
                'is_calculated_from': is_calculated_from,
                'source_edu_credit': best_source,
                'source_step': source_entry.get('source_step') if source_was_calculated else step,
                'GSI1PK': f'YEAR#{year}#PERIOD#{period}#EDU#{target_edu}#CR#{target_cred_padded}',
                'GSI1SK': f'STEP#{step_padded}#DISTRICT#{district_id}',
                'GSI2PK': f'YEAR#{year}#PERIOD#{period}#DISTRICT#{district_id}',
                'GSI2SK': f'EDU#{target_edu}#CR#{target_cred_padded}#STEP#{step_padded}',
                'GSI_COMP_PK': f'EDU#{target_edu}#CR#{target_cred_padded}#STEP#{step_padded}',
                'GSI_COMP_SK': f'SALARY#{salary_padded}#YEAR#{year}#DISTRICT#{district_id}',
            }
            calculated_items.append(calculated_item)
            matrix[missing_combo][step] = calculated_item  # Add to matrix so it can be used as source

    return calculated_items