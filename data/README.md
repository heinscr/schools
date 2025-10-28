# District Data

This directory contains Massachusetts school district data files.

## Files

### districts.json
Main dataset containing all Massachusetts school districts with:
- District name
- Main address
- Member towns

Organized by district type:
- `regional_academic` - Regional school districts
- `regional_vocational` - Regional vocational/technical schools
- `county_agricultural` - County agricultural schools
- `other_districts` - Municipal (single-town) districts

**Size**: ~75KB
**Districts**: 356 total

### all_districts.json
Complete unfiltered dataset including all districts.

**Size**: ~85KB

## Importing Data

To import districts into DynamoDB:

```bash
cd ../backend
source venv/bin/activate
python import_districts.py --file ../data/districts.json
```

### Dry Run
Preview the import without making changes:
```bash
python import_districts.py --file ../data/districts.json --dry-run
```

## Data Structure

Example district entry:
```json
{
  "district": "Acton-Boxborough",
  "members": ["Acton", "Boxborough"],
  "address": "15 Charter Rd, Acton, MA 01720"
}
```

## Source

District data compiled from:
- Massachusetts Department of Elementary and Secondary Education (DESE)
- Public school district records
- Official district websites
