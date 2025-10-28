"""
Script to initialize the database with sample Massachusetts school districts
Run with: python init_sample_data.py
"""

from database import SessionLocal, init_db
from models import District, DistrictTown

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
    """Initialize database with sample data"""
    print("Initializing database tables...")
    init_db()

    db = SessionLocal()
    try:
        # Check if data already exists
        existing_count = db.query(District).count()
        if existing_count > 0:
            print(f"Database already contains {existing_count} districts.")
            response = input("Do you want to clear and reinitialize? (yes/no): ")
            if response.lower() != "yes":
                print("Skipping initialization.")
                return

            # Clear existing data
            print("Clearing existing data...")
            db.query(DistrictTown).delete()
            db.query(District).delete()
            db.commit()

        # Add sample districts
        print(f"\nAdding {len(SAMPLE_DISTRICTS)} sample districts...")
        for district_data in SAMPLE_DISTRICTS:
            print(f"  - Adding {district_data['name']}")

            # Create district
            district = District(
                name=district_data["name"],
                main_address=district_data["main_address"]
            )
            db.add(district)
            db.flush()

            # Add towns
            for town_name in district_data["towns"]:
                town = DistrictTown(
                    district_id=district.id,
                    town_name=town_name
                )
                db.add(town)

        db.commit()
        print(f"\n✓ Successfully initialized database with {len(SAMPLE_DISTRICTS)} districts!")

        # Display summary
        total_towns = db.query(DistrictTown).count()
        print(f"✓ Total towns: {total_towns}")

    except Exception as e:
        print(f"\n✗ Error initializing database: {e}")
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    init_sample_data()
