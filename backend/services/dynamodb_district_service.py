from typing import List, Optional, Tuple
from datetime import datetime
from decimal import Decimal
import uuid
from boto3.dynamodb.conditions import Key, Attr
from botocore.exceptions import ClientError

from schemas import DistrictCreate, DistrictUpdate


class DynamoDBDistrictService:
    """Service layer for district operations using DynamoDB"""

    @staticmethod
    def _generate_id() -> str:
        """Generate a unique ID for a district"""
        return str(uuid.uuid4())

    @staticmethod
    def _create_district_item(district_id: str, district_data: DistrictCreate) -> dict:
        """Create a DynamoDB item from district data"""
        now = datetime.utcnow().isoformat()

        item = {
            'PK': f'DISTRICT#{district_id}',
            'SK': 'METADATA',
            'district_id': district_id,
            'name': district_data.name,
            'name_lower': district_data.name.lower(),  # For case-insensitive search
            'main_address': district_data.main_address or '',
            'towns': district_data.towns,
            'district_type': getattr(district_data, 'district_type', ''),
            'created_at': now,
            'updated_at': now,
            'entity_type': 'district'
        }

        return item

    @staticmethod
    def _create_town_items(district_id: str, district_name: str, towns: List[str]) -> List[dict]:
        """Create DynamoDB items for district-town relationships"""
        items = []
        for town in towns:
            item = {
                'PK': f'DISTRICT#{district_id}',
                'SK': f'TOWN#{town.upper()}',
                'GSI_TOWN_PK': f'TOWN#{town.upper()}',
                'GSI_TOWN_SK': f'DISTRICT#{district_name.upper()}',
                'district_id': district_id,
                'district_name': district_name,
                'town_name': town,
                'entity_type': 'district_town'
            }
            items.append(item)
        return items

    @staticmethod
    def create_district(table, district_data: DistrictCreate) -> dict:
        """Create a new district with associated towns"""
        district_id = DynamoDBDistrictService._generate_id()

        # Create main district item
        district_item = DynamoDBDistrictService._create_district_item(district_id, district_data)

        try:
            # Put district metadata
            table.put_item(Item=district_item)

            # Put town relationships
            town_items = DynamoDBDistrictService._create_town_items(
                district_id, district_data.name, district_data.towns
            )
            for town_item in town_items:
                table.put_item(Item=town_item)

            return DynamoDBDistrictService._item_to_dict(district_item)
        except ClientError as e:
            raise Exception(f"Error creating district: {e.response['Error']['Message']}")

    @staticmethod
    def get_district(table, district_id: str) -> Optional[dict]:
        """Get a district by ID"""
        try:
            response = table.get_item(
                Key={
                    'PK': f'DISTRICT#{district_id}',
                    'SK': 'METADATA'
                }
            )

            if 'Item' not in response:
                return None

            return DynamoDBDistrictService._item_to_dict(response['Item'])
        except ClientError as e:
            raise Exception(f"Error getting district: {e.response['Error']['Message']}")

    @staticmethod
    def get_districts(
        table,
        name: Optional[str] = None,
        town: Optional[str] = None,
        limit: int = 50,
        offset: int = 0
    ) -> Tuple[List[dict], int]:
        """
        Get districts with optional filtering
        Returns tuple of (districts, total_count)
        """
        try:
            if town:
                # Use GSI_TOWN to query by town
                return DynamoDBDistrictService._query_by_town(table, town, limit, offset)
            elif name:
                # Scan with filter on name
                return DynamoDBDistrictService._scan_by_name(table, name, limit, offset)
            else:
                # Get all districts
                return DynamoDBDistrictService._get_all_districts(table, limit, offset)
        except ClientError as e:
            raise Exception(f"Error getting districts: {e.response['Error']['Message']}")

    @staticmethod
    def _query_by_town(table, town: str, limit: int, offset: int) -> Tuple[List[dict], int]:
        """Query districts by town using GSI_TOWN"""
        response = table.query(
            IndexName='GSI_TOWN',
            KeyConditionExpression=Key('GSI_TOWN_PK').eq(f'TOWN#{town.upper()}')
        )

        # Get unique district IDs
        district_ids = set()
        for item in response.get('Items', []):
            if 'district_id' in item:
                district_ids.add(item['district_id'])

        # Fetch full district data
        districts = []
        for district_id in district_ids:
            district = DynamoDBDistrictService.get_district(table, district_id)
            if district:
                districts.append(district)

        # Apply pagination
        total = len(districts)
        districts = districts[offset:offset + limit]

        return districts, total

    @staticmethod
    def _scan_by_name(table, name: str, limit: int, offset: int) -> Tuple[List[dict], int]:
        """Scan districts by name"""
        response = table.scan(
            FilterExpression=Attr('entity_type').eq('district') & Attr('name_lower').eq(name.lower())
        )

        districts = [DynamoDBDistrictService._item_to_dict(item) for item in response.get('Items', [])]

        total = len(districts)
        districts = districts[offset:offset + limit]

        return districts, total

    @staticmethod
    def _get_all_districts(table, limit: int, offset: int) -> Tuple[List[dict], int]:
        """Get all districts"""
        response = table.scan(
            FilterExpression=Attr('entity_type').eq('district')
        )

        districts = [DynamoDBDistrictService._item_to_dict(item) for item in response.get('Items', [])]

        total = len(districts)
        districts = districts[offset:offset + limit]

        return districts, total

    @staticmethod
    def update_district(
        table,
        district_id: str,
        district_data: DistrictUpdate
    ) -> Optional[dict]:
        """Update a district"""
        # Get existing district
        existing = DynamoDBDistrictService.get_district(table, district_id)
        if not existing:
            return None

        try:
            # Update metadata
            update_expr_parts = []
            expr_attr_values = {}
            expr_attr_names = {}

            if district_data.name is not None:
                update_expr_parts.append('#name = :name')
                update_expr_parts.append('name_lower = :name_lower')
                expr_attr_values[':name'] = district_data.name
                expr_attr_values[':name_lower'] = district_data.name.lower()
                expr_attr_names['#name'] = 'name'

            if district_data.main_address is not None:
                update_expr_parts.append('main_address = :address')
                expr_attr_values[':address'] = district_data.main_address

            if district_data.district_type is not None:
                update_expr_parts.append('district_type = :district_type')
                expr_attr_values[':district_type'] = district_data.district_type

            update_expr_parts.append('updated_at = :updated_at')
            expr_attr_values[':updated_at'] = datetime.utcnow().isoformat()

            if district_data.towns is not None:
                update_expr_parts.append('towns = :towns')
                expr_attr_values[':towns'] = district_data.towns

            # Update main item
            table.update_item(
                Key={
                    'PK': f'DISTRICT#{district_id}',
                    'SK': 'METADATA'
                },
                UpdateExpression='SET ' + ', '.join(update_expr_parts),
                ExpressionAttributeValues=expr_attr_values,
                ExpressionAttributeNames=expr_attr_names if expr_attr_names else None
            )

            # Update town relationships if provided
            if district_data.towns is not None:
                # Delete old town items
                response = table.query(
                    KeyConditionExpression=Key('PK').eq(f'DISTRICT#{district_id}') & Key('SK').begins_with('TOWN#')
                )
                for item in response.get('Items', []):
                    table.delete_item(Key={'PK': item['PK'], 'SK': item['SK']})

                # Create new town items
                new_name = district_data.name if district_data.name else existing['name']
                town_items = DynamoDBDistrictService._create_town_items(
                    district_id, new_name, district_data.towns
                )
                for town_item in town_items:
                    table.put_item(Item=town_item)

            # Return updated district
            return DynamoDBDistrictService.get_district(table, district_id)
        except ClientError as e:
            raise Exception(f"Error updating district: {e.response['Error']['Message']}")

    @staticmethod
    def delete_district(table, district_id: str) -> bool:
        """Delete a district (and all related items)"""
        try:
            # Query all items for this district
            response = table.query(
                KeyConditionExpression=Key('PK').eq(f'DISTRICT#{district_id}')
            )

            if not response.get('Items'):
                return False

            # Delete all items
            for item in response['Items']:
                table.delete_item(Key={'PK': item['PK'], 'SK': item['SK']})

            return True
        except ClientError as e:
            raise Exception(f"Error deleting district: {e.response['Error']['Message']}")

    @staticmethod
    def search_districts(
        table,
        query_text: Optional[str] = None,
        limit: int = 50,
        offset: int = 0
    ) -> Tuple[List[dict], int]:
        """
        Search districts by name or town
        Returns tuple of (districts, total_count)
        """
        if not query_text:
            return DynamoDBDistrictService._get_all_districts(table, limit, offset)

        try:
            # Search by name
            name_results = table.scan(
                FilterExpression=Attr('entity_type').eq('district') & Attr('name_lower').contains(query_text.lower())
            )

            # Search by town using GSI
            town_results = table.query(
                IndexName='GSI_TOWN',
                KeyConditionExpression=Key('GSI_TOWN_PK').eq(f'TOWN#{query_text.upper()}')
            )

            # Combine results
            district_ids = set()

            # Add districts from name search
            for item in name_results.get('Items', []):
                district_ids.add(item['district_id'])

            # Add districts from town search
            for item in town_results.get('Items', []):
                if 'district_id' in item:
                    district_ids.add(item['district_id'])

            # Fetch full district data
            districts = []
            for district_id in district_ids:
                district = DynamoDBDistrictService.get_district(table, district_id)
                if district:
                    districts.append(district)

            # Apply pagination
            total = len(districts)
            districts = districts[offset:offset + limit]

            return districts, total
        except ClientError as e:
            raise Exception(f"Error searching districts: {e.response['Error']['Message']}")

    @staticmethod
    def _item_to_dict(item: dict) -> dict:
        """Convert DynamoDB item to response dict"""
        return {
            'id': item['district_id'],
            'name': item['name'],
            'main_address': item.get('main_address', ''),
            'towns': item.get('towns', []),
            'district_type': item.get('district_type', ''),
            'created_at': item['created_at'],
            'updated_at': item['updated_at']
        }
