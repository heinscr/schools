import os
import boto3
import logging
from typing import Any
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

# Load environment variables from .env file for local development
load_dotenv()

# Get DynamoDB configuration from environment
DYNAMODB_ENDPOINT = os.getenv("DYNAMODB_ENDPOINT")  # For local development
AWS_REGION = os.getenv("AWS_REGION", "us-east-2")
TABLE_NAME = os.getenv("DYNAMODB_TABLE_NAME")

if not TABLE_NAME:
    raise ValueError("DYNAMODB_TABLE_NAME environment variable must be set")

# Create DynamoDB client
def get_dynamodb_client() -> Any:
    """Get DynamoDB client

    Returns:
        boto3 DynamoDB client configured for local or production use
    """
    if DYNAMODB_ENDPOINT:
        # Local development with DynamoDB Local
        return boto3.client(
            'dynamodb',
            endpoint_url=DYNAMODB_ENDPOINT,
            region_name=AWS_REGION
        )
    else:
        # Production - use AWS DynamoDB
        return boto3.client('dynamodb', region_name=AWS_REGION)


def get_dynamodb_resource() -> Any:
    """Get DynamoDB resource (higher-level interface)

    Returns:
        boto3 DynamoDB resource configured for local or production use
    """
    if DYNAMODB_ENDPOINT:
        # Local development
        return boto3.resource(
            'dynamodb',
            endpoint_url=DYNAMODB_ENDPOINT,
            region_name=AWS_REGION
        )
    else:
        # Production
        return boto3.resource('dynamodb', region_name=AWS_REGION)


# Global clients (reused across Lambda invocations)
dynamodb_client = get_dynamodb_client()
dynamodb_resource = get_dynamodb_resource()
table = dynamodb_resource.Table(TABLE_NAME)


def init_db() -> None:
    """
    Initialize DynamoDB table (for local development only)
    In production, table is created by Terraform

    Creates a single table with all GSIs:
    - ExactMatchIndex: For salary comparisons across districts
    - FallbackQueryIndex: For fallback matching logic
    - GSI_TOWN: For town-based district searches
    - ComparisonIndex: Fast single-query salary comparisons (Option 2 optimization)
    """
    if not DYNAMODB_ENDPOINT:
        logger.info("Skipping table creation - using AWS DynamoDB (table managed by Terraform)")
        return

    try:
        # Check if table exists
        dynamodb_client.describe_table(TableName=TABLE_NAME)
        logger.info(f"Table {TABLE_NAME} already exists")
    except dynamodb_client.exceptions.ResourceNotFoundException:
        # Create table for local development
        logger.info(f"Creating local DynamoDB table: {TABLE_NAME}")
        local_table = dynamodb_resource.create_table(
            TableName=TABLE_NAME,
            KeySchema=[
                {'AttributeName': 'PK', 'KeyType': 'HASH'},
                {'AttributeName': 'SK', 'KeyType': 'RANGE'}
            ],
            AttributeDefinitions=[
                {'AttributeName': 'PK', 'AttributeType': 'S'},
                {'AttributeName': 'SK', 'AttributeType': 'S'},
                {'AttributeName': 'GSI1PK', 'AttributeType': 'S'},
                {'AttributeName': 'GSI1SK', 'AttributeType': 'S'},
                {'AttributeName': 'GSI2PK', 'AttributeType': 'S'},
                {'AttributeName': 'GSI2SK', 'AttributeType': 'S'},
                {'AttributeName': 'GSI_TOWN_PK', 'AttributeType': 'S'},
                {'AttributeName': 'GSI_TOWN_SK', 'AttributeType': 'S'},
                {'AttributeName': 'GSI_COMP_PK', 'AttributeType': 'S'},
                {'AttributeName': 'GSI_COMP_SK', 'AttributeType': 'S'}
            ],
            GlobalSecondaryIndexes=[
                {
                    'IndexName': 'ExactMatchIndex',
                    'KeySchema': [
                        {'AttributeName': 'GSI1PK', 'KeyType': 'HASH'},
                        {'AttributeName': 'GSI1SK', 'KeyType': 'RANGE'}
                    ],
                    'Projection': {'ProjectionType': 'ALL'},
                    'ProvisionedThroughput': {
                        'ReadCapacityUnits': 5,
                        'WriteCapacityUnits': 5
                    }
                },
                {
                    'IndexName': 'FallbackQueryIndex',
                    'KeySchema': [
                        {'AttributeName': 'GSI2PK', 'KeyType': 'HASH'},
                        {'AttributeName': 'GSI2SK', 'KeyType': 'RANGE'}
                    ],
                    'Projection': {'ProjectionType': 'ALL'},
                    'ProvisionedThroughput': {
                        'ReadCapacityUnits': 5,
                        'WriteCapacityUnits': 5
                    }
                },
                {
                    'IndexName': 'GSI_TOWN',
                    'KeySchema': [
                        {'AttributeName': 'GSI_TOWN_PK', 'KeyType': 'HASH'},
                        {'AttributeName': 'GSI_TOWN_SK', 'KeyType': 'RANGE'}
                    ],
                    'Projection': {'ProjectionType': 'ALL'},
                    'ProvisionedThroughput': {
                        'ReadCapacityUnits': 5,
                        'WriteCapacityUnits': 5
                    }
                },
                {
                    'IndexName': 'ComparisonIndex',
                    'KeySchema': [
                        {'AttributeName': 'GSI_COMP_PK', 'KeyType': 'HASH'},
                        {'AttributeName': 'GSI_COMP_SK', 'KeyType': 'RANGE'}
                    ],
                    'Projection': {'ProjectionType': 'ALL'},
                    'ProvisionedThroughput': {
                        'ReadCapacityUnits': 5,
                        'WriteCapacityUnits': 5
                    }
                }
            ],
            BillingMode='PROVISIONED',
            ProvisionedThroughput={
                'ReadCapacityUnits': 5,
                'WriteCapacityUnits': 5
            }
        )
        local_table.wait_until_exists()
        logger.info(f"Table {TABLE_NAME} created successfully")


def get_table() -> Any:
    """Dependency function to get DynamoDB table

    Returns:
        DynamoDB table resource for dependency injection
    """
    return table