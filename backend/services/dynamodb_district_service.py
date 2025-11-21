from typing import List, Optional, Tuple
from datetime import datetime, UTC
from decimal import Decimal
import uuid
from boto3.dynamodb.conditions import Key, Attr
from botocore.exceptions import ClientError

from schemas import DistrictCreate, DistrictUpdate
from config import MAX_DYNAMODB_FETCH_LIMIT


class DynamoDBDistrictService:
    """Service layer for district operations using DynamoDB"""

    @staticmethod
    def _generate_id() -> str:
        """Generate a unique ID for a district"""
        return str(uuid.uuid4())

    @staticmethod
    def _create_district_item(district_id: str, district_data: DistrictCreate) -> dict:
        """Create a DynamoDB item from district data"""
        now = datetime.now(UTC).isoformat()

        item = {
            'PK': f'DISTRICT#{district_id}',
            'SK': 'METADATA',
            'district_id': district_id,
            'name': district_data.name,
            'name_lower': district_data.name.lower(),  # For case-insensitive search
            'main_address': district_data.main_address or '',
            'district_url': district_data.district_url or '',
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
        # Use pagination to limit items fetched from DynamoDB
        # Add buffer to account for offset, cap for DoS protection
        max_items_to_fetch = min(offset + limit + 50, MAX_DYNAMODB_FETCH_LIMIT)

        response = table.query(
            IndexName='GSI_TOWN',
            KeyConditionExpression=Key('GSI_TOWN_PK').eq(f'TOWN#{town.upper()}'),
            Limit=max_items_to_fetch
        )

        # Get unique district IDs (maintain order)
        district_ids = []
        seen_ids = set()
        for item in response.get('Items', []):
            if 'district_id' in item and item['district_id'] not in seen_ids:
                district_ids.append(item['district_id'])
                seen_ids.add(item['district_id'])

        # Fetch only the district IDs we need (after offset, up to limit)
        # This reduces N+1 queries to only what's needed
        districts = []
        for district_id in district_ids[offset:offset + limit]:
            district = DynamoDBDistrictService.get_district(table, district_id)
            if district:
                districts.append(district)

        # Return actual count
        total = len(district_ids)

        return districts, total

    @staticmethod
    def _scan_by_name(table, name: str, limit: int, offset: int) -> Tuple[List[dict], int]:
        """Scan districts by name (exact match, case-insensitive)"""
        districts = []
        last_evaluated_key = None
        
        # For exact name match, we need to scan with a safety Limit to avoid DoS.
        # Fetch a bounded number of items computed from offset+limit with a small buffer,
        # and cap by MAX_DYNAMODB_FETCH_LIMIT.
        max_items_to_fetch = min(offset + limit + 50, MAX_DYNAMODB_FETCH_LIMIT)

        while True:
            scan_kwargs = {
                'FilterExpression': Attr('entity_type').eq('district') & Attr('name_lower').eq(name.lower()),
                'Limit': max_items_to_fetch
            }
            
            if last_evaluated_key:
                scan_kwargs['ExclusiveStartKey'] = last_evaluated_key
            
            response = table.scan(**scan_kwargs)
            
            districts.extend([
                DynamoDBDistrictService._item_to_dict(item) 
                for item in response.get('Items', [])
            ])
            
            # Check if there are more items to scan
            last_evaluated_key = response.get('LastEvaluatedKey')
            if not last_evaluated_key:
                break
            
            # Safety check - if we found a match for exact name, we can stop
            # (assuming unique names)
            if len(districts) > 0:
                break

        total = len(districts)
        districts = districts[offset:offset + limit]

        return districts, total

    @staticmethod
    def _get_all_districts(table, limit: int, offset: int) -> Tuple[List[dict], int]:
        """Get all districts using GSI_METADATA index for efficient querying"""
        districts: List[dict] = []
        last_evaluated_key = None

        # Compute a capped fetch limit to guard against DoS style large offsets
        fetch_limit = min(offset + limit + 50, MAX_DYNAMODB_FETCH_LIMIT)

        # First attempt: query GSI_METADATA (sparse index of district metadata)
        try:
            while True:
                query_kwargs = {
                    'IndexName': 'GSI_METADATA',
                    'KeyConditionExpression': Key('SK').eq('METADATA'),
                    'Limit': fetch_limit
                }

                if last_evaluated_key:
                    query_kwargs['ExclusiveStartKey'] = last_evaluated_key

                response = table.query(**query_kwargs)

                districts.extend([
                    DynamoDBDistrictService._item_to_dict(item)
                    for item in response.get('Items', [])
                ])

                # If we already fetched enough for requested page, we can stop early
                if len(districts) >= offset + limit or len(districts) >= fetch_limit:
                    break

                last_evaluated_key = response.get('LastEvaluatedKey')
                if not last_evaluated_key:
                    break
        except Exception:
            # Fall back to scan if the index doesn't exist yet
            districts = []

        # Fallback: if index returned no items (e.g., not ACTIVE yet), perform a filtered scan
        if not districts:
            last_evaluated_key = None
            while True:
                scan_kwargs = {
                    'FilterExpression': Attr('entity_type').eq('district'),
                    'Limit': fetch_limit
                }
                if last_evaluated_key:
                    scan_kwargs['ExclusiveStartKey'] = last_evaluated_key
                response = table.scan(**scan_kwargs)
                districts.extend([
                    DynamoDBDistrictService._item_to_dict(item)
                    for item in response.get('Items', [])
                ])
                if len(districts) >= offset + limit or len(districts) >= fetch_limit:
                    break
                last_evaluated_key = response.get('LastEvaluatedKey')
                if not last_evaluated_key:
                    break

        # Ensure deterministic ordering by name
        districts.sort(key=lambda d: d.get('name', '').lower())

        paginated = districts[offset:offset + limit]
        total = len(districts)
        return paginated, total

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

            if district_data.district_url is not None:
                update_expr_parts.append('district_url = :district_url')
                expr_attr_values[':district_url'] = district_data.district_url

            if district_data.district_type is not None:
                update_expr_parts.append('district_type = :district_type')
                expr_attr_values[':district_type'] = district_data.district_type

            update_expr_parts.append('updated_at = :updated_at')
            expr_attr_values[':updated_at'] = datetime.now(UTC).isoformat()

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
            # Limit operations to prevent DoS
            max_items_to_fetch = min(offset + limit + 50, MAX_DYNAMODB_FETCH_LIMIT)

            # Search by name using GSI_METADATA index with begins_with for prefix matching
            # This is much more efficient than scanning the entire table
            query_lower = query_text.lower()
            name_results_items = []
            last_evaluated_key = None

            while True:
                query_kwargs = {
                    'IndexName': 'GSI_METADATA',
                    'KeyConditionExpression': Key('SK').eq('METADATA') & Key('name_lower').begins_with(query_lower),
                    'Limit': max_items_to_fetch
                }

                if last_evaluated_key:
                    query_kwargs['ExclusiveStartKey'] = last_evaluated_key

                name_results = table.query(**query_kwargs)
                name_results_items.extend(name_results.get('Items', []))

                # If we have enough items or no more pages, stop
                if len(name_results_items) >= max_items_to_fetch:
                    break

                last_evaluated_key = name_results.get('LastEvaluatedKey')
                if not last_evaluated_key:
                    break

            # Search by town using GSI with limit
            town_results = table.query(
                IndexName='GSI_TOWN',
                KeyConditionExpression=Key('GSI_TOWN_PK').eq(f'TOWN#{query_text.upper()}'),
                Limit=max_items_to_fetch
            )

            # Combine results (maintain order, avoid duplicates)
            districts_map = {}
            seen_ids = set()

            # Add districts from name search first (these are already full district items)
            for item in name_results_items:
                district_id = item['district_id']
                if district_id not in seen_ids:
                    districts_map[district_id] = DynamoDBDistrictService._item_to_dict(item)
                    seen_ids.add(district_id)

            # Add districts from town search
            # Note: GSI_TOWN items only contain town reference data, not full district data
            # We need to fetch the full METADATA items for these districts
            town_district_ids = []
            for item in town_results.get('Items', []):
                if 'district_id' in item and item['district_id'] not in seen_ids:
                    town_district_ids.append(item['district_id'])
                    seen_ids.add(item['district_id'])

            # Fetch town-based districts
            # TODO: Optimize with batch_get_item for better performance in production
            if town_district_ids:
                for district_id in town_district_ids:
                    district = DynamoDBDistrictService.get_district(table, district_id)
                    if district:
                        districts_map[district_id] = district

            # Sort by insertion order and apply pagination
            all_district_ids = list(districts_map.keys())
            paginated_ids = all_district_ids[offset:offset + limit]
            districts = [districts_map[did] for did in paginated_ids]

            # Return actual count
            total = len(all_district_ids)

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
            'district_url': item.get('district_url', ''),
            'towns': item.get('towns', []),
            'district_type': item.get('district_type', ''),
            'created_at': item['created_at'],
            'updated_at': item['updated_at']
        }
