"""
Script to initialize DynamoDB with sample Massachusetts school districts
Run with: python init_dynamodb_sample_data.py
"""

from database import get_table, init_db
from services.dynamodb_district_service import DynamoDBDistrictService
from schemas import DistrictCreate

# Sample Massachusetts school districts with their towns
SAMPLE_DISTRICTS = [
    {
        "name": "Springfield Public Schools",
        "main_address": "195 State Street, Springfield, MA 01103",
        "towns": ["Springfield"]
    },
    {
        "name": "Boston Public Schools",
        "main_address": "2300 Washington Street, Boston, MA 02119",
        "towns": ["Boston"]
    },
    {
        "name": "Worcester Public Schools",
        "main_address": "20 Irving Street, Worcester, MA 01609",
        "towns": ["Worcester"]
    },
    {
        "name": "Cambridge Public Schools",
        "main_address": "159 Thorndike Street, Cambridge, MA 02141",
        "towns": ["Cambridge"]
    },
    {
        "name": "Newton Public Schools",
        "main_address": "100 Walnut Street, Newton, MA 02460",
        "towns": ["Newton"]
    },
    {
        "name": "Quabbin Regional School District",
        "main_address": "872 South Street, Barre, MA 01005",
        "towns": ["Barre", "Hardwick", "Hubbardston", "New Braintree", "Oakham"]
    },
    {
        "name": "Berkshire Hills Regional School District",
        "main_address": "380 Main Road, Stockbridge, MA 01262",
        "towns": ["Great Barrington", "Stockbridge", "West Stockbridge"]
    },
    {
        "name": "Minuteman Regional Vocational Technical School District",
        "main_address": "758 Marrett Road, Lexington, MA 02421",
        "towns": ["Acton", "Arlington", "Belmont", "Bolton", "Boxborough", "Carlisle",
                  "Concord", "Dover", "Lancaster", "Lexington", "Lincoln", "Needham",
                  "Stow", "Sudbury", "Wayland", "Weston"]
    },
    {
        "name": "Amherst-Pelham Regional School District",
        "main_address": "170 Chestnut Street, Amherst, MA 01002",
        "towns": ["Amherst", "Pelham"]
    },
    {
        "name": "Brookline Public Schools",
        "main_address": "333 Washington Street, Brookline, MA 02445",
        "towns": ["Brookline"]
    },
    {
        "name": "Lowell Public Schools",
        "main_address": "155 Merrimack Street, Lowell, MA 01852",
        "towns": ["Lowell"]
    },
    {
        "name": "Framingham Public Schools",
        "main_address": "73 Mount Wayte Avenue, Framingham, MA 01702",
        "towns": ["Framingham"]
    }
]


def init_sample_data():
    """Initialize DynamoDB with sample data"""
    print("Initializing DynamoDB tables...")
    init_db()

    table = get_table()

    try:
        # Check if data already exists
        response = table.scan(Limit=1)
        if response.get('Count', 0) > 0:
            response_input = input("Table already contains data. Clear and reinitialize? (yes/no): ")
            if response_input.lower() != "yes":
                print("Skipping initialization.")
                return

            # Clear existing data
            print("Clearing existing data...")
            scan_response = table.scan()
            for item in scan_response.get('Items', []):
                table.delete_item(Key={'PK': item['PK'], 'SK': item['SK']})

        # Add sample districts
        print(f"\nAdding {len(SAMPLE_DISTRICTS)} sample districts...")
        for district_data in SAMPLE_DISTRICTS:
            print(f"  - Adding {district_data['name']}")

            # Create district
            district_create = DistrictCreate(**district_data)
            DynamoDBDistrictService.create_district(table, district_create)

        print(f"\n✓ Successfully initialized DynamoDB with {len(SAMPLE_DISTRICTS)} districts!")

        # Display summary
        scan_response = table.scan()
        total_items = len(scan_response.get('Items', []))
        print(f"✓ Total items in table: {total_items}")

    except Exception as e:
        print(f"\n✗ Error initializing DynamoDB: {e}")
        raise


if __name__ == "__main__":
    init_sample_data()
