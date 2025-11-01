#!/usr/bin/env python3
"""
Script to download teacher contract PDFs from URLs in teacher_contracts.json
and save them to organized folders: data/contract_pdfs/{district}.pdf
"""

import json
import os
import time
import requests
from pathlib import Path
from urllib.parse import urlparse
import re

# Configuration
CONTRACTS_FILE = "teacher_contracts.json"
OUTPUT_DIR = "contract_pdfs"
DOWNLOAD_DELAY = 1  # seconds between downloads to be respectful
TIMEOUT = 30  # seconds for download timeout

def sanitize_filename(name: str) -> str:
    """Sanitize district name for use as filename."""
    # Remove or replace invalid filename characters
    name = re.sub(r'[<>:"/\\|?*]', '', name)
    # Replace spaces and other problematic chars with underscores
    name = re.sub(r'\s+', '_', name)
    return name

def load_contracts():
    """Load contracts from JSON file."""
    with open(CONTRACTS_FILE, 'r') as f:
        return json.load(f)

def get_file_extension(url: str, content_type: str = None) -> str:
    """Determine file extension from URL or content type."""
    # First try to get extension from URL
    parsed = urlparse(url)
    path = parsed.path.lower()

    if path.endswith('.pdf'):
        return '.pdf'
    elif path.endswith('.doc'):
        return '.doc'
    elif path.endswith('.docx'):
        return '.docx'

    # Try content type if available
    if content_type:
        if 'pdf' in content_type.lower():
            return '.pdf'
        elif 'word' in content_type.lower() or 'msword' in content_type.lower():
            return '.doc'
        elif 'officedocument' in content_type.lower():
            return '.docx'

    # Default to .pdf
    return '.pdf'

def download_file(url: str, output_path: str) -> bool:
    """
    Download a file from URL to output_path.
    Returns True if successful, False otherwise.
    """
    try:
        print(f"  Downloading from: {url}")

        # Handle Google Drive links specially
        if 'drive.google.com' in url:
            # Try to convert to direct download link
            if '/file/d/' in url:
                file_id = url.split('/file/d/')[1].split('/')[0]
                url = f"https://drive.google.com/uc?export=download&id={file_id}"
                print(f"  Converted to direct download: {url}")

        # Set up headers to mimic a browser
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }

        # Make the request
        response = requests.get(url, headers=headers, timeout=TIMEOUT, allow_redirects=True)
        response.raise_for_status()

        # Check if we got a valid response
        content_type = response.headers.get('content-type', '')

        # Verify file extension matches content
        expected_ext = get_file_extension(url, content_type)
        if not output_path.endswith(expected_ext):
            # Update output path with correct extension
            base = os.path.splitext(output_path)[0]
            output_path = base + expected_ext

        # Save the file
        with open(output_path, 'wb') as f:
            f.write(response.content)

        file_size = len(response.content)
        print(f"  ✓ Downloaded: {file_size:,} bytes -> {output_path}")
        return True

    except requests.exceptions.RequestException as e:
        print(f"  ✗ Error downloading: {e}")
        return False
    except Exception as e:
        print(f"  ✗ Unexpected error: {e}")
        return False

def main():
    """Main function to download all contracts."""
    print("=" * 70)
    print("Teacher Contract PDF Downloader")
    print("=" * 70)

    # Create output directory
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    print(f"\nOutput directory: {OUTPUT_DIR}/")

    # Load contracts
    contracts = load_contracts()
    print(f"Loaded {len(contracts)} contracts from {CONTRACTS_FILE}\n")

    # Statistics
    successful = 0
    failed = 0
    skipped = 0

    # Process each contract
    for i, contract in enumerate(contracts, 1):
        district = contract.get('district', 'Unknown')
        url = contract.get('contract_url', '')

        print(f"[{i}/{len(contracts)}] {district}")

        # Skip if no URL or marked as not found
        if not url or url == "NOT_FOUND" or url.startswith("NOT_"):
            print(f"  ⊘ Skipped: No valid URL")
            skipped += 1
            continue

        # Prepare output filename
        safe_name = sanitize_filename(district)
        output_path = os.path.join(OUTPUT_DIR, f"{safe_name}.pdf")

        # Check if already downloaded
        if os.path.exists(output_path):
            file_size = os.path.getsize(output_path)
            print(f"  ⊙ Already exists: {file_size:,} bytes")
            successful += 1
            continue

        # Download the file
        if download_file(url, output_path):
            successful += 1
        else:
            failed += 1

        # Rate limiting delay
        if i < len(contracts):
            time.sleep(DOWNLOAD_DELAY)

    # Print summary
    print("\n" + "=" * 70)
    print("DOWNLOAD SUMMARY")
    print("=" * 70)
    print(f"Total contracts:     {len(contracts)}")
    print(f"Successfully saved:  {successful} ({successful/len(contracts)*100:.1f}%)")
    print(f"Failed:              {failed} ({failed/len(contracts)*100:.1f}%)")
    print(f"Skipped (no URL):    {skipped} ({skipped/len(contracts)*100:.1f}%)")
    print("=" * 70)
    print(f"\nFiles saved to: {os.path.abspath(OUTPUT_DIR)}/")

if __name__ == "__main__":
    main()
