#!/usr/bin/env python3
"""
IMPROVED PDF salary table extraction with better handling of:
- Roman numerals in column headers (I, II, III, IV)
- Multiplier/Salary column pairs
- Parentheses in education labels
- Messy text extraction
"""
import sys
sys.path.insert(0, '/home/user/schools')

from test_extraction import *  # Import base functions
import re
from typing import Any, Dict, List, Optional, Sequence, Tuple

# Enhanced education mappings including Roman numerals
ENHANCED_EDU_MAP_RAW = {
    **EDU_MAP_RAW,  # Include all existing mappings
    # Roman numeral variants
    'I': ('B', 0),
    'II': ('B', 15),
    'III': ('B', 30),
    'IV': ('M', 0),
    'V': ('M', 15),
    'VI': ('M', 30),
    'VII': ('M', 45),
    'VIII': ('M', 60),
    '(I)': ('B', 0),
    '(II)': ('B', 15),
    '(III)': ('B', 30),
    '(IV)': ('M', 0),
    '(V)': ('M', 15),
    '(VI)': ('M', 30),
    '(VII)': ('M', 45),
    '(VIII)': ('M', 60),
}


def enhanced_normalize_lane_key(text: Any) -> str:
    """Enhanced version that handles Roman numerals and parentheses better"""
    if text is None:
        return 'NONE'

    raw = str(text).upper().strip()

    # Remove common prefixes/suffixes
    raw = raw.replace('B.A.', 'BA').replace('M.A.', 'MA')
    raw = raw.replace('BACHELOR', 'BA').replace('BACCALAUREATE', 'BA')
    raw = raw.replace('MASTER', 'MA').replace('MASTERS', 'MA')
    raw = raw.replace('DOCTORATE', 'DOC').replace('DOCTORAL', 'DOC')

    # Handle parenthetical Roman numerals: "BA (I)" or "MA+15 (II)"
    # Extract the main part before parentheses
    paren_match = re.search(r'\(([IVX]+)\)', raw)
    if paren_match:
        roman_num = paren_match.group(1)
        # Check if this is a standalone Roman numeral with no other content
        cleaned = re.sub(r'\([IVX]+\)', '', raw).strip()
        cleaned = re.sub(r'[^A-Z0-9+]', '', cleaned)
        if not cleaned or cleaned in ['BA', 'MA', 'B', 'M']:
            # Use Roman numeral for mapping
            return roman_num

    # Handle "BA + (10)" -> "BA+10"
    raw = re.sub(r'\+\s*\((\d+)\)', r'+\1', raw)

    # Normalize dashes to plus
    raw = raw.replace('–', '+').replace('—', '+').replace('-', '+').replace(':', '+')

    # Remove spaces around plus signs
    raw = re.sub(r'\s*\+\s*', '+', raw)

    # Normalize BA15 to BA+15, M30 to M+30
    raw = re.sub(r'\b(BA|MA|B|M)(\d{1,2})\b', r'\1+\2', raw)

    # Try tokenizing to extract education label
    tokens = enhanced_tokenize_lane_labels(raw)
    if tokens:
        return tokens[0]

    # Clean up for mapping
    simplified = re.sub(r'[^A-Z0-9+]', '', raw)

    # Handle explicit lane references
    lane_match = re.match(r'LANE(\d+)', simplified)
    if lane_match:
        return f"LANE{lane_match.group(1)}"

    pay_scale_match = re.match(r'PAYSCALE(\d+)', simplified)
    if pay_scale_match:
        return f"PAYSCALE{pay_scale_match.group(1)}"

    level_match = re.match(r'LEVEL(\d+)', simplified)
    if level_match:
        return f"LEVEL{level_match.group(1)}"

    # Check for standalone Roman numerals
    if re.fullmatch(r'[IVX]+', simplified):
        return simplified

    return simplified if simplified else 'NONE'


