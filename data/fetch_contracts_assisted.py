#!/usr/bin/env python3
"""
Assistant script for tracking progress on finding teacher contracts.
This script manages the process of finding contracts with manual/assisted lookup.
"""

import json
import os
from typing import List, Dict, Tuple

DISTRICTS_FILE = "contracts_folders.json"
OUTPUT_FILE = "teacher_contracts.json"
PROGRESS_FILE = "contract_search_progress.json"

def load_districts() -> List[str]:
    """Load the list of districts from the JSON file."""
    with open(DISTRICTS_FILE, 'r') as f:
        return json.load(f)

def load_results() -> Dict[str, str]:
    """Load existing results."""
    if os.path.exists(OUTPUT_FILE):
        with open(OUTPUT_FILE, 'r') as f:
            data = json.load(f)
            return {item['district']: item['contract_url'] for item in data}
    return {}

def load_progress() -> Dict:
    """Load progress tracking data."""
    if os.path.exists(PROGRESS_FILE):
        with open(PROGRESS_FILE, 'r') as f:
            return json.load(f)
    return {"last_processed_index": 0, "failed_districts": []}

def save_progress(progress: Dict):
    """Save progress tracking data."""
    with open(PROGRESS_FILE, 'w') as f:
        json.dump(progress, f, indent=2)

def save_results(results: Dict[str, str]):
    """Save results to the output file."""
    output = [
        {"district": district, "contract_url": url}
        for district, url in sorted(results.items())
    ]
    with open(OUTPUT_FILE, 'w') as f:
        json.dump(output, f, indent=2)

def get_next_batch(batch_size: int = 10) -> Tuple[List[str], int]:
    """Get the next batch of districts to process."""
    districts = load_districts()
    results = load_results()
    progress = load_progress()

    # Find unprocessed districts
    unprocessed = [d for d in districts if d not in results]

    if not unprocessed:
        print("All districts have been processed!")
        return [], 0

    # Get next batch
    batch = unprocessed[:batch_size]
    remaining = len(unprocessed)

    return batch, remaining

def update_contract(district: str, url: str):
    """Update a single district's contract URL."""
    results = load_results()
    results[district] = url
    save_results(results)
    print(f"Updated {district}: {url}")

def generate_search_queries(districts: List[str]) -> List[Tuple[str, str]]:
    """Generate search queries for a batch of districts."""
    queries = []
    for district in districts:
        query = f"{district} Massachusetts school district Unit A teacher contract collective bargaining agreement"
        queries.append((district, query))
    return queries

def report_status():
    """Print current status."""
    districts = load_districts()
    results = load_results()
    progress = load_progress()

    total = len(districts)
    found = len([u for u in results.values() if u and u != "NOT_FOUND"])
    not_found = len([u for u in results.values() if u == "NOT_FOUND"])
    remaining = total - len(results)

    print("\n" + "=" * 60)
    print("TEACHER CONTRACT SEARCH STATUS")
    print("=" * 60)
    print(f"Total districts:        {total}")
    print(f"Contracts found:        {found} ({found/total*100:.1f}%)")
    print(f"Not found:             {not_found} ({not_found/total*100:.1f}%)")
    print(f"Remaining to search:   {remaining} ({remaining/total*100:.1f}%)")
    print("=" * 60)

    if remaining > 0:
        print("\nNext districts to search:")
        unprocessed = [d for d in districts if d not in results]
        for i, d in enumerate(unprocessed[:5], 1):
            print(f"  {i}. {d}")
        if len(unprocessed) > 5:
            print(f"  ... and {len(unprocessed) - 5} more")

def main():
    """Main CLI interface."""
    import sys

    if len(sys.argv) < 2:
        print("Usage:")
        print("  python fetch_contracts_assisted.py status          # Show current status")
        print("  python fetch_contracts_assisted.py next [N]        # Get next N districts to search (default 10)")
        print("  python fetch_contracts_assisted.py add <district> <url>  # Add a contract URL")
        print("  python fetch_contracts_assisted.py missing         # List districts without contracts")
        return

    command = sys.argv[1]

    if command == "status":
        report_status()

    elif command == "next":
        batch_size = int(sys.argv[2]) if len(sys.argv) > 2 else 10
        batch, remaining = get_next_batch(batch_size)
        print(f"\nNext {len(batch)} districts to search ({remaining} total remaining):\n")
        queries = generate_search_queries(batch)
        for i, (district, query) in enumerate(queries, 1):
            print(f"{i}. {district}")
            print(f"   Search query: {query}\n")

    elif command == "add":
        if len(sys.argv) < 4:
            print("Error: Must provide district name and URL")
            print("Usage: python fetch_contracts_assisted.py add <district> <url>")
            return
        district = sys.argv[2]
        url = sys.argv[3]
        update_contract(district, url)
        report_status()

    elif command == "missing":
        districts = load_districts()
        results = load_results()
        missing = [d for d in districts if d not in results]
        print(f"\nDistricts without contracts ({len(missing)}):")
        for d in missing:
            print(f"  - {d}")

    else:
        print(f"Unknown command: {command}")

if __name__ == "__main__":
    main()
