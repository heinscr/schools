#!/usr/bin/env python3
"""Debug PDF structure - see what pdfplumber extracts"""
import pdfplumber
import sys
from pathlib import Path

if len(sys.argv) < 2:
    print("Usage: python debug_pdf.py <pdf_file>")
    sys.exit(1)

pdf_path = sys.argv[1]
print(f"Analyzing: {pdf_path}\n")

with pdfplumber.open(pdf_path) as pdf:
    for page_num, page in enumerate(pdf.pages, 1):
        print(f"{'='*60}")
        print(f"PAGE {page_num}")
        print(f"{'='*60}")

        # Show text
        text = page.extract_text() or ""
        print(f"\nText preview (first 500 chars):")
        print(text[:500])
        print("...\n")

        # Show tables
        tables = page.extract_tables()
        print(f"Tables found: {len(tables)}")

        for table_idx, table in enumerate(tables, 1):
            print(f"\nTable {table_idx}:")
            print(f"  Dimensions: {len(table)} rows × {len(table[0]) if table else 0} cols")
            if table:
                print(f"  Header row: {table[0]}")
                if len(table) > 1:
                    print(f"  First data row: {table[1]}")
                if len(table) > 2:
                    print(f"  Second data row: {table[2]}")

        print()
