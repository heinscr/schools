#!/usr/bin/env python3
"""
Contract Scraping Script
Extracts teacher salary schedules from contract PDFs using pdfplumber + regex

Usage:
    python scrape_contracts.py ../data/sample_contracts/*.pdf
    python scrape_contracts.py ../data/sample_contracts/*.pdf --output extracted_data.json
    python scrape_contracts.py --help
"""
import argparse
import sys
import json
import logging
from pathlib import Path
from typing import List, Dict

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / 'backend'))

from services.contract_processor import ContractIngestion
from services.table_extractor import TableDetector, TableParser


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(levelname)s: %(message)s'
)
logger = logging.getLogger(__name__)


class ContractScraper:
    """Main orchestrator for contract scraping"""

    def __init__(self, verbose: bool = False):
        if verbose:
            logging.getLogger().setLevel(logging.DEBUG)

        self.ingestion = ContractIngestion()
        self.detector = TableDetector()
        self.parser = TableParser()

    def process_file(self, file_path: str) -> Dict:
        """
        Process a single contract PDF file

        Returns:
            Summary dict with success status and extracted records
        """
        logger.info(f"\n{'='*60}")
        logger.info(f"Processing: {file_path}")
        logger.info(f"{'='*60}")

        try:
            # Stage 1: Extract text and tables from PDF
            extracted = self.ingestion.extract_from_file(file_path)
            district_name = extracted['district_name']

            logger.info(f"District: {district_name}")
            logger.info(f"Pages: {extracted['total_pages']}")

            # Stage 2: Detect salary tables
            table_pages = self.detector.find_salary_tables(extracted['pages'])

            if not table_pages:
                logger.warning("⚠️  No salary tables detected")
                return {
                    'success': False,
                    'file': file_path,
                    'district': district_name,
                    'error': 'No salary tables detected',
                    'records': []
                }

            logger.info(f"Found {len(table_pages)} page(s) with salary tables")

            # Stage 3: Parse and normalize tables
            all_records = []

            for table_page in table_pages:
                page_num = table_page['page_number']
                year = table_page['school_year'] or 'unknown'

                logger.info(
                    f"\nPage {page_num}: {len(table_page['tables'])} table(s), "
                    f"year={year}"
                )

                for table_idx, raw_table in enumerate(table_page['tables'], 1):
                    logger.info(f"  Table {table_idx}: {len(raw_table)} rows")

                    parsed_table = self.parser.parse_table(
                        raw_table,
                        district_name=district_name,
                        school_year=year,
                        page_number=page_num
                    )

                    if parsed_table:
                        records = self.parser.normalize_to_json_format(parsed_table)
                        all_records.extend(records)
                        logger.info(f"  ✓ Extracted {len(records)} salary records")
                    else:
                        logger.warning(f"  ✗ Failed to parse table {table_idx}")

            # Summary
            if all_records:
                years = sorted(set(r['school_year'] for r in all_records))
                logger.info(
                    f"\n✓ SUCCESS: Extracted {len(all_records)} records "
                    f"for {district_name}"
                )
                logger.info(f"  Years: {', '.join(years)}")

                return {
                    'success': True,
                    'file': file_path,
                    'district': district_name,
                    'records_extracted': len(all_records),
                    'years': years,
                    'records': all_records
                }
            else:
                logger.warning(f"\n✗ FAILED: No records extracted")
                return {
                    'success': False,
                    'file': file_path,
                    'district': district_name,
                    'error': 'No records extracted from tables',
                    'records': []
                }

        except Exception as e:
            logger.error(f"\n✗ ERROR: {e}", exc_info=True)
            return {
                'success': False,
                'file': file_path,
                'error': str(e),
                'records': []
            }

    def process_batch(self, file_paths: List[str]) -> Dict:
        """Process multiple contract files"""
        results = []
        all_records = []

        for file_path in file_paths:
            result = self.process_file(file_path)
            results.append(result)

            if result.get('success'):
                all_records.extend(result.get('records', []))

        return {
            'total_files': len(file_paths),
            'successful': sum(1 for r in results if r.get('success')),
            'failed': sum(1 for r in results if not r.get('success')),
            'total_records': len(all_records),
            'results': results,
            'records': all_records
        }


def main():
    parser = argparse.ArgumentParser(
        description='Scrape teacher salary schedules from contract PDFs',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Process all PDFs in a directory
  python scrape_contracts.py ../data/sample_contracts/*.pdf

  # Save extracted data to JSON
  python scrape_contracts.py ../data/sample_contracts/*.pdf --output data.json

  # Verbose logging
  python scrape_contracts.py ../data/sample_contracts/*.pdf --verbose

  # Preview sample records
  python scrape_contracts.py ../data/sample_contracts/Bedford*.pdf --preview 5
        """
    )

    parser.add_argument(
        'files',
        nargs='+',
        help='PDF file paths to process'
    )
    parser.add_argument(
        '--output', '-o',
        help='Output JSON file path (optional)',
        default=None
    )
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Enable verbose debug logging'
    )
    parser.add_argument(
        '--preview', '-p',
        type=int,
        metavar='N',
        help='Show N sample records from each district',
        default=0
    )

    args = parser.parse_args()

    # Check if pdfplumber is installed
    try:
        import pdfplumber
    except ImportError:
        print("\n❌ Error: pdfplumber is not installed")
        print("Install it with: pip install pdfplumber")
        sys.exit(1)

    # Create scraper and process files
    scraper = ContractScraper(verbose=args.verbose)
    result = scraper.process_batch(args.files)

    # Print summary
    print(f"\n{'='*60}")
    print(f"EXTRACTION SUMMARY")
    print(f"{'='*60}")
    print(f"Total files:     {result['total_files']}")
    print(f"Successful:      {result['successful']}")
    print(f"Failed:          {result['failed']}")
    print(f"Total records:   {result['total_records']}")
    print(f"{'='*60}\n")

    # Detailed results
    print("DETAILED RESULTS:")
    for r in result['results']:
        if r.get('success'):
            print(
                f"  ✓ {r['district']}: {r['records_extracted']} records "
                f"({', '.join(r['years'])})"
            )
        else:
            district = r.get('district', Path(r['file']).stem)
            error = r.get('error', 'unknown error')
            print(f"  ✗ {district}: {error}")

    # Preview sample records
    if args.preview > 0 and result['records']:
        print(f"\n{'='*60}")
        print(f"SAMPLE RECORDS (first {args.preview} from each district)")
        print(f"{'='*60}\n")

        # Group by district
        by_district = {}
        for record in result['records']:
            district = record['district_name']
            if district not in by_district:
                by_district[district] = []
            by_district[district].append(record)

        for district, records in by_district.items():
            print(f"{district}:")
            for record in records[:args.preview]:
                print(
                    f"  {record['school_year']} | "
                    f"Step {record['step']:2d} | "
                    f"{record['education']}+{record['credits']:2d} | "
                    f"${record['salary']:>8,.2f}"
                )
            print()

    # Save to JSON if requested
    if args.output:
        output_path = Path(args.output)

        # Prepare data for JSON export
        export_data = {
            'summary': {
                'total_files': result['total_files'],
                'successful': result['successful'],
                'failed': result['failed'],
                'total_records': result['total_records']
            },
            'records': result['records']
        }

        with open(output_path, 'w') as f:
            json.dump(export_data, f, indent=2)

        print(f"💾 Saved {len(result['records'])} records to {output_path}")

    # Exit with appropriate code
    sys.exit(0 if result['failed'] == 0 else 1)


if __name__ == '__main__':
    main()
