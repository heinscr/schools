#!/usr/bin/env python3
"""
Simple standalone test of contract extraction
No complex imports - everything inline
"""
import pdfplumber
import re
from decimal import Decimal
from pathlib import Path
import json


def extract_year_from_text(text):
    """
    Extract school year from text using multiple pattern matching strategies

    Tries in order:
    1. School year format: "2022-2023"
    2. Effective date with month: "Effective July 1, 2022"
    3. Month followed by year: "July 2022"
    4. Any 4-digit year in 1900-2099 range

    Returns school year in "YYYY-YYYY" format or "unknown"
    """
    if not text:
        return "unknown"

    # Strategy 1: Look for YYYY-YYYY pattern (e.g., "2022-2023")
    match = re.search(r'(\d{4})\s*[-–—]\s*(\d{4})', text)
    if match:
        year1, year2 = match.group(1), match.group(2)
        return f"{year1}-{year2}"

    # Strategy 2: Look for "Effective [Month] [Day,] YYYY" pattern
    # Matches: "Effective July 1, 2022" or "Effective September 1, 2023"
    match = re.search(
        r'Effective\s+(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s+(\d{4})',
        text,
        re.IGNORECASE
    )
    if match:
        year = int(match.group(1))
        # Convert to school year format (e.g., 2022 -> "2022-2023")
        return f"{year}-{year + 1}"

    # Strategy 3: Look for month name followed by year
    # Matches: "July 2022" or "September 2023"
    match = re.search(
        r'(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{4})',
        text,
        re.IGNORECASE
    )
    if match:
        year = int(match.group(1))
        # Convert to school year format
        return f"{year}-{year + 1}"

    # Strategy 4: Look for any standalone 4-digit year (1900-2099)
    # This is a fallback and less reliable
    years = re.findall(r'\b(19\d{2}|20\d{2})\b', text)
    if years:
        # Take the most recent year found
        year = int(max(years))
        if 2000 <= year <= 2099:  # Reasonable range for school contracts
            return f"{year}-{year + 1}"

    return "unknown"


def extract_tables_from_pdf(pdf_path):
    """Extract all tables from a PDF"""
    results = []

    with pdfplumber.open(pdf_path) as pdf:
        for page_num, page in enumerate(pdf.pages, 1):
            text = page.extract_text() or ""
            tables = page.extract_tables()

            # Check if this looks like a salary table page
            if re.search(r'(SALARY|COMPENSATION|TEACHERS?)\s+SCHEDULE', text, re.I):
                # Extract year using improved logic
                year = extract_year_from_text(text)

                print(f"\nPage {page_num}: Found salary table for {year}")
                print(f"  Tables found: {len(tables)}")

                for table_idx, table in enumerate(tables, 1):
                    if table and len(table) > 1:
                        print(f"  Table {table_idx}: {len(table)} rows x {len(table[0])} cols")
                        print(f"    Header: {table[0]}")
                        print(f"    First data row: {table[1]}")

                        results.append({
                            'page': page_num,
                            'year': year,
                            'table': table
                        })

    return results


def parse_salary_table(table, district_name, year):
    """Parse a salary table into records"""
    if not table or len(table) < 2:
        return []

    # Education column mapping
    edu_map = {
        'BA': ('B', 0), 'B': ('B', 0),
        'BA+15': ('B', 15), 'B+15': ('B', 15),
        'BA+30': ('B', 30), 'B+30': ('B', 30), 'B30/MA': ('M', 0),
        'MA': ('M', 0), 'M': ('M', 0), 'MASTERS': ('M', 0),
        'MA+15': ('M', 15), 'M+15': ('M', 15),
        'MA+30': ('M', 30), 'M+30': ('M', 30),
        'MA+45': ('M', 45), 'M+45': ('M', 45), 'MA+45/CAGS': ('M', 45),
        'CAGS': ('M', 60), 'CAGS/DOC': ('D', 0),
        'DOC': ('D', 0), 'DOCTORATE': ('D', 0),
    }

    records = []

    # Parse header
    header = [str(h).strip().upper().replace(' ', '') for h in table[0]]
    edu_columns = [h for h in header if h and h not in ['', 'STEPS', 'STEP']]

    print(f"    Education columns: {edu_columns}")

    # Parse data rows
    for row in table[1:]:
        if not row or len(row) < 2:
            continue

        # Extract step number
        step_match = re.search(r'\b(\d+)\b', str(row[0]))
        if not step_match:
            continue
        step = int(step_match.group(1))

        # Extract salaries
        for col_idx, edu_col in enumerate(edu_columns):
            if col_idx + 1 < len(row):
                salary_str = str(row[col_idx + 1])
                salary_cleaned = re.sub(r'[$,\s]', '', salary_str)

                try:
                    salary = float(Decimal(salary_cleaned))

                    # Map education column
                    if edu_col in edu_map:
                        education, credits = edu_map[edu_col]

                        records.append({
                            'district_id': district_name.lower(),
                            'district_name': district_name,
                            'school_year': year,
                            'period': 'full-year',
                            'education': education,
                            'credits': credits,
                            'step': step,
                            'salary': salary
                        })
                except:
                    pass

    return records


def main():
    import sys

    if len(sys.argv) < 2:
        print("Usage: python test_extraction.py <pdf_file> [pdf_file ...]")
        sys.exit(1)

    all_records = []

    for pdf_path in sys.argv[1:]:
        path = Path(pdf_path)
        if not path.exists():
            print(f"File not found: {pdf_path}")
            continue

        # Extract district name from filename
        district = path.stem.split('_')[0].title()

        print(f"\n{'='*60}")
        print(f"Processing: {path.name}")
        print(f"District: {district}")
        print(f"{'='*60}")

        # Extract tables
        tables = extract_tables_from_pdf(pdf_path)

        # Parse each table
        for table_info in tables:
            records = parse_salary_table(
                table_info['table'],
                district,
                table_info['year']
            )
            all_records.extend(records)
            print(f"    Extracted {len(records)} salary records")

    # Summary
    print(f"\n{'='*60}")
    print(f"TOTAL RECORDS EXTRACTED: {len(all_records)}")
    print(f"{'='*60}")

    if all_records:
        # Group by district
        by_district = {}
        for rec in all_records:
            dist = rec['district_name']
            if dist not in by_district:
                by_district[dist] = []
            by_district[dist].append(rec)

        print(f"\nBreakdown by district:")
        for dist, recs in sorted(by_district.items()):
            years = sorted(set(r['school_year'] for r in recs))
            print(f"  {dist}: {len(recs)} records ({', '.join(years)})")

        # Show sample records
        print(f"\nSample records (first 5):")
        for rec in all_records[:5]:
            print(
                f"  {rec['district_name']:12s} | {rec['school_year']} | "
                f"Step {rec['step']:2d} | {rec['education']}+{rec['credits']:2d} | "
                f"${rec['salary']:>8,.2f}"
            )

        # Save to JSON
        output_file = 'extracted_salaries.json'
        with open(output_file, 'w') as f:
            json.dump(all_records, f, indent=2)
        print(f"\n💾 Saved to {output_file}")


if __name__ == '__main__':
    main()
