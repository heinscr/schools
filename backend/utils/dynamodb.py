"""
DynamoDB utility functions for batch operations and common queries
"""
import boto3
from typing import Dict, List


def get_district_towns(district_ids: List[str], districts_table_name: str) -> Dict[str, List[str]]:
    """
    Batch fetch towns for multiple districts from DynamoDB

    Args:
        district_ids: List of district IDs to fetch
        districts_table_name: Name of the DynamoDB districts table

    Returns:
        Dict mapping district_id to list of town names
    """
    if not districts_table_name or not district_ids:
        print(f"get_district_towns: table={districts_table_name}, ids_count={len(district_ids) if district_ids else 0}")
        return {}

    district_towns = {}

    try:
        # Use DynamoDB client for batch_get_item
        client = boto3.client('dynamodb')
        print(f"Fetching towns for {len(district_ids)} districts")

        # Batch get items (max 100 at a time)
        for i in range(0, len(district_ids), 100):
            batch = district_ids[i:i + 100]
            print(f"Batch {i//100 + 1}: {len(batch)} districts")

            # Build request items
            keys = [
                {
                    'PK': {'S': f'DISTRICT#{district_id}'},
                    'SK': {'S': 'METADATA'}
                }
                for district_id in batch
            ]

            response = client.batch_get_item(
                RequestItems={
                    districts_table_name: {
                        'Keys': keys
                    }
                }
            )

            items = response.get('Responses', {}).get(districts_table_name, [])
            print(f"Got {len(items)} items back from DynamoDB")

            # Extract towns from responses
            for item in items:
                # Convert DynamoDB low-level format to normal values
                district_id_attr = item.get('district_id', {})
                district_id = district_id_attr.get('S') if isinstance(district_id_attr, dict) else district_id_attr

                towns_attr = item.get('towns', {})
                if isinstance(towns_attr, dict) and 'L' in towns_attr:
                    towns = [t.get('S', '') for t in towns_attr['L'] if isinstance(t, dict)]
                else:
                    towns = []

                if district_id:
                    district_towns[district_id] = towns
                    print(f"  {district_id}: {towns}")

        print(f"Returning {len(district_towns)} district->towns mappings")

    except Exception as e:
        print(f"Error batch fetching district towns: {str(e)}")
        import traceback
        traceback.print_exc()
        # Return empty dict on error

    return district_towns