def enhanced_tokenize_lane_labels(text: str) -> List[str]:
    """Enhanced tokenizer that handles Roman numerals and parentheses"""
    if not text:
        return []

    normalized = text.upper().strip()

    # Normalize common patterns
    normalized = normalized.replace('B.A.', 'BA').replace('M.A.', 'MA')
    normalized = normalized.replace('BACCALAUREATE', 'BA').replace('BACHELOR', 'BA')
    normalized = normalized.replace('MASTERS', 'MA').replace('MASTER', 'MA')

    # Remove parentheses around numbers: "BA + (10)" -> "BA+10"
    normalized = re.sub(r'\+\s*\((\d+)\)', r'+\1', normalized)

    # Normalize separators
    normalized = normalized.replace('-', '+').replace('/', ' ')

    # Remove other punctuation except + and spaces
    normalized = re.sub(r'[^A-Z0-9+ ]', ' ', normalized)
    normalized = re.sub(r'\s+', ' ', normalized).strip()

    # Normalize BA15 to BA+15
    normalized = re.sub(r'\b(BA|MA|B|M)(\d{1,2})\b', r'\1+\2', normalized)

    # Enhanced pattern to match education tokens
    token_pattern = re.compile(
        r'(?:BA|MA|B|M)(?:\+\d+)?|'  # BA, MA, B+15, M+30, etc.
        r'CAGS|DOC|DR|EDD|PHD|'  # Doctorate variants
        r'[IVX]+',  # Roman numerals
        re.I
    )

    tokens = token_pattern.findall(normalized)
    return [token.upper().strip() for token in tokens if token.strip()]


# Rebuild enhanced education map
ENHANCED_EDU_MAP: Dict[str, Tuple[str, int]] = {}
for key, value in ENHANCED_EDU_MAP_RAW.items():
    normalized_key = enhanced_normalize_lane_key(key)
    if normalized_key != 'NONE':
        ENHANCED_EDU_MAP[normalized_key] = value


def enhanced_collapse_multiplier_salary_columns(
    table: Optional[Sequence[Sequence[Any]]],
    lane_labels: Optional[List[str]] = None,
) -> Optional[List[List[str]]]:
    """
    Enhanced version that better detects and collapses Multiplier/Salary column pairs.

    Looks for patterns like:
    Step | Multiplier | Salary | Multiplier | Salary | ...
    or
    Step | Label1 (I) | | Label2 (II) | | ...
    """
    if not table or len(table) < 2:
        return None

    table_list = [list(row) for row in table]
    header = table_list[0]

    if not header or len(header) < 3:
        return table_list

    # Normalize header cells
    normalized = [enhanced_normalize_lane_key(cell) if cell else 'EMPTY' for cell in header]

    # Check if we have alternating MULTIPLIER/SALARY pattern (skip first column)
    pattern = normalized[1:]
    if len(pattern) < 2 or len(pattern) % 2 != 0:
        return table_list

    # Check for multiplier/salary pattern
    is_mult_sal_pattern = True
    for idx, cell in enumerate(pattern):
        expected = 'MULTIPLIER' if idx % 2 == 0 else 'SALARY'
        if cell != expected:
            is_mult_sal_pattern = False
            break

    if not is_mult_sal_pattern:
        return table_list

    # We have a multiplier/salary pattern - collapse it
    pair_count = len(pattern) // 2

    print(f"  ✓ Detected {pair_count} Multiplier/Salary column pairs - collapsing...")

    # Get lane labels
    labels: List[str] = []
    if lane_labels and len(lane_labels) >= pair_count:
        labels = lane_labels[:pair_count]
    else:
        # Try to extract labels from rows above header
        # Often the labels appear 1-2 rows before the Multiplier/Salary row
        labels = []

        # Generate fallback labels
        for i in range(pair_count):
            if i < len(labels):
                continue
            labels.append(f'Lane {i + 1}')

    # Build collapsed table
    new_table: List[List[str]] = [['Step'] + labels]

    for row in table_list[1:]:
        if len(row) < 1 + pair_count * 2:
            continue

        new_row = [row[0]]  # Step column

        for pair_idx in range(pair_count):
            # Salary is at index: 1 + pair_idx * 2 + 1
            salary_idx = 1 + pair_idx * 2 + 1
            salary_val = row[salary_idx] if salary_idx < len(row) else ''
            new_row.append(salary_val)

        new_table.append(new_row)

    return new_table if len(new_table) > 1 else None


def enhanced_extract_lane_labels(lines: List[str], header_idx: int, expected_pairs: int) -> List[str]:
    """
    Enhanced lane label extraction that looks for Roman numerals and parenthetical labels.
    """
    labels: List[str] = []
    if header_idx <= 0 or expected_pairs <= 0:
        return labels

    # Look in lines before the header
    start = max(0, header_idx - 15)  # Increased search range

    for line in lines[start:header_idx]:
        candidate = line.strip()
        if not candidate or candidate.lower().startswith('step'):
            continue

        # Try tokenizing with enhanced tokenizer
        label_tokens = enhanced_tokenize_lane_labels(candidate)
        if label_tokens:
            labels.extend(label_tokens)

        # Also look for patterns like "B.A. (I)  B.A. + (10) II  B.A. + (20) III  MA (IV)"
        # These might be on a single line
        parts = re.split(r'\s{2,}', candidate)
        for part in parts:
            part_tokens = enhanced_tokenize_lane_labels(part)
            if part_tokens and part_tokens not in labels:
                labels.extend(part_tokens)

    # Deduplicate while preserving order
    deduped: List[str] = []
    seen: set[str] = set()
    for label in labels:
        norm_label = enhanced_normalize_lane_key(label)
        if norm_label not in seen and norm_label != 'NONE':
            seen.add(norm_label)
            deduped.append(norm_label)

    return deduped[-expected_pairs:] if expected_pairs and len(deduped) >= expected_pairs else deduped


