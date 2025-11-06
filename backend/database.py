import os
import boto3
import logging
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

# Load environment variables from .env file for local development
load_dotenv()

# Get DynamoDB configuration from environment
DYNAMODB_ENDPOINT = os.getenv("DYNAMODB_ENDPOINT")  # For local development
AWS_REGION = os.getenv("AWS_REGION", "us-east-2")
DISTRICTS_TABLE_NAME = os.getenv("DYNAMODB_DISTRICTS_TABLE")

if not DISTRICTS_TABLE_NAME:
    raise ValueError("DYNAMODB_DISTRICTS_TABLE environment variable must be set")

# Create DynamoDB client
def get_dynamodb_client():
    """Get DynamoDB client"""
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


def get_dynamodb_resource():
    """Get DynamoDB resource (higher-level interface)"""
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
districts_table = dynamodb_resource.Table(DISTRICTS_TABLE_NAME)


def init_db():
    """
    Initialize DynamoDB tables (for local development only)
    In production, tables are created by Terraform
    """
    if not DYNAMODB_ENDPOINT:
        logger.info("Skipping table creation - using AWS DynamoDB (tables managed by Terraform)")
        return

    try:
        # Check if table exists
        dynamodb_client.describe_table(TableName=DISTRICTS_TABLE_NAME)
        logger.info(f"Table {DISTRICTS_TABLE_NAME} already exists")
    except dynamodb_client.exceptions.ResourceNotFoundException:
        # Create table for local development
        logger.info(f"Creating local DynamoDB table: {DISTRICTS_TABLE_NAME}")
        table = dynamodb_resource.create_table(
            TableName=DISTRICTS_TABLE_NAME,
            KeySchema=[
                {'AttributeName': 'PK', 'KeyType': 'HASH'},
                {'AttributeName': 'SK', 'KeyType': 'RANGE'}
            ],
            AttributeDefinitions=[
                {'AttributeName': 'PK', 'AttributeType': 'S'},
                {'AttributeName': 'SK', 'AttributeType': 'S'},
                {'AttributeName': 'GSI_TOWN_PK', 'AttributeType': 'S'},
                {'AttributeName': 'GSI_TOWN_SK', 'AttributeType': 'S'}
            ],
            GlobalSecondaryIndexes=[
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
                }
            ],
            BillingMode='PROVISIONED',
            ProvisionedThroughput={
                'ReadCapacityUnits': 5,
                'WriteCapacityUnits': 5
            }
        )
        table.wait_until_exists()
        logger.info(f"Table {DISTRICTS_TABLE_NAME} created successfully")


def get_table():
    """Dependency function to get DynamoDB table"""
    return districts_table