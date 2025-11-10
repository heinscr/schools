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
        description='Process contract PDFs from S3 with hybrid extraction (pdfplumber + Claude API)',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Environment Variables:
  ANTHROPIC_API_KEY    Claude API key (required)
  AWS_PROFILE          AWS profile to use (optional)
  AWS_REGION           AWS region (default: us-east-1)

Examples:
  # Process all PDFs in the bucket
  export ANTHROPIC_API_KEY=sk-ant-...
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
  - Image-based PDFs: ~$0.03 per contract (Claude API)
  - Based on samples: 25% text-based, 75% image-based
  - 350 contracts = ~$8 total
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
        '--api-key',
        help='Claude API key (or set ANTHROPIC_API_KEY env var)'
    )

    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='List files without processing'
    )

    args = parser.parse_args()

    # Check for API key
    api_key = args.api_key or os.environ.get('ANTHROPIC_API_KEY')
    if not api_key and not args.dry_run:
        print("❌ Error: ANTHROPIC_API_KEY environment variable not set")
        print("Get your API key from: https://console.anthropic.com/")
        print("\nSet it with:")
        print("  export ANTHROPIC_API_KEY=sk-ant-...")
        sys.exit(1)

    # Check dependencies
    try:
        import pdfplumber
        import anthropic
        import pdf2image
        import boto3
    except ImportError as e:
        print(f"❌ Error: Missing dependency: {e}")
        print("\nInstall required packages:")
        print("  pip install pdfplumber anthropic pdf2image boto3 pillow")
        print("\nSystem dependencies (for pdf2image):")
        print("  Ubuntu/Debian: apt-get install poppler-utils")
        print("  macOS: brew install poppler")
        sys.exit(1)

    print("🚀 Contract PDF Processor")
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

            print(f"\n💰 Estimated cost (assuming 75% need Claude API):")
            print(f"   {len(pdf_files)} files × 75% × $0.03 = ${len(pdf_files) * 0.75 * 0.03:.2f}")

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
        extractor = HybridContractExtractor(anthropic_api_key=api_key)

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
                icon = "📝" if method == "pdfplumber" else "🤖"
                print(f"  {icon} {file_info['filename']}: {records} records ({method})")
            else:
                print(f"  ❌ {file_info['filename']}: {file_info.get('error', 'unknown error')}")

        # Cost estimate
        print(f"\n💰 COST ESTIMATE:")
        print(f"   Claude API calls: {results['claude_count']}")
        print(f"   Estimated cost: ${results['claude_count'] * 0.03:.2f}")

        # Exit code
        sys.exit(0 if results['failed'] == 0 else 1)

    except Exception as e:
        print(f"\n❌ Fatal error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
