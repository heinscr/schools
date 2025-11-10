#!/usr/bin/env python3
"""
Process contract PDFs from S3 bucket with hybrid extraction
Handles both text-based and image-based PDFs
"""
import argparse
import sys
import os
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent / 'backend'))

from services.hybrid_extractor import HybridContractExtractor


def main():
    parser = argparse.ArgumentParser(
        description='Process contract PDFs from S3 with hybrid extraction (pdfplumber + AWS Textract)',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Environment Variables:
  AWS_PROFILE          AWS profile to use (optional)
  AWS_REGION           AWS region (default: us-east-1)

Examples:
  # Process all PDFs in the bucket
  python process_s3_contracts.py

  # Use specific AWS profile
  AWS_PROFILE=myprofile python process_s3_contracts.py

  # Custom input/output buckets
  python process_s3_contracts.py \\
    --input-bucket my-bucket \\
    --input-prefix contracts/pdfs/ \\
    --output-bucket my-bucket \\
    --output-prefix contracts/data/

Cost Estimate:
  - Text-based PDFs: Free (pdfplumber)
  - Image-based PDFs: $15 per 1,000 pages (AWS Textract)
  - Based on samples: 25% text-based, 75% image-based
  - 350 contracts (avg 3 pages) = ~$10-12 total
        """
    )

    parser.add_argument(
        '--input-bucket',
        default='crackpow-schools-918213481336',
        help='S3 bucket containing PDFs (default: crackpow-schools-918213481336)'
    )

    parser.add_argument(
        '--input-prefix',
        default='contracts/pdfs/',
        help='S3 prefix/folder for input PDFs (default: contracts/pdfs/)'
    )

    parser.add_argument(
        '--output-bucket',
        default='crackpow-schools-918213481336',
        help='S3 bucket for JSON output (default: crackpow-schools-918213481336)'
    )

    parser.add_argument(
        '--output-prefix',
        default='contracts/data/',
        help='S3 prefix/folder for output JSON (default: contracts/data/)'
    )

    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='List files without processing'
    )

    args = parser.parse_args()

    # Check dependencies
    try:
        import pdfplumber
        import boto3
    except ImportError as e:
        print(f"❌ Error: Missing dependency: {e}")
        print("\nInstall required packages:")
        print("  pip install pdfplumber boto3")
        sys.exit(1)

    print("🚀 Contract PDF Processor (AWS Textract)")
    print("="*60)
    print(f"Input:  s3://{args.input_bucket}/{args.input_prefix}")
    print(f"Output: s3://{args.output_bucket}/{args.output_prefix}")
    print("="*60)

    if args.dry_run:
        print("\n🔍 DRY RUN MODE - Listing files only\n")

        import boto3
        s3 = boto3.client('s3')

        try:
            response = s3.list_objects_v2(
                Bucket=args.input_bucket,
                Prefix=args.input_prefix
            )

            pdf_files = [
                obj['Key'] for obj in response.get('Contents', [])
                if obj['Key'].lower().endswith('.pdf')
            ]

            print(f"Found {len(pdf_files)} PDF files:\n")
            for i, key in enumerate(pdf_files, 1):
                filename = Path(key).name
                print(f"  {i}. {filename}")

            # Count pages for cost estimate
            print(f"\n💰 Estimated cost (assuming 75% need Textract, avg 3 pages/PDF):")
            textract_pdfs = int(len(pdf_files) * 0.75)
            total_pages = textract_pdfs * 3
            cost = (total_pages / 1000) * 15
            print(f"   {textract_pdfs} PDFs × 3 pages × $15/1000 pages = ${cost:.2f}")

        except Exception as e:
            print(f"❌ Error accessing S3: {e}")
            print("\nMake sure you have AWS credentials configured:")
            print("  aws configure")
            print("Or set AWS_PROFILE environment variable")
            sys.exit(1)

        sys.exit(0)

    # Process files
    print("\n📄 Processing PDFs...\n")

    try:
        extractor = HybridContractExtractor()

        results = extractor.process_s3_bucket(
            input_bucket=args.input_bucket,
            input_prefix=args.input_prefix,
            output_bucket=args.output_bucket,
            output_prefix=args.output_prefix
        )

        # Detailed results
        print("\nDETAILED RESULTS:")
        for file_info in results['files']:
            if file_info.get('success'):
                method = file_info['method']
                records = file_info['records']
                icon = "📝" if method == "pdfplumber" else "🔍"
                print(f"  {icon} {file_info['filename']}: {records} records ({method})")
            else:
                print(f"  ❌ {file_info['filename']}: {file_info.get('error', 'unknown error')}")

        # Cost estimate
        print(f"\n💰 COST ESTIMATE:")
        print(f"   Textract calls: {results['textract_count']}")
        print(f"   Estimated cost (avg 3 pages): ${results['textract_count'] * 3 * 0.015:.2f}")

        # Exit code
        sys.exit(0 if results['failed'] == 0 else 1)

    except Exception as e:
        print(f"\n❌ Fatal error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
