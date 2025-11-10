#!/usr/bin/env python3
"""Test year extraction patterns"""
import re

def extract_year_from_text(text):
    """Extract school year from text using multiple pattern matching strategies"""
    if not text:
        return "unknown"

    # Strategy 1: Look for YYYY-YYYY pattern (e.g., "2022-2023")
    match = re.search(r'(\d{4})\s*[-–—]\s*(\d{4})', text)
    if match:
        year1, year2 = match.group(1), match.group(2)
        return f"{year1}-{year2}", "YYYY-YYYY pattern"

    # Strategy 2: Look for "Effective [Month] [Day,] YYYY" pattern
    match = re.search(
        r'Effective\s+(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s+(\d{4})',
        text,
        re.IGNORECASE
    )
    if match:
        year = int(match.group(1))
        return f"{year}-{year + 1}", "Effective Month Day, YYYY"

    # Strategy 3: Look for month name followed by year
    match = re.search(
        r'(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{4})',
        text,
        re.IGNORECASE
    )
    if match:
        year = int(match.group(1))
        return f"{year}-{year + 1}", "Month YYYY"

    # Strategy 4: Look for any standalone 4-digit year (2000-2099)
    years = re.findall(r'\b(20\d{2})\b', text)
    if years:
        year = int(max(years))
        return f"{year}-{year + 1}", "Standalone YYYY"

    return "unknown", "No pattern matched"


# Test cases
test_cases = [
    "SCHEDULE A TEACHERS SCHEDULE\nEffective July 1, 2022",
    "Teachers Salary Schedule 2022-2023\n(Increase all wages by 2.5%)",
    "Agawam Public Schools\nTeachers Salary Schedule\n2023-2024",
    "COMPENSATION SCHEDULES\nThe following compensation schedules will govern during the term of this Agreement.\nAgawam Public Schools\nTeachers Salary Schedule\nSeptember 2022",
    "APPENDIX A - July 2024",
    "Contract effective for the 2022 school year",
]

print("Year Extraction Pattern Testing")
print("=" * 70)

for i, text in enumerate(test_cases, 1):
    year, pattern = extract_year_from_text(text)
    preview = text.replace('\n', ' ')[:50] + "..." if len(text) > 50 else text.replace('\n', ' ')
    print(f"\nTest {i}: {preview}")
    print(f"  Result: {year}")
    print(f"  Pattern: {pattern}")