def enhanced_is_valid_step_number(step: int) -> bool:
    """Check if a step number is valid (not garbage from bad text extraction)"""
    # Valid step numbers are typically 0-30 (some districts go higher but rarely above 35)
    return 0 <= step <= 35


def enhanced_parse_salary_table(
    table: List[List[str]],
    district_name: str,
    year: str,
    alias_map: Optional[Dict[str, str]] = None
) -> List[Dict]:
    """Enhanced parser using improved education mappings"""
    if not table or len(table) < 2:
        return []

    records = []

    # Find header row
    header_row_idx = 0
    for idx, row in enumerate(table):
        if row and str(row[0]).strip().upper() == 'STEP':
            header_row_idx = idx
            break

    if header_row_idx > 0:
        print(f"    Skipping {header_row_idx} non-header row(s) at top of table")

    # Parse header with enhanced normalizer
    raw_header = table[header_row_idx]
    normalized_header = [enhanced_normalize_lane_key(h) for h in raw_header]
    alias_map = alias_map or {}

    # Map columns to education levels using enhanced map
    edu_columns = []
    for i, (raw_cell, normalized_cell) in enumerate(zip(raw_header, normalized_header)):
        if i == 0:  # Skip step column
            continue

        display_label = str(raw_cell).strip() or normalized_cell

        # Try direct mapping first
        if normalized_cell in ENHANCED_EDU_MAP:
            edu_columns.append((i, display_label, ENHANCED_EDU_MAP[normalized_cell]))
            continue

        # Try alias mapping
        alias_key = enhanced_normalize_lane_key(display_label)
        mapped_key = alias_map.get(alias_key) or alias_map.get(normalized_cell)
        if mapped_key and mapped_key in ENHANCED_EDU_MAP:
            edu_columns.append((i, display_label, ENHANCED_EDU_MAP[mapped_key]))
            continue

        # Warn about unknown columns (skip common metadata columns)
        if normalized_cell.upper() not in ['MULTIPLIER', 'SALARY', 'EMPTY', 'NONE', '']:
            print(f"    WARNING: Unknown education level '{display_label}' (normalized: '{normalized_cell}') in column {i}")

    if not edu_columns:
        print("    ERROR: No valid education columns found")
        return []

    print(f"    Mapped {len(edu_columns)} columns: {[(h, edu, cr) for _, h, (edu, cr) in edu_columns]}")

    # Parse data rows with validation
    valid_records = 0
    invalid_steps = 0

    for row_idx, row in enumerate(table[header_row_idx + 1:], header_row_idx + 2):
        if not row or len(row) < 2:
            continue

        # Extract and validate step number
        step_str = str(row[0]).strip()
        step_match = re.search(r'(\d+)', step_str)
        if not step_match:
            continue

        step = int(step_match.group(1))

        # Validate step number to filter garbage
        if not enhanced_is_valid_step_number(step):
            invalid_steps += 1
            continue

        # Extract salaries
        for col_idx, col_name, (education, credits) in edu_columns:
            if col_idx >= len(row):
                continue

            salary_str = str(row[col_idx]).strip()
            if not salary_str:
                continue

            # Clean and parse salary
            salary_cleaned = re.sub(r'[$,\s]', '', salary_str)
            try:
                salary = float(Decimal(salary_cleaned))

                # Validate salary range
                if 20000 <= salary <= 200000:
                    records.append({
                        'district_id': district_name.lower().replace(' ', '-'),
                        'district_name': district_name,
                        'school_year': year,
                        'period': 'full-year',
                        'education': education,
                        'credits': credits,
                        'step': step,
                        'salary': salary
                    })
                    valid_records += 1
            except (ValueError, InvalidOperation):
                pass

    if invalid_steps > 0:
        print(f"    Filtered out {invalid_steps} rows with invalid step numbers (> 35)")

    return records


def enhanced_extract_tables_from_pdf(pdf_path: str) -> Tuple[List[Dict], List[str]]:
    """Enhanced extraction with improved column handling"""
    results: List[Dict] = []
    seen_tables = set()
    attempted_methods: List[str] = []
    trigger_pattern = re.compile(
        r'(SALARY|COMPENSATION|TEACHERS?|SCHEDULE|PAY\s*SCALES?|ACADEMIC|STEP)',
        re.I
    )

    def add_result(
        page_num: int,
        year: str,
        table_data: Optional[Sequence[Sequence[Any]]],
        method: str,
        alias_map: Optional[Dict[str, str]] = None
    ) -> None:
        normalized = normalize_table_data(table_data)
        if len(normalized) < 2:
            return

        for sub_table in split_table_on_step_columns(normalized):
            if len(sub_table) < 2:
                continue

            key = (method, page_num, tuple(tuple(row) for row in sub_table))
            if key in seen_tables:
                continue

            seen_tables.add(key)
            results.append({
                'page': page_num,
                'year': year,
                'table': sub_table,
                'method': method,
                'aliases': alias_map or {}
            })

    # Try pypdfium2 first
    if PYPDFIUM_AVAILABLE and pdfium is not None:
        attempted_methods.append('pypdfium')
        print("  Trying pypdfium2 extraction...")
        pypdfium_pages = extract_text_with_pypdfium(pdf_path)

        for page_num, text in pypdfium_pages:
            if not trigger_pattern.search(text):
                continue

            year = extract_year_from_text(text)
            print(f"\nPage {page_num}: Detected salary schedule for {year} (pypdfium2)")
            lines = text.split('\n')

            # Enhanced lane label extraction
            alias_map = collect_lane_aliases(text)

            # Try column-oriented parsing with enhanced collapsing
            column_tables = parse_column_oriented_tables(lines)
            for block_idx, table_data in enumerate(column_tables, start=1):
                if table_data:
                    # Try enhanced multiplier/salary collapsing
                    expected_pairs = max(0, (len(table_data[0]) - 1) // 2)
                    lane_labels = enhanced_extract_lane_labels(lines, 0, expected_pairs)
                    collapsed = enhanced_collapse_multiplier_salary_columns(table_data, lane_labels)
                    final_table = collapsed or table_data

                    print(f"  pypdfium2 success (block {block_idx}): {len(final_table)} rows x {len(final_table[0])} cols")
                    add_result(page_num, year, final_table, 'pypdfium2-column', alias_map)

            # Try row-oriented parsing
            row_table = parse_row_oriented_table(lines)
            if row_table:
                print(f"  pypdfium2 row-parse success: {len(row_table)} rows x {len(row_table[0])} cols")
                add_result(page_num, year, row_table, 'pypdfium2-row', alias_map)
    else:
        print("  pypdfium2 not available")

    # Try PyMuPDF
    attempted_methods.append('pymupdf')
    doc = fitz.open(pdf_path)
    try:
        for page_index in range(len(doc)):
            page_num = page_index + 1
            page = doc[page_index]
            text = str(page.get_text() or '')

            if not trigger_pattern.search(text):
                continue

            year = extract_year_from_text(text)
            print(f"\nPage {page_num}: Detected salary schedule for {year} (PyMuPDF)")
            alias_map = collect_lane_aliases(text)
            lines = text.split('\n')

            # Built-in table detection
            table_finder = getattr(page, 'find_tables', None)
            tables = table_finder() if callable(table_finder) else None
            table_objects = getattr(tables, 'tables', None) if tables is not None else None

            if table_objects:
                print(f"  Built-in table detection: {len(table_objects)} tables")
                for table_obj in table_objects:
                    table_data = table_obj.extract()
                    if table_data:
                        # Apply enhanced collapsing
                        expected_pairs = max(0, (len(table_data[0]) - 1) // 2)
                        lane_labels = enhanced_extract_lane_labels(lines, 0, expected_pairs)
                        collapsed = enhanced_collapse_multiplier_salary_columns(table_data, lane_labels)
                        final_table = collapsed or table_data

                        add_result(page_num, year, final_table, 'pymupdf-table', alias_map)

            # Text-based column parsing
            column_tables = parse_column_oriented_tables(lines)
            for block_idx, table_data in enumerate(column_tables, start=1):
                # Apply enhanced collapsing
                expected_pairs = max(0, (len(table_data[0]) - 1) // 2)
                lane_labels = enhanced_extract_lane_labels(lines, 0, expected_pairs)
                collapsed = enhanced_collapse_multiplier_salary_columns(table_data, lane_labels)
                final_table = collapsed or table_data

                print(f"  Successfully parsed block {block_idx}: {len(final_table)} rows x {len(final_table[0])} cols")
                add_result(page_num, year, final_table, 'pymupdf-text-column', alias_map)

            # Row-oriented parsing
            row_table = parse_row_oriented_table(lines)
            if row_table:
                print(f"  Row-oriented parse: {len(row_table)} rows x {len(row_table[0])} cols")
                add_result(page_num, year, row_table, 'pymupdf-text-row', alias_map)

    finally:
        doc.close()

    return results, attempted_methods


# Main function
if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--limit', type=int, default=None)
    parser.add_argument('--output', type=str, default='improved_results.json')
    parser.add_argument('--summary-output', type=str, default='improved_summary.csv')
    args = parser.parse_args()

    # Get PDF files
    contracts_dir = Path('data/results_contracts')
    pdf_paths = sorted(p for p in contracts_dir.rglob('*.pdf') if p.is_file())

    if args.limit:
        pdf_paths = pdf_paths[:args.limit]

    print(f"Found {len(pdf_paths)} PDF(s) to process.\n")

    all_records: List[Dict] = []
    per_pdf_summary: List[Dict[str, Any]] = []

    for pdf_path in pdf_paths:
        district = pdf_path.stem.split('_')[0].title()
        method_counts: Dict[str, int] = {'pypdfium': 0, 'pymupdf': 0, 'pdfplumber': 0, 'other': 0}

        print(f"\n{'='*70}")
        print(f"Processing: {pdf_path.name}")
        print(f"District: {district}")
        print(f"{'='*70}")

        try:
            tables, attempted = enhanced_extract_tables_from_pdf(str(pdf_path))

            if not tables:
                print("  WARNING: No tables found")
                per_pdf_summary.append({
                    'document': pdf_path.name,
                    'pypdfium_records': 0,
                    'pymupdf_records': 0,
                    'pdfplumber_records': 0,
                    'other_records': 0,
                    'total_records': 0,
                    'attempted_pypdfium': 'pypdfium' in attempted,
                    'attempted_pymupdf': 'pymupdf' in attempted,
                    'attempted_pdfplumber': False,
                })
                continue

            for table_info in tables:
                records = enhanced_parse_salary_table(
                    table_info['table'],
                    district,
                    table_info['year'],
                    table_info.get('aliases')
                )
                all_records.extend(records)
                method = table_info.get('method', 'unknown')
                bucket = summarize_method_bucket(method)
                method_counts[bucket] += len(records)
                print(f"  ✓ Extracted {len(records)} salary records (method: {method})")

            per_pdf_summary.append({
                'document': pdf_path.name,
                'pypdfium_records': method_counts.get('pypdfium', 0),
                'pymupdf_records': method_counts.get('pymupdf', 0),
                'pdfplumber_records': method_counts.get('pdfplumber', 0),
                'other_records': method_counts.get('other', 0),
                'total_records': sum(method_counts.values()),
                'attempted_pypdfium': 'pypdfium' in attempted,
                'attempted_pymupdf': 'pymupdf' in attempted,
                'attempted_pdfplumber': False,
            })

        except Exception as exc:
            print(f"  ERROR: {exc}")
            import traceback
            traceback.print_exc()

    # Print summary
    print(f"\n{'='*70}")
    print(f"TOTAL RECORDS EXTRACTED: {len(all_records)}")
    print(f"{'='*70}")

    if all_records:
        # Group by district/year
        by_district: Dict[Tuple[str, str], List[Dict]] = {}
        for rec in all_records:
            key = (rec['district_name'], rec['school_year'])
            by_district.setdefault(key, []).append(rec)

        print("\nBreakdown:")
        for (dist, year), recs in sorted(by_district.items()):
            steps = len({r['step'] for r in recs})
            edu_levels = len({(r['education'], r['credits']) for r in recs})
            print(f"  {dist} ({year}): {len(recs)} records ({steps} steps × {edu_levels} edu levels)")

        # Save results
        output_path = Path(args.output)
        with open(output_path, 'w') as f:
            json.dump({'records': all_records, 'summary': per_pdf_summary}, f, indent=2)
        print(f"\n💾 Saved {len(all_records)} records to {output_path}")

        summary_path = Path(args.summary_output)
        with open(summary_path, 'w', newline='') as csv_file:
            writer = csv.DictWriter(csv_file, fieldnames=[
                'document', 'pypdfium_records', 'attempted_pypdfium',
                'pymupdf_records', 'attempted_pymupdf',
                'pdfplumber_records', 'attempted_pdfplumber',
                'other_records', 'total_records',
            ])
            writer.writeheader()
            writer.writerows(per_pdf_summary)
        print(f"💾 Saved summary to {summary_path}")
